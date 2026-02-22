"""LangChain tools factory for the DeepAgents investment workflow v2.

All tools are built via a factory function that closes over user_id, report_id,
and other session-specific values. This pattern ensures thread-safety for concurrent
workflow executions and avoids global state.

Tools are synchronous — LangChain automatically runs them in a thread executor
when invoked from an async agent context.

Static data (portfolio positions, concentration, user profile, watchlist) is
pre-fetched via prefetch_agent_context() before agents start, then injected into
their system prompts — this avoids redundant tool calls at runtime.
"""
import json
from datetime import date, datetime
from decimal import Decimal
from typing import Optional
from uuid import uuid4

import yfinance as yf
from langchain_core.tools import tool
from tavily import TavilyClient

from dependencies.investment.portfolio_calculator import PortfolioCalculator
from dependencies.investment.yahoo_finance import YahooFinanceClient
from models.database_models import (
    Investment as DBInvestment,
    InvestmentReport,
    InvestmentProfile,
    InvestmentWatchlist,
)

# Countries whose stocks are eligible for the French PEA tax wrapper
_PEA_ELIGIBLE_COUNTRIES = {
    "FRA", "DEU", "NLD", "BEL", "ESP", "ITA", "PRT", "IRL",
    "FIN", "SWE", "NOR", "DNK", "AUT", "LUX", "CHE", "POL",
    "CZE", "HUN", "ROU", "SVK", "SVN", "HRV", "BGR", "GRC",
    "CYP", "MLT", "EST", "LVA", "LTU", "ISL", "LIE",
}


