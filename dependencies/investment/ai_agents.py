"""AI-powered investment recommendation workflow."""
from typing import AsyncGenerator
from openai import OpenAI
import json

from config import settings
from models.investment import PortfolioMetrics
from domain.entities.investment import Investment


class AgentEvent:
    """Represents a streaming event from the AI agents."""
    def __init__(self, event_type: str, data: dict):
        self.event_type = event_type
        self.data = data

    def to_sse(self) -> str:
        """Convert to Server-Sent Events format."""
        return f"data: {json.dumps({'type': self.event_type, **self.data})}\n\n"


class InvestmentResearchWorkflow:
    """
    Controlled multi-step workflow for investment research.
    Each step is a separate API call for predictable behavior.
    """

    def __init__(self, user_portfolio: list[Investment], portfolio_metrics: PortfolioMetrics):
        self.client = OpenAI(api_key=settings.openai_investment_key)
        self.model = "gpt-4.1"
        self.user_portfolio = user_portfolio
        self.portfolio_metrics = portfolio_metrics
        self.user_context = self._build_user_context()

    def _build_user_context(self) -> str:
        """Build the user context string."""
        portfolio_summary = []
        for inv in self.user_portfolio:
            portfolio_summary.append(
                f"- {inv.vehicle.name} ({inv.vehicle.symbol}): "
                f"{inv.vehicle.sector or 'N/A'} sector, {inv.vehicle.country} region"
            )

        return f"""## USER PROFILE
- Name: Kelly, 28 years old, AI engineer in Lyon, France
- Risk tolerance: Moderate
- Investment horizon: Medium to long term
- Budget this month: 50 EUR
- Interests: Technology, sustainable/ESG investments, can eventually invest in other sectors to

## ETHICAL EXCLUSIONS (MUST AVOID)
- Fossil fuels (oil, gas, coal companies)
- Military, defense, weapons manufacturers
- Tobacco, gambling
- Any company with poor environmental or social practices

## CURRENT PORTFOLIO ({len(self.user_portfolio)} holdings)
{chr(10).join(portfolio_summary) if portfolio_summary else "Empty portfolio - first investment!"}

## DIVERSIFICATION METRICS
- Breakdown by country: {', '.join(f'{k}: {round(v.percentage, 2)}%' for k, v in self.portfolio_metrics.breakdown_by_country.items())}
- Breakdown by sector: {', '.join(f'{k}: {round(v.percentage, 2)}%' for k, v in self.portfolio_metrics.breakdown_by_sector.items())}
- Breakdown by asset type: {', '.join(f'{k}: {round(v.percentage, 2)}%' for k, v in self.portfolio_metrics.breakdown_by_asset_type.items())}
"""

    def _call_with_web_search(self, prompt: str) -> tuple[str, list[dict]]:
        """Make an API call with web search tool enabled."""
        response = self.client.responses.create(
            model=self.model,
            tools=[{"type": "web_search_preview"}],
            input=prompt,
        )

        searches = []
        for item in response.output:
            if item.type == "web_search_call":
                searches.append({"query": getattr(item, "query", "")})

        text_output = ""
        for item in response.output:
            if item.type == "message":
                for content in item.content:
                    if content.type == "output_text":
                        text_output = content.text
                        break

        return text_output, searches

    def _call_without_tools(self, prompt: str) -> str:
        """Make an API call without tools (pure reasoning)."""
        response = self.client.responses.create(
            model=self.model,
            input=prompt,
        )

        for item in response.output:
            if item.type == "message":
                for content in item.content:
                    if content.type == "output_text":
                        return content.text
        return ""

    def step1_market_discovery(self) -> tuple[str, list[dict]]:
        """Step 1: Broad market research without user bias."""
        prompt = """You are a financial research specialist. Your task is to research current market trends.

Search for information about:
1. Current stock market trends and what's performing well
2. Best performing sectors right now
3. Popular ETFs and fund flows
4. Emerging investment opportunities

Perform multiple web searches to gather comprehensive market intelligence.

After your research, provide a summary of:
- Overall market sentiment
- Top performing sectors
- Notable stocks and ETFs that are trending
- Any emerging opportunities worth investigating

Be specific with names and ticker symbols when possible."""

        return self._call_with_web_search(prompt)

    def step2_build_candidates(self, market_research: str) -> str:
        """Step 2: Build initial candidate list from research."""
        prompt = f"""Based on the following market research, identify 5-6 specific investment opportunities.

## MARKET RESEARCH
{market_research}

For each candidate, provide:
1. Full name
2. Ticker symbol (if available)
3. Sector/Industry
4. Why it's interesting (based on the research)
5. Approximate price range if mentioned
6. Risk if any explicitly mentioned in the research

Format as a numbered list. Focus on concrete, investable assets (stocks, ETFs, funds)."""

        return self._call_without_tools(prompt)

    def step3_filter_and_rank(self, candidates: str) -> str:
        """Step 3: Filter by ethics and rank by portfolio fit."""
        prompt = f"""Review these investment candidates: apply ethical filtering and rank by portfolio fit.

## USER CONTEXT
{self.user_context}

## CANDIDATES
{candidates}

## TASK 1: ETHICAL SCREENING
Remove any candidate related to:
- Fossil fuels (oil, gas, coal companies)
- Military, defense, weapons manufacturers
- Tobacco, gambling
- Companies with poor environmental or social practices

For each candidate, briefly state PASS or FAIL with reason if failing.

## TASK 2: PORTFOLIO FIT RANKING
For candidates that pass ethical screening, evaluate:
1. Geographic diversification (adds exposure to underrepresented regions?)
2. Sector diversification (complements existing holdings?)
3. Risk alignment (moderate risk tolerance)
4. Budget fit (user has 50 EUR to invest)

## OUTPUT
Provide the top 3-4 candidates ranked by portfolio fit, with a brief justification for each."""

        return self._call_without_tools(prompt)

    def step4_deep_research(self, top_candidates: str) -> tuple[str, list[dict]]:
        """Step 4: Deep dive research on top candidates."""
        prompt = f"""Research detailed information about these top investment candidates.

## TOP CANDIDATES TO RESEARCH
{top_candidates}

For each candidate, search for:
- Current price
- Recent performance (YTD, 1-year)
- Analyst ratings or recommendations
- Key risks
- For ETFs: expense ratio

Provide concrete data points for each. Be specific with numbers and dates."""

        return self._call_with_web_search(prompt)

    def step5_final_recommendation(self, deep_research: str) -> str:
        """Step 5: Generate final recommendations."""
        prompt = f"""Generate final investment recommendations based on your research.

## USER CONTEXT
{self.user_context}

## DETAILED RESEARCH
{deep_research}

Select the TOP 2 investments and present them in this format:

## Market Context
(2-3 sentences on current trends relevant to the recommendations)

## Recommendation 1: [Name] ([Ticker])
- **Price**: X€ | **Sector**: Y | **Geography**: Z
- **Why it fits**: Explain why this is good for this specific user
- **Risk**: Key risk to be aware of

## Recommendation 2: [Name] ([Ticker])
- **Price**: X€ | **Sector**: Y | **Geography**: Z
- **Why it fits**: Explain why this is good for this specific user
- **Risk**: Key risk to be aware of

## Suggested Allocation
How to split the 50€ budget between the two recommendations.

Be concise but precise. Include ticker symbols and current prices."""

        return self._call_without_tools(prompt)


