"""Investment workflow v2 — DeepAgents orchestration.

Architecture:
- 1 main orchestrator agent (create_deep_agent with subagents=[...] and tools=[...])
- 3 specialized sub-agents (steps 1-3), each with its own prompt and tool subset
- The main orchestrator handles step 4 (decision & thesis) directly via its own tools
- Sub-agents are defined natively via DeepAgents' SubAgent TypedDict
- Inter-agent results passed as text in task prompts (data volumes are small enough)
- All persistent data saved to DB by tools during execution
- Temp workspace cleaned up after each run
"""
import json
import logging
import os
import shutil
import time
from datetime import datetime, timezone
from typing import Any, AsyncGenerator
from uuid import uuid4

logger = logging.getLogger(__name__)

from deepagents import create_deep_agent
from deepagents.middleware.subagents import SubAgent
from langchain_core.messages import HumanMessage
from langchain_openai import ChatOpenAI

from config import settings
from database import SessionLocal
from dependencies.investment.agent_prompts import (
    MAIN_ORCHESTRATOR_PROMPT,
    build_macro_scan_prompt,
    build_opportunity_research_prompt,
    build_portfolio_review_prompt,
)
from dependencies.investment.agent_tools import build_tools, filter_tools, prefetch_agent_context
from models.database_models import InvestmentReport

# Model name resolved from settings (env var: INVESTMENT_MODEL).
# Kept as a module-level shorthand so the pricing lookup can reference it.
_MODEL_NAME = settings.investment_model

# Pricing per 1M tokens (USD). Update when OpenAI changes rates.
# cache_read_per_1m: price for tokens served from the prompt cache (subset of input_tokens).
# Fresh input cost = (input_tokens - cached_tokens) * input_per_1m / 1e6
# Cached input cost = cached_tokens * cache_read_per_1m / 1e6
_MODEL_PRICING: dict[str, dict[str, float]] = {
    "gpt-4.1-mini": {"input_per_1m": 0.40, "cache_read_per_1m": 0.10, "output_per_1m": 1.60},
    "gpt-4.1":      {"input_per_1m": 2.00, "cache_read_per_1m": 0.50, "output_per_1m": 8.00},
    "gpt-5.1":      {"input_per_1m": 1.25, "cache_read_per_1m": 0.13, "output_per_1m": 10.00},
    "gpt-5-mini":   {"input_per_1m": 0.25, "cache_read_per_1m": 0.03, "output_per_1m": 2.00},
    # Fallback — conservative estimate (no cache discount assumed)
    "default":      {"input_per_1m": 2.00, "cache_read_per_1m": 2.00, "output_per_1m": 8.00},
}

# Tool subsets per sub-agent (by tool name).
# Static data tools (get_portfolio_positions, get_portfolio_concentration,
# get_user_profile, get_watchlist) are no longer tools — data is pre-fetched
# and injected into each agent's system prompt via the builder functions.
_PORTFOLIO_REVIEW_TOOLS = {
    "web_search",
    "update_thesis_status",
}
_MACRO_SCAN_TOOLS = {
    "web_search",
    "save_macro_context",
}
_RESEARCH_TOOLS = {
    "get_stock_fundamentals",
    "web_search",
    "add_to_watchlist",
}
# Tools used by the main orchestrator to handle step 4 directly
_ORCHESTRATOR_TOOLS = {
    "save_final_report",
    "save_investment_suggestions",
}