def prefetch_agent_context(db_session_factory, user_id: str) -> dict:
    """Fetch static user data from the DB before agents start.

    Opens a single short-lived DB session and returns a dict with:
    - portfolio_positions: list of active position dicts (incl. price_change_pct,
      current_price, significant_move pre-computed via yfinance)
    - portfolio_concentration: concentration metrics dict
    - user_profile: profile dict (risk_tolerance, exclusions, horizon, macro_context)
    - watchlist: list of active watchlist item dicts
    """
    db = db_session_factory()
    try:
        # --- Portfolio positions ---
        investments = (
            db.query(DBInvestment)
            .filter(DBInvestment.user_id == user_id, DBInvestment.is_active == True)
            .all()
        )
        total_cost = sum(
            float(inv.purchase_price) * float(inv.quantity) for inv in investments
        )
        portfolio_positions = []
        for inv in investments:
            cost = float(inv.purchase_price) * float(inv.quantity)
            portfolio_positions.append({
                "id": inv.id,
                "symbol": inv.symbol,
                "name": inv.name,
                "sector": inv.sector,
                "country": inv.country,
                "asset_type": inv.asset_type.value if inv.asset_type else None,
                "account_type": inv.account_type,
                "quantity": float(inv.quantity),
                "purchase_price": float(inv.purchase_price),
                "purchase_date": inv.purchase_date.isoformat() if inv.purchase_date else None,
                "currency": inv.currency,
                "investment_thesis": inv.investment_thesis,
                "thesis_status": inv.thesis_status or "valid",
                "alert_threshold_pct": float(inv.alert_threshold_pct) if inv.alert_threshold_pct else None,
                "cost_weight_pct": round(cost / total_cost * 100, 2) if total_cost else 0,
                "notes": inv.notes,
                # Placeholders — filled in by the price-change loop below
                "price_change_pct": None,
                "current_price": None,
                "significant_move": False,
            })

        # --- Price changes since purchase date (yfinance, one call per position) ---
        for position in portfolio_positions:
            purchase_date = position["purchase_date"]
            if not purchase_date:
                continue
            try:
                hist = yf.Ticker(position["symbol"]).history(start=purchase_date)
                if not hist.empty:
                    price_on_date = float(hist["Close"].iloc[0])
                    current = float(hist["Close"].iloc[-1])
                    change_pct = round((current - price_on_date) / price_on_date * 100, 2) if price_on_date else 0
                    position["price_change_pct"] = change_pct
                    position["current_price"] = current
                    position["significant_move"] = abs(change_pct) >= 15
            except Exception:
                pass  # leave as None / False — agent will note the gap

        # --- User profile ---
        profile = (
            db.query(InvestmentProfile)
            .filter(InvestmentProfile.user_id == user_id)
            .first()
        )
        if not profile:
            raise ValueError(f"User profile not found for user_id {user_id}")
        else:
            user_profile = {
                "risk_tolerance": profile.risk_tolerance.value if profile.risk_tolerance else "moderate",
                "currency_preference": profile.currency_preference or "EUR",
                "investment_horizon": profile.investment_horizon or "medium_long_term",
                "ethical_exclusions": profile.ethical_exclusions or "defense, fossil fuels, tobacco, gambling",
                "country": profile.country,
                "interests": profile.interests,
                "last_macro_context": profile.last_macro_context,
            }

        # --- Watchlist ---
        watchlist_items = (
            db.query(InvestmentWatchlist)
            .filter(InvestmentWatchlist.user_id == user_id, InvestmentWatchlist.is_active == True)
            .all()
        )
        watchlist = [
            {
                "id": item.id,
                "symbol": item.symbol,
                "name": item.name,
                "sector": item.sector,
                "country": item.country,
                "reason": item.reason,
                "source": item.source,
                "priority": item.priority,
            }
            for item in watchlist_items
        ]

        # --- Portfolio concentration ---
        currency = user_profile["currency_preference"]
        calculator = PortfolioCalculator(db)
        metrics = calculator.calculate_portfolio_metrics(user_id, currency)
        portfolio_concentration = {
            "total_value": float(metrics.total_value),
            "total_cost": float(metrics.total_cost),
            "total_gain_loss_pct": float(metrics.total_gain_loss_percent),
            "investment_count": metrics.investment_count,
            "diversification_score": metrics.diversification_score,
            "breakdown_by_sector": {
                k: {"percentage": round(v.percentage, 2), "count": v.count}
                for k, v in metrics.breakdown_by_sector.items()
            },
            "breakdown_by_country": {
                k: {"percentage": round(v.percentage, 2), "count": v.count}
                for k, v in metrics.breakdown_by_country.items()
            },
            "breakdown_by_asset_type": {
                k: {"percentage": round(v.percentage, 2), "count": v.count}
                for k, v in metrics.breakdown_by_asset_type.items()
            },
            "top_performers": [
                {"symbol": p.symbol, "gain_loss_pct": float(p.gain_loss_percent)}
                for p in metrics.top_performers
            ],
            "worst_performers": [
                {"symbol": p.symbol, "gain_loss_pct": float(p.gain_loss_percent)}
                for p in metrics.worst_performers
            ],
        }

        return {
            "portfolio_positions": portfolio_positions,
            "portfolio_concentration": portfolio_concentration,
            "user_profile": user_profile,
            "watchlist": watchlist,
        }
    finally:
        db.close()