async def launch_agents_stream(
    user_portfolio: list[Investment],
    portfolio_metrics: PortfolioMetrics,
) -> AsyncGenerator[AgentEvent, None]:
    """
    Launch the investment research workflow and yield streaming events.
    """
    workflow = InvestmentResearchWorkflow(user_portfolio, portfolio_metrics)

    # Step 1: Market Discovery
    yield AgentEvent("step_start", {"step": 1, "name": "Market Discovery"})
    market_research, searches = workflow.step1_market_discovery()
    for search in searches:
        yield AgentEvent("tool_call", {"tool_name": "web_search", "arguments": json.dumps(search)})
    yield AgentEvent("step_complete", {"step": 1, "summary": market_research})

    # Step 2: Build Candidates
    yield AgentEvent("step_start", {"step": 2, "name": "Building Candidate List"})
    candidates = workflow.step2_build_candidates(market_research)
    yield AgentEvent("step_complete", {"step": 2, "summary": candidates})

    # Step 3: Filter & Rank
    yield AgentEvent("step_start", {"step": 3, "name": "Ethical Screening & Portfolio Fit"})
    top_candidates = workflow.step3_filter_and_rank(candidates)
    yield AgentEvent("step_complete", {"step": 3, "summary": top_candidates})

    # Step 4: Deep Research
    yield AgentEvent("step_start", {"step": 4, "name": "Deep Dive Research"})
    deep_research, searches = workflow.step4_deep_research(top_candidates)
    for search in searches:
        yield AgentEvent("tool_call", {"tool_name": "web_search", "arguments": json.dumps(search)})
    yield AgentEvent("step_complete", {"step": 4, "summary": deep_research})

    # Step 5: Final Recommendation
    yield AgentEvent("step_start", {"step": 5, "name": "Generating Recommendations"})
    recommendation = workflow.step5_final_recommendation(deep_research)
    yield AgentEvent("step_complete", {"step": 5, "summary": "Recommendations ready"})

    yield AgentEvent("final_output", {"recommendation": recommendation})