class InvestmentWorkflowV2:
    """Runs the monthly investment workflow using DeepAgents.

    Each workflow run:
    1. Creates an InvestmentReport DB record (status=in_progress)
    2. Builds LangChain tools with user_id/report_id closed over
    3. Instantiates 3 sub-agents and the main orchestrator via create_deep_agent
    4. The main orchestrator handles step 4 (decision & thesis) directly
    5. Streams events as SSE-formatted strings
    6. Marks the report completed and cleans up temp workspace
    """

    WORKSPACE_BASE = "static/agent_workspace"

    def __init__(self, user_id: str, budget_eur: float):
        self.user_id = user_id
        self.budget_eur = budget_eur
        self.session_id = str(uuid4())
        self.report_id = str(uuid4())
        self.workspace_dir = f"{self.WORKSPACE_BASE}/{self.session_id}"
        # Accumulated token counts across all agents in this run
        self._tokens_input: int = 0   # total input tokens (fresh + cached)
        self._tokens_cached: int = 0  # subset served from prompt cache
        self._tokens_output: int = 0
        # Step timing / progress tracking
        self._step4_started: bool = False
        self._step_start_times: dict[str, float] = {}  # step_name → monotonic time

    # ------------------------------------------------------------------
    # Setup / teardown
    # ------------------------------------------------------------------

    def _ensure_workspace(self) -> None:
        os.makedirs(self.workspace_dir, exist_ok=True)

    def _cleanup_workspace(self) -> None:
        if os.path.exists(self.workspace_dir):
            shutil.rmtree(self.workspace_dir, ignore_errors=True)

    def _create_report_record(self) -> None:
        """Insert a new InvestmentReport row for this workflow run."""
        report_date = datetime.now(timezone.utc).date()
        db = SessionLocal()
        try:
            db.add(
                InvestmentReport(
                    id=self.report_id,
                    user_id=self.user_id,
                    report_date=report_date,
                    status="in_progress",
                )
            )
            db.commit()
            logger.info("[%s] Report record created (user=%s, date=%s)", self.report_id, self.user_id, report_date)
        finally:
            db.close()

    def _mark_report_complete(
        self, tokens_input: int, tokens_cached: int, tokens_output: int, cost_usd: float
    ) -> str:
        """Mark the report as completed, save token/cost data, and return the final_recommendation text."""
        db = SessionLocal()
        try:
            report = (
                db.query(InvestmentReport)
                .filter(InvestmentReport.id == self.report_id)
                .first()
            )
            final_text = ""
            if report:
                report.status = "completed"
                report.completed_at = datetime.utcnow()
                report.tokens_input = tokens_input
                report.tokens_cached = tokens_cached
                report.tokens_output = tokens_output
                report.cost_usd = round(cost_usd, 6)
                report.model_used = _MODEL_NAME
                db.commit()
                final_text = report.final_recommendation or ""
                logger.info(
                    "[%s] Report marked completed — tokens_in=%d (cached=%d), tokens_out=%d, cost=$%.4f",
                    self.report_id, tokens_input, tokens_cached, tokens_output, cost_usd,
                )
            return final_text
        finally:
            db.close()

    def _mark_report_failed(self, error: str) -> None:
        db = SessionLocal()
        try:
            report = (
                db.query(InvestmentReport)
                .filter(InvestmentReport.id == self.report_id)
                .first()
            )
            if report:
                report.status = "failed"
                report.completed_at = datetime.utcnow()
                db.commit()
                logger.error("[%s] Report marked failed: %s", self.report_id, error)
        finally:
            db.close()

    # ------------------------------------------------------------------
    # Agent construction
    # ------------------------------------------------------------------

    def _build_agent(self, all_tools: list, context: dict, today_date: str):
        """Build the main orchestrator with 3 inline sub-agents.

        Pre-fetched data from `context` is injected into each sub-agent's
        system prompt so they don't need to call read-only DB tools at runtime.

        Args:
            all_tools: Full list of runtime tools from build_tools().
            context: Dict returned by prefetch_agent_context() with keys:
                portfolio_positions, portfolio_concentration, user_profile, watchlist.
            today_date: ISO date string (YYYY-MM-DD) injected into every agent's context.
        """
        print(f"Building agent with {len(all_tools)} tools for user {self.user_id} and report {self.report_id}")
        portfolio_tools = filter_tools(all_tools, _PORTFOLIO_REVIEW_TOOLS)
        macro_tools = filter_tools(all_tools, _MACRO_SCAN_TOOLS)
        research_tools = filter_tools(all_tools, _RESEARCH_TOOLS)
        orchestrator_tools = filter_tools(all_tools, _ORCHESTRATOR_TOOLS)

        positions_json = json.dumps(context["portfolio_positions"], ensure_ascii=False, indent=2)
        concentration_json = json.dumps(context["portfolio_concentration"], ensure_ascii=False, indent=2)
        profile_json = json.dumps(context["user_profile"], ensure_ascii=False, indent=2)
        watchlist_json = json.dumps(context["watchlist"], ensure_ascii=False, indent=2)

        model = ChatOpenAI(
            model=_MODEL_NAME,
            api_key=settings.openai_investment_key,
        )

        subagents: list[SubAgent] = [
            SubAgent(
                name="portfolio_review_agent",
                description=(
                    "Performs the monthly review of the existing portfolio. "
                    "Evaluates the validity of each investment thesis, detects significant price movements, "
                    "checks concentration. Saves thesis statuses to the database."
                ),
                system_prompt=build_portfolio_review_prompt(positions_json, concentration_json, today_date),
                tools=portfolio_tools,
                model=model,
            ),
            SubAgent(
                name="macro_scan_agent",
                description=(
                    "Performs the monthly macro-economic and sector scan. "
                    "Researches market trends, identifies favored sectors, "
                    "applies ESG filters. Updates the user's macro investment log."
                ),
                system_prompt=build_macro_scan_prompt(profile_json, today_date),
                tools=macro_tools,
                model=model,
            ),
            SubAgent(
                name="opportunity_research_agent",
                description=(
                    "Researches the best investment opportunity of the month. "
                    "Builds a shortlist of 3-5 candidates from the watchlist and macro themes, "
                    "performs quick fundamental analysis, checks PEA/CTO eligibility, "
                    "and selects the final recommendation (one, or two if budget and conviction both allow)."
                ),
                system_prompt=build_opportunity_research_prompt(
                    positions_json, watchlist_json, profile_json, today_date, self.budget_eur
                ),
                tools=research_tools,
                model=model,
            ),
        ]

        return create_deep_agent(
            model=model,
            tools=orchestrator_tools,
            system_prompt=MAIN_ORCHESTRATOR_PROMPT,
            subagents=subagents,
        )

    # ------------------------------------------------------------------
    # SSE event conversion
    # ------------------------------------------------------------------

    @staticmethod
    def _make_sse(event_type: str, data: dict) -> str:
        return f"data: {json.dumps({'type': event_type, **data}, ensure_ascii=False)}\n\n"

    @staticmethod
    def _extract_task_result(output: Any) -> str | None:
        """Extract the sub-agent's result text from a LangGraph Command or message output.

        DeepAgents returns a Command(update={"messages": [ToolMessage(text)]}).
        We pull the final message's content to surface the agent's written report.
        """
        if output is None:
            return None
        # LangGraph Command — result is in update["messages"][-1]
        update = getattr(output, "update", None)
        if isinstance(update, dict):
            messages = update.get("messages", [])
            if messages:
                content = getattr(messages[-1], "content", "")
                if isinstance(content, str):
                    return content.strip() or None
                if isinstance(content, list):
                    text = "".join(
                        block.get("text", "") if isinstance(block, dict) else str(block)
                        for block in content
                    )
                    return text.strip() or None
        # Plain string output
        if isinstance(output, str):
            return output.strip() or None
        # Any other message-like object
        content = getattr(output, "content", None)
        if content is not None:
            return str(content).strip() or None
        return None

    def _event_to_sse(self, event: dict) -> str | None:
        """Convert a LangChain astream_events v2 event to an SSE string.

        DeepAgents exposes sub-agents via a single 'task' StructuredTool.
        When the orchestrator calls task(subagent_type="portfolio_review_agent"),
        LangChain fires on_tool_start with name="task" — not the sub-agent name.
        We therefore resolve the effective agent name from inputs["subagent_type"].

        Sub-agents run via ainvoke (not astream_events), so token events only
        come from the main orchestrator (step 4).
        """
        kind = event.get("event", "")
        name = event.get("name", "")

        _step_names = {
            "portfolio_review_agent": "Step 1 — Portfolio Review",
            "macro_scan_agent": "Step 2 — Macro & Sector Scan",
            "opportunity_research_agent": "Step 3 — Opportunity Research",
        }
        _step_numbers = {
            "portfolio_review_agent": 1,
            "macro_scan_agent": 2,
            "opportunity_research_agent": 3,
        }

        if kind == "on_chat_model_start":
            model = event.get("metadata", {}).get("ls_model_name") or name
            run_id = str(event.get("run_id", ""))[:8]
            logger.info("[%s] LLM call started: model=%s run_id=%s", self.report_id, model, run_id)
            return None

        if kind == "on_chat_model_stream":
            chunk = event.get("data", {}).get("chunk")
            if chunk and hasattr(chunk, "content"):
                content = chunk.content
                if isinstance(content, str) and content:
                    return self._make_sse("token", {"content": content, "agent": name})
                elif isinstance(content, list):
                    # Some models return list of content blocks
                    text = "".join(
                        block.get("text", "") for block in content
                        if isinstance(block, dict) and block.get("type") == "text"
                    )
                    if text:
                        return self._make_sse("token", {"content": text, "agent": name})

        elif kind == "on_tool_start":
            inputs = event.get("data", {}).get("input", {})
            # DeepAgents routes sub-agents through the 'task' tool; resolve agent name
            agent_name = inputs.get("subagent_type", name) if name == "task" else name

            if agent_name in _step_names:
                self._step_start_times[agent_name] = time.monotonic()
                logger.info("[%s] Step start: %s", self.report_id, _step_names[agent_name])
                return self._make_sse("step_start", {
                    "step": _step_numbers[agent_name],
                    "step_name": _step_names[agent_name],
                })
            elif name != "task":
                # Base tool call (web_search, save_final_report, etc.).
                # Skip the 'task' tool itself — handled above.
                first_input = next(iter(inputs.values()), None) if isinstance(inputs, dict) else None
                if name in ("save_final_report", "save_investment_suggestions"):
                    logger.info("[%s] [step4] Tool call: %s", self.report_id, name)
                else:
                    logger.info("[%s] Tool call: %s(%s)", self.report_id, name,
                                str(first_input)[:120] if first_input else "")
                return self._make_sse("tool_call", {
                    "tool": name,
                    "inputs": {k: str(v)[:100] for k, v in inputs.items()} if isinstance(inputs, dict) else {},
                })

        elif kind == "on_tool_end":
            inputs = event.get("data", {}).get("input", {})
            # astream_events v2 includes input in on_tool_end; resolve agent name same way
            agent_name = inputs.get("subagent_type", name) if name == "task" else name

            if agent_name in _step_numbers:
                elapsed = time.monotonic() - self._step_start_times.get(agent_name, time.monotonic())
                logger.info("[%s] Step complete: %s (elapsed=%.1fs)", self.report_id, _step_names[agent_name], elapsed)
                result_text = self._extract_task_result(event.get("data", {}).get("output"))
                payload: dict = {
                    "step": _step_numbers[agent_name],
                    "step_name": _step_names[agent_name],
                }
                if result_text:
                    payload["result"] = result_text
                return self._make_sse("step_complete", payload)

            elif name == "save_final_report":
                markdown_report = inputs.get("markdown_report", "")
                if markdown_report:
                    logger.info("[%s] Final report ready (%d chars)", self.report_id, len(markdown_report))
                    return self._make_sse("final_report", {"content": markdown_report})

            elif name == "save_investment_suggestions":
                suggestions_json_str = inputs.get("suggestions_json", "[]")
                elapsed4 = time.monotonic() - self._step_start_times.get("step4", time.monotonic())
                try:
                    suggestions = json.loads(suggestions_json_str)
                    logger.info(
                        "[%s] [step4] Investment suggestions ready: %d items (step4 elapsed=%.1fs)",
                        self.report_id, len(suggestions), elapsed4,
                    )
                    return self._make_sse("investment_suggestions", {"suggestions": suggestions})
                except (json.JSONDecodeError, Exception) as e:
                    logger.warning("[%s] Failed to parse investment suggestions: %s", self.report_id, e)

        return None

    # ------------------------------------------------------------------
    # Main entry point
    # ------------------------------------------------------------------

    async def stream(self) -> AsyncGenerator[str, None]:
        """Run the workflow and yield SSE-formatted strings.

        Yields:
            str: SSE-formatted event strings (e.g. "data: {...}\\n\\n")

        Event types emitted:
        - "workflow_start": workflow begins, includes report_id
        - "step_start": a sub-agent step begins (step 1-3)
        - "tool_call": a base tool is called (web_search, yfinance, etc.)
        - "token": streaming token from any agent LLM call
        - "step_complete": a sub-agent step finishes
        - "workflow_complete": workflow done, report saved to DB
        - "error": unrecoverable error
        """
        logger.info(
            "[%s] Workflow starting — user=%s, budget=%.2f EUR, session=%s",
            self.report_id, self.user_id, self.budget_eur, self.session_id,
        )
        self._ensure_workspace()
        self._create_report_record()

        yield self._make_sse("workflow_start", {
            "report_id": self.report_id,
            "message": "Starting monthly investment analysis...",
        })

        try:
            logger.debug("[%s] Pre-fetching user context from DB", self.report_id)
            context = prefetch_agent_context(
                db_session_factory=SessionLocal,
                user_id=self.user_id,
            )
            logger.info(
                "[%s] Context loaded — %d positions, %d watchlist items",
                self.report_id,
                len(context["portfolio_positions"]),
                len(context["watchlist"]),
            )

            today_date = datetime.now(timezone.utc).date().isoformat()

            logger.debug("[%s] Building tools and agent", self.report_id)
            all_tools = build_tools(
                db_session_factory=SessionLocal,
                user_id=self.user_id,
                report_id=self.report_id,
                tavily_api_key=settings.tavily_api_key,
            )
            agent = self._build_agent(all_tools, context, today_date)
            logger.debug("[%s] Agent constructed, starting astream_events", self.report_id)

            initial_message = HumanMessage(
                content=(
                    f"Today's date is {today_date}. "
                    f"Run a complete investment analysis workflow. "
                    f"The user's available budget for this run is {self.budget_eur} EUR — "
                    f"use this value throughout the analysis. The budget may be split across "
                    f"up to two recommendations if two genuinely compelling opportunities exist, "
                    f"but one focused recommendation is the default. "
                    f"Execute the 3 sub-agent steps in order (portfolio review, macro scan, "
                    f"opportunity research), then handle step 4 (decision & thesis) yourself."
                )
            )

            final_output = ""
            event_count = 0
            workflow_start = time.monotonic()
            logger.info("[%s] Starting astream_events (recursion_limit=%d)", self.report_id, settings.agent_recursion_limit)
            async for event in agent.astream_events(
                {"messages": [initial_message]},
                version="v2",
                config={"recursion_limit": settings.agent_recursion_limit}
            ):
                event_count += 1
                sse = self._event_to_sse(event)
                if sse:
                    yield sse

                # Detect step 3 completion → emit step 4 start
                if not self._step4_started:
                    ev_kind = event.get("event", "")
                    ev_name = event.get("name", "")
                    if ev_kind == "on_tool_end" and ev_name == "task":
                        inputs = event.get("data", {}).get("input", {})
                        if inputs.get("subagent_type") == "opportunity_research_agent":
                            self._step4_started = True
                            self._step_start_times["step4"] = time.monotonic()
                            elapsed = self._step_start_times["step4"] - workflow_start
                            logger.info(
                                "[%s] Step 4 starting — Decision & Thesis Documentation (workflow elapsed=%.1fs)",
                                self.report_id, elapsed,
                            )
                            yield self._make_sse("step_start", {
                                "step": 4,
                                "step_name": "Step 4 — Decision & Thesis",
                            })

                # Periodic heartbeat: log every 100 events so we know the loop is alive
                if event_count % 100 == 0:
                    elapsed = time.monotonic() - workflow_start
                    logger.info(
                        "[%s] Workflow heartbeat — %d events, elapsed=%.1fs",
                        self.report_id, event_count, elapsed,
                    )

                # Capture the final AI message for the report + accumulate token usage
                if event.get("event") == "on_chat_model_end":
                    output = event.get("data", {}).get("output")
                    if output is not None:
                        if hasattr(output, "content") and isinstance(output.content, str):
                            final_output = output.content
                        # Accumulate token counts from all LLM calls (orchestrator + sub-agents).
                        # usage_metadata fields (LangChain ≥ 0.3.9):
                        #   input_tokens            — total input tokens (fresh + cached)
                        #   output_tokens           — generated tokens
                        #   input_token_details     — dict with optional 'cache_read' key
                        usage = getattr(output, "usage_metadata", None)
                        if usage:
                            self._tokens_input += usage.get("input_tokens", 0)
                            self._tokens_output += usage.get("output_tokens", 0)
                            details = usage.get("input_token_details") or {}
                            self._tokens_cached += details.get("cache_read", 0)

            logger.info(
                "[%s] astream_events finished — %d events, final_output=%d chars, tokens_in=%d, tokens_out=%d",
                self.report_id, event_count, len(final_output),
                self._tokens_input, self._tokens_output,
            )

            # Save final report text to DB
            if final_output:
                db = SessionLocal()
                try:
                    report = (
                        db.query(InvestmentReport)
                        .filter(InvestmentReport.id == self.report_id)
                        .first()
                    )
                    if report:
                        report.final_recommendation = final_output
                        db.commit()
                finally:
                    db.close()

            # Compute cost and persist.
            # Fresh input = total input − cached (cached tokens billed at discount rate).
            pricing = _MODEL_PRICING.get(_MODEL_NAME, _MODEL_PRICING["default"])
            fresh_input = self._tokens_input - self._tokens_cached
            cost_usd = (
                fresh_input * pricing["input_per_1m"] / 1_000_000
                + self._tokens_cached * pricing["cache_read_per_1m"] / 1_000_000
                + self._tokens_output * pricing["output_per_1m"] / 1_000_000
            )
            self._mark_report_complete(
                self._tokens_input, self._tokens_cached, self._tokens_output, cost_usd
            )
            logger.info("[%s] Workflow complete — emitting workflow_complete event", self.report_id)
            yield self._make_sse("workflow_complete", {
                "report_id": self.report_id,
                "message": "Monthly analysis complete. Report saved.",
                "tokens_input": self._tokens_input,
                "tokens_cached": self._tokens_cached,
                "tokens_output": self._tokens_output,
                "cost_usd": round(cost_usd, 6),
                "model": _MODEL_NAME,
            })

        except Exception as e:
            logger.exception("[%s] Workflow failed with unhandled exception: %s", self.report_id, e)
            self._mark_report_failed(str(e))
            yield self._make_sse("error", {"message": str(e)})

        finally:
            logger.debug("[%s] Cleaning up workspace: %s", self.report_id, self.workspace_dir)
            self._cleanup_workspace()