def build_tools(
    db_session_factory,
    user_id: str,
    report_id: str,
    tavily_api_key: str,
) -> list:
    """Build the runtime tool list for the investment workflow.

    Static data (portfolio positions, concentration, user profile, watchlist) is
    pre-fetched via prefetch_agent_context() and injected into agent prompts —
    these tools are NOT included here.

    All tools close over user_id, report_id, and db_session_factory.
    Each tool opens and closes its own short-lived DB session (NullPool-safe).

    Args:
        db_session_factory: Callable that returns a new SQLAlchemy Session.
        user_id: The authenticated user's ID.
        report_id: The InvestmentReport row ID for this workflow run.
        tavily_api_key: Tavily Search API key.
    """
    tavily = TavilyClient(api_key=tavily_api_key)

    # -------------------------------------------------------------------------
    # MARKET DATA TOOLS — yfinance (blocking, runs in thread executor)
    # -------------------------------------------------------------------------

    @tool
    def get_stock_fundamentals(symbol: str) -> str:
        """Fetch fundamental data for a stock or ETF ticker symbol.

        Returns a JSON object with: name, sector, industry, country, asset_type,
        current_price, currency, market_cap_category, per (trailing P/E),
        forward_per, revenue_growth, operating_margins, debt_to_equity,
        ebitda_margins, dividend_yield, expense_ratio, pea_eligible.

        pea_eligible is True for European companies (eligible for the French PEA tax wrapper).

        Args:
            symbol: Ticker symbol (e.g. "ASML", "MSFT", "IWDA.AS")
        """
        try:
            ticker = yf.Ticker(symbol)
            info = ticker.info or {}
            country_raw = info.get("country", "")
            country = YahooFinanceClient._map_country(country_raw)
            current_price = info.get("currentPrice") or info.get("regularMarketPrice") or info.get("navPrice")
            return json.dumps({
                "symbol": symbol.upper(),
                "name": info.get("longName") or info.get("shortName", symbol),
                "sector": info.get("sector"),
                "industry": info.get("industry"),
                "country": country,
                "asset_type": YahooFinanceClient._map_asset_type(info.get("quoteType")).value,
                "current_price": float(current_price) if current_price else None,
                "currency": info.get("currency", "USD"),
                "market_cap_category": YahooFinanceClient._map_market_cap_category(
                    info.get("marketCap")
                ).value if info.get("marketCap") else None,
                "per": info.get("trailingPE"),
                "forward_per": info.get("forwardPE"),
                "revenue_growth": info.get("revenueGrowth"),
                "operating_margins": info.get("operatingMargins"),
                "debt_to_equity": info.get("debtToEquity"),
                "ebitda_margins": info.get("ebitdaMargins"),
                "dividend_yield": info.get("dividendYield"),
                "expense_ratio": info.get("annualReportExpenseRatio"),
                "pea_eligible": country in _PEA_ELIGIBLE_COUNTRIES,
            }, ensure_ascii=False)
        except Exception as e:
            return json.dumps({"error": str(e), "symbol": symbol})

    # -------------------------------------------------------------------------
    # WEB SEARCH TOOL — Tavily
    # -------------------------------------------------------------------------

    @tool
    def web_search(query: str) -> str:
        """Search the web for financial news and analysis using Tavily.

        Use targeted, specific queries for best results. Examples:
        - "ASML earnings results Q4 2025"
        - "CAC40 S&P500 market trend February 2026"
        - "Technology sector PER benchmark 2026"

        Args:
            query: Search query string.

        Returns a JSON array of up to 5 results with title, url, and content snippet.
        """
        try:
            response = tavily.search(query=query, max_results=5)
            results = [
                {
                    "title": r.get("title", ""),
                    "url": r.get("url", ""),
                    "content": r.get("content", "")[:500],  # cap at 500 chars per result
                }
                for r in response.get("results", [])
            ]
            return json.dumps(results, ensure_ascii=False)
        except Exception as e:
            return json.dumps({"error": str(e), "query": query})

    # -------------------------------------------------------------------------
    # WRITE TOOLS — persist agent results to DB
    # -------------------------------------------------------------------------

    @tool
    def update_thesis_status(
        investment_id: str,
        thesis_status: str,
        notes: Optional[str] = None,
    ) -> str:
        """Update an investment's thesis status after the portfolio review step.

        Args:
            investment_id: The investment UUID (from get_portfolio_positions).
            thesis_status: One of "valid", "watch", or "reconsider".
                - valid: thesis intact, no action needed
                - watch: price moved significantly or news warrants monitoring
                - reconsider: thesis broken or fundamentals deteriorated
            notes: Optional note explaining the status change.

        Returns "ok" on success.
        """
        if thesis_status not in ("valid", "watch", "reconsider"):
            return f"Error: thesis_status must be one of valid/watch/reconsider, got '{thesis_status}'"
        db = db_session_factory()
        try:
            investment = db.query(DBInvestment).filter(DBInvestment.id == investment_id).first()
            if not investment:
                return f"Error: investment {investment_id} not found"
            investment.thesis_status = thesis_status
            if notes:
                investment.notes = notes
            investment.updated_at = datetime.utcnow()
            db.commit()
            return "ok"
        except Exception as e:
            db.rollback()
            return f"Error: {e}"
        finally:
            db.close()

    @tool
    def save_macro_context(macro_context: str) -> str:
        """Persist the macro context produced by the macro scan step to the user's profile.

        This updates the 'carnet de bord' so next month's workflow can compare
        current conditions to the previous month's context.

        Args:
            macro_context: A concise (3-4 sentence) summary of current macro environment in French.

        Returns "ok" on success.
        """
        db = db_session_factory()
        try:
            profile = (
                db.query(InvestmentProfile)
                .filter(InvestmentProfile.user_id == user_id)
                .first()
            )
            if not profile:
                return "Error: user profile not found"
            profile.last_macro_context = macro_context
            profile.last_macro_updated_at = datetime.utcnow()
            db.commit()
            return "ok"
        except Exception as e:
            db.rollback()
            return f"Error: {e}"
        finally:
            db.close()

    @tool
    def add_to_watchlist(
        name: str,
        symbol: Optional[str] = None,
        sector: Optional[str] = None,
        country: Optional[str] = None,
        reason: Optional[str] = None,
        priority: str = "normal",
    ) -> str:
        """Add a new company to the user's watchlist for future monthly reviews.

        Use this when a promising candidate is identified but its price exceeds
        the current monthly budget, or when you discover a company worth tracking
        for future months.

        Args:
            name: Company or ETF full name.
            symbol: Ticker symbol if known (optional).
            sector: Sector (e.g. "Technology", "Healthcare").
            country: ISO 3-letter country code (e.g. "FRA", "USA").
            reason: Why this is worth watching (in French).
            priority: "high", "normal", or "low".

        Returns JSON with the created item's id and name.
        """
        db = db_session_factory()
        try:
            item = InvestmentWatchlist(
                id=str(uuid4()),
                user_id=user_id,
                name=name,
                symbol=symbol,
                sector=sector,
                country=country,
                reason=reason,
                source="agent_suggestion",
                priority=priority,
                is_active=True,
            )
            db.add(item)
            db.commit()
            return json.dumps({"id": item.id, "name": item.name})
        except Exception as e:
            db.rollback()
            return f"Error: {e}"
        finally:
            db.close()

    @tool
    def save_final_report(markdown_report: str) -> str:
        """Save the complete Markdown analysis report to the database.

        Call this with the full formatted Markdown report that will be displayed to the user.

        Args:
            markdown_report: The complete Markdown report string (in French).

        Returns "ok" on success.
        """
        db = db_session_factory()
        try:
            report = (
                db.query(InvestmentReport)
                .filter(InvestmentReport.id == report_id)
                .first()
            )
            if not report:
                return f"Error: report {report_id} not found"
            report.final_recommendation = markdown_report
            db.commit()
            return "ok"
        except Exception as e:
            db.rollback()
            return f"Error: {e}"
        finally:
            db.close()

    @tool
    def save_investment_suggestions(suggestions_json: str) -> str:
        """Save structured investment suggestions so the frontend can display one action button per recommendation.

        Call this AFTER save_final_report, once per workflow run.

        Args:
            suggestions_json: JSON array of suggestion objects. Each object must include:
                symbol (str), name (str), account_type ("PEA" or "CTO"),
                allocation_eur (number or null), current_price (number or null),
                currency (str, e.g. "EUR"), suggested_quantity (number or null),
                investment_thesis (str or null), notes (str or null),
                alert_threshold_pct (number or null, e.g. 20.0).

        Example:
            '[{"symbol": "ASML", "name": "ASML Holding NV", "account_type": "PEA",
               "allocation_eur": 50.0, "current_price": 680.0, "currency": "EUR",
               "suggested_quantity": 0.073, "investment_thesis": "EUV monopoly...",
               "notes": null, "alert_threshold_pct": 20.0}]'

        Returns "ok" on success, error description on failure.
        """
        try:
            suggestions = json.loads(suggestions_json)
            if not isinstance(suggestions, list):
                return "Error: suggestions_json must be a JSON array"
            required = {"symbol", "account_type"}
            for s in suggestions:
                if not isinstance(s, dict) or not required.issubset(s.keys()):
                    return "Error: each suggestion must be an object with 'symbol' and 'account_type'"
            return "ok"
        except json.JSONDecodeError as e:
            return f"Error: invalid JSON — {e}"
        except Exception as e:
            return f"Error: {e}"

    return [
        get_stock_fundamentals,
        web_search,
        update_thesis_status,
        save_macro_context,
        add_to_watchlist,
        save_final_report,
        save_investment_suggestions,
    ]


def filter_tools(all_tools: list, names: set[str]) -> list:
    """Return only the tools whose names are in the given set."""
    return [t for t in all_tools if t.name in names]
