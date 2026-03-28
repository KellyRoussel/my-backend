"""Portfolio chatbot agent — single DeepAgent with gitmcp.io MCP tools.

Architecture:
- Single DeepAgent (no sub-agents — this is a conversational chatbot, not a pipeline)
- GitHub repos accessed via gitmcp.io MCP endpoints through langchain-mcp-adapters
- Medium articles accessed via two standard LangChain tools (RSS + page fetch)
- Conversation history passed as LangChain messages on every request (stateless agent)
- Streams SSE events: session → tokens → done
- Agent is cached at module level and rebuilt every 10 minutes (MCP session TTL)
"""
import asyncio
import json
import logging
import time
from typing import AsyncGenerator

from deepagents import create_deep_agent
from langchain_core.messages import AIMessage, HumanMessage
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_mcp_adapters.client import MultiServerMCPClient
from pydantic import create_model

from config import settings
from dependencies.portfolio.agent_prompts import PORTFOLIO_AGENT_SYSTEM_PROMPT
from dependencies.portfolio.agent_tools import build_tools

logger = logging.getLogger(__name__)

_AGENT_CACHE_TTL = 600  # seconds — rebuild agent + MCP tools every 10 minutes

_agent_cache: dict = {"agent": None, "built_at": 0.0}
_agent_lock = asyncio.Lock()


def _patch_empty_schema_tools(tools: list) -> list:
    """OpenAI rejects tool schemas that have no `properties` field.
    MCP tools with zero parameters produce ``{"type": "object"}`` — patch them
    to ``{"type": "object", "properties": {}}`` via an empty Pydantic model.
    """
    for tool in tools:
        if not hasattr(tool, "args_schema") or tool.args_schema is None:
            continue
        schema = tool.args_schema
        if isinstance(schema, dict):
            if "properties" not in schema:
                schema["properties"] = {}
        else:
            if "properties" not in schema.model_json_schema():
                tool.args_schema = create_model(f"{tool.name}_schema")
    return tools

# gitmcp.io endpoint for each of Kelly's public repos.
# Each entry becomes one MCP server connection during a chat request.
_GITMCP_SERVERS: dict[str, dict] = {
    "my_home_assistant": {
        "url": "https://gitmcp.io/KellyRoussel/my_home_assistant",
        "transport": "streamable_http",
    },
    "insta_poster": {
        "url": "https://gitmcp.io/KellyRoussel/insta_poster",
        "transport": "streamable_http",
    },
    "bobobidou": {
        "url": "https://gitmcp.io/KellyRoussel/Bobobidou",
        "transport": "streamable_http",
    },
    "investment_agent": {
        "url": "https://gitmcp.io/KellyRoussel/investment_agent",
        "transport": "streamable_http",
    },
    "my_backend": {
        "url": "https://gitmcp.io/KellyRoussel/my-backend",
        "transport": "streamable_http",
    },
}


async def _build_portfolio_agent():
    """Instantiate a fresh agent — no cache, no lock."""
    t0 = time.perf_counter()

    mcp_client = MultiServerMCPClient(_GITMCP_SERVERS)
    mcp_tools = _patch_empty_schema_tools(await mcp_client.get_tools())
    logger.info("[portfolio] MCP tools loaded (%d tools) in %.2fs", len(mcp_tools), time.perf_counter() - t0)

    all_tools = mcp_tools + build_tools()

    t2 = time.perf_counter()
    model = ChatGoogleGenerativeAI(
        model="gemini-2.5-flash",
        google_api_key=settings.gemini_api_key,
        streaming=True,
    )
    logger.info("[portfolio] ChatGoogleGenerativeAI init in %.2fs", time.perf_counter() - t2)

    t3 = time.perf_counter()
    agent = create_deep_agent(
        model=model,
        tools=all_tools,
        system_prompt=PORTFOLIO_AGENT_SYSTEM_PROMPT,
        subagents=[],
    )
    logger.info("[portfolio] create_deep_agent in %.2fs", time.perf_counter() - t3)
    logger.info("[portfolio] Agent ready — total build time: %.2fs", time.perf_counter() - t0)
    return agent


async def get_or_build_portfolio_agent():
    """Return a cached agent, rebuilding if the cache is empty or expired."""
    async with _agent_lock:
        age = time.time() - _agent_cache["built_at"]
        if _agent_cache["agent"] is not None and age < _AGENT_CACHE_TTL:
            logger.info("[portfolio] Using cached agent (age: %.0fs)", age)
            return _agent_cache["agent"]

        logger.info("[portfolio] Building agent (cache miss)...")
        agent = await _build_portfolio_agent()
        _agent_cache["agent"] = agent
        _agent_cache["built_at"] = time.time()
        return agent


class PortfolioAgent:
    """Streams a single conversational response for the portfolio chatbot."""

    def __init__(self, session_id: str):
        self.session_id = session_id

    @staticmethod
    def _make_sse(event_type: str, data: dict) -> str:
        return f"data: {json.dumps({'type': event_type, **data}, ensure_ascii=False)}\n\n"

    async def stream(
        self,
        history: list[dict],
        user_message: str,
        session_id: str,
    ) -> AsyncGenerator[str, None]:
        """Stream the agent response as SSE strings.

        Yields:
            str: SSE-formatted strings — session event first, then token events, then done.

        Args:
            history: Previous turns as [{"role": "user"|"assistant", "content": str}]
            user_message: The new user message to respond to
            session_id: The visitor's session UUID (emitted in the session event)
        """
        # Emit session event first so the frontend can persist the session ID
        yield self._make_sse("session", {"session_id": session_id})

        try:
            t0 = time.perf_counter()
            agent = await get_or_build_portfolio_agent()
            logger.info("[portfolio][%s] Agent ready in %.2fs", self.session_id[:8], time.perf_counter() - t0)

            # Build the message list from conversation history
            messages = []
            for turn in history:
                if turn.get("role") == "user":
                    messages.append(HumanMessage(content=turn["content"]))
                elif turn.get("role") == "assistant":
                    messages.append(AIMessage(content=turn["content"]))
            messages.append(HumanMessage(content=user_message))

            t1 = time.perf_counter()
            first_token = True
            async for event in agent.astream_events(
                {"messages": messages},
                version="v2",
                config={"recursion_limit": 20},
            ):
                if event.get("event") == "on_chat_model_stream":
                    chunk = event.get("data", {}).get("chunk")
                    if chunk and hasattr(chunk, "content"):
                        content = chunk.content
                        if isinstance(content, str) and content:
                            if first_token:
                                logger.info("[portfolio][%s] First token in %.2fs", self.session_id[:8], time.perf_counter() - t1)
                                first_token = False
                            yield self._make_sse("token", {"content": content})
                        elif isinstance(content, list):
                            text = "".join(
                                block.get("text", "")
                                for block in content
                                if isinstance(block, dict) and block.get("type") == "text"
                            )
                            if text:
                                if first_token:
                                    logger.info("[portfolio][%s] First token in %.2fs", self.session_id[:8], time.perf_counter() - t1)
                                    first_token = False
                                yield self._make_sse("token", {"content": text})

                elif event.get("event") == "on_tool_start":
                    tool_name = event.get("name", "")
                    logger.info("[portfolio][%s] Tool call: %s", self.session_id[:8], tool_name)

        except Exception as e:
            logger.error("[portfolio][%s] Agent error: %s", self.session_id[:8], e)
            _agent_cache["agent"] = None  # invalidate cache on error
            yield self._make_sse("error", {"message": "Something went wrong. Please try again."})
            return

        yield self._make_sse("done", {})
