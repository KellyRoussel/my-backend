"""Investment feature router — portfolio CRUD, metrics, price history, AI recommendations."""
from collections import defaultdict
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from database import get_db
from dependencies.investment.open_figi import OpenFigiClient
from dependencies.investment.yahoo_finance import YahooFinanceClient
from dependencies.investment.currency_converter import CurrencyConverter
from dependencies.investment.portfolio_calculator import PortfolioCalculator
from dependencies.investment.ai_agents import launch_agents_stream
from dependencies.investment.ai_agents_v2 import InvestmentWorkflowV2
from domain.entities.investment import Investment as DomainInvestment, Vehicle
from domain.value_objects import Money
from models.database_models import (
    Investment as DBInvestment,
    InvestmentReport,
    InvestmentProfile,
    InvestmentWatchlist,
    RiskTolerance,
)
from models.investment import (
    InvestmentCreateRequest,
    InvestmentUpdateRequest,
    InvestmentProfileUpdate,
    InvestmentResponse,
    InvestmentProfileResponse,
    InvestmentReportResponse,
    PriceHistoryResponse,
    PortfolioHistoryPoint,
    PortfolioHistoryResponse,
    PortfolioMetrics,
    WatchlistItemCreate,
    WatchlistItemResponse,
)
from repositories import InvestmentRepository


investment_router = APIRouter(prefix="/investment", tags=["Investment"])


# --- Helpers ---

def _get_user_id(request: Request) -> str:
    return request.state.user_id


def _get_or_create_profile(user_id: str, db: Session) -> InvestmentProfile:
    profile = db.query(InvestmentProfile).filter(InvestmentProfile.user_id == user_id).first()
    if not profile:
        profile = InvestmentProfile(user_id=user_id)
        db.add(profile)
        db.commit()
        db.refresh(profile)
    return profile


def _to_decimal(value: Optional[float]) -> Optional[Decimal]:
    if value is None:
        return None
    return Decimal(str(value))


def _build_investment_response(investment: DBInvestment) -> InvestmentResponse:
    return InvestmentResponse(
        id=investment.id,
        created_at=investment.created_at,
        updated_at=investment.updated_at,
        user_id=investment.user_id,
        symbol=investment.symbol,
        name=investment.name,
        asset_type=investment.asset_type.value if investment.asset_type else None,
        country=investment.country,
        sector=investment.sector,
        industry=investment.industry,
        market_cap_category=investment.market_cap_category.value if investment.market_cap_category else None,
        purchase_date=investment.purchase_date,
        purchase_price=float(investment.purchase_price),
        quantity=float(investment.quantity),
        currency=investment.currency,
        dividend_yield=float(investment.dividend_yield) if investment.dividend_yield is not None else None,
        expense_ratio=float(investment.expense_ratio) if investment.expense_ratio is not None else None,
        notes=investment.notes,
        investment_thesis=investment.investment_thesis,
        thesis_status=investment.thesis_status,
        alert_threshold_pct=float(investment.alert_threshold_pct) if investment.alert_threshold_pct is not None else None,
        account_type=investment.account_type,
        is_active=investment.is_active,
    )


def _db_investment_to_domain(db_investment: DBInvestment) -> DomainInvestment:
    """Convert database investment model to domain entity."""
    vehicle = Vehicle(
        symbol=db_investment.symbol,
        name=db_investment.name,
        asset_type=db_investment.asset_type,
        country=db_investment.country,
        sector=db_investment.sector,
        industry=db_investment.industry,
        market_cap_category=db_investment.market_cap_category,
    )
    return DomainInvestment(
        id=db_investment.id,
        user_id=db_investment.user_id,
        vehicle=vehicle,
        purchase_date=db_investment.purchase_date,
        purchase_price=Money(
            amount=float(db_investment.purchase_price),
            currency=db_investment.currency,
        ),
        quantity=int(db_investment.quantity),
    )


# --- Investment CRUD ---

@investment_router.post("/investments", response_model=InvestmentResponse, status_code=status.HTTP_201_CREATED)
def create_investment(
    payload: InvestmentCreateRequest,
    request: Request,
    db: Session = Depends(get_db),
) -> InvestmentResponse:
    user_id = _get_user_id(request)
    investment_repo = InvestmentRepository(db)

    if payload.account_type == "PEA":
        ticker_symbol = payload.ticker_symbol
    else:
        try:
            ticker_symbol = OpenFigiClient.isin_to_ticker(payload.isin)
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=str(exc),
            ) from exc

    if not ticker_symbol:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Unable to resolve ticker_symbol from the provided input.",
        )

    profile = YahooFinanceClient.get_investment_profile(ticker_symbol)
    purchase_price = YahooFinanceClient.get_purchase_price(ticker_symbol, payload.purchase_date)

    if purchase_price is None:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Unable to fetch purchase price for the provided date.",
        )

    created = investment_repo.create(
        user_id=user_id,
        symbol=profile["symbol"],
        name=profile["name"],
        asset_type=profile["asset_type"],
        country=profile["country"],
        purchase_date=payload.purchase_date,
        purchase_price=_to_decimal(purchase_price),
        quantity=Decimal(str(payload.quantity)),
        currency=profile["currency"],
        sector=profile["sector"],
        industry=profile["industry"],
        market_cap_category=profile["market_cap_category"],
        notes=payload.notes,
        investment_thesis=payload.investment_thesis,
        thesis_status=payload.thesis_status,
        alert_threshold_pct=_to_decimal(payload.alert_threshold_pct),
        account_type=payload.account_type,
    )

    return _build_investment_response(created)


@investment_router.patch("/investments/{investment_id}", response_model=InvestmentResponse)
def update_investment(
    investment_id: str,
    payload: InvestmentUpdateRequest,
    request: Request,
    db: Session = Depends(get_db),
) -> InvestmentResponse:
    user_id = _get_user_id(request)
    investment_repo = InvestmentRepository(db)

    investment = investment_repo.get_by_id(investment_id)
    if investment is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Investment not found.")

    if investment.user_id != user_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized to update this investment")

    profile = YahooFinanceClient.get_investment_profile(payload.ticker_symbol)

    investment.symbol = profile["symbol"]
    investment.name = profile["name"]
    investment.asset_type = profile["asset_type"]
    investment.country = profile["country"]
    investment.sector = profile["sector"]
    investment.industry = profile["industry"]
    investment.market_cap_category = profile["market_cap_category"]
    investment.currency = profile["currency"]

    investment_repo.update(investment)
    return _build_investment_response(investment)


@investment_router.get("/investments", response_model=list[InvestmentResponse])
def list_user_investments(
    request: Request,
    skip: int = 0,
    limit: int = 100,
    active_only: bool = True,
    db: Session = Depends(get_db),
) -> list[InvestmentResponse]:
    user_id = _get_user_id(request)
    investment_repo = InvestmentRepository(db)
    investments = investment_repo.get_by_user(
        user_id=user_id,
        active_only=active_only,
        skip=skip,
        limit=limit,
    )
    return [_build_investment_response(inv) for inv in investments]


@investment_router.get("/investments/{investment_id}/price-history", response_model=PriceHistoryResponse)
def get_price_history(
    investment_id: str,
    request: Request,
    start_date: Optional[date] = Query(None, description="Start date (default: 30 days ago)"),
    end_date: Optional[date] = Query(None, description="End date (default: today)"),
    db: Session = Depends(get_db),
) -> PriceHistoryResponse:
    user_id = _get_user_id(request)
    investment_repo = InvestmentRepository(db)

    investment = investment_repo.get_by_id(investment_id)
    if investment is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Investment not found")

    if investment.user_id != user_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized to view this investment's price history")

    if end_date is None:
        end_date = date.today()
    if start_date is None:
        start_date = end_date - timedelta(days=30)

    price_histories = YahooFinanceClient.get_price_history(investment.symbol, start_date, end_date)

    return PriceHistoryResponse(
        investment_id=str(investment_id),
        symbol=investment.symbol,
        data_points=price_histories,
        total_points=len(price_histories),
        start_date=price_histories[0].timestamp if price_histories else None,
        end_date=price_histories[-1].timestamp if price_histories else None,
    )


@investment_router.delete("/investments/{investment_id}")
def delete_investment(
    investment_id: str,
    request: Request,
    db: Session = Depends(get_db),
) -> dict:
    user_id = _get_user_id(request)
    investment_repo = InvestmentRepository(db)

    investment = investment_repo.get_by_id(investment_id)
    if investment is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Investment not found.")

    if investment.user_id != user_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized to delete this investment")

    investment_repo.delete(investment_id)
    return {"detail": "Investment deleted successfully."}


# --- Portfolio ---

@investment_router.get("/portfolio/metrics")
def get_portfolio_metrics(
    request: Request,
    db: Session = Depends(get_db),
) -> PortfolioMetrics:
    user_id = _get_user_id(request)
    profile = _get_or_create_profile(user_id, db)
    calculator = PortfolioCalculator(db)
    return calculator.calculate_portfolio_metrics(user_id, profile.currency_preference or "USD")


@investment_router.get("/portfolio/price-history", response_model=PortfolioHistoryResponse)
def get_portfolio_price_history(
    request: Request,
    start_date: Optional[date] = Query(None, description="Start date (default: 30 days ago)"),
    end_date: Optional[date] = Query(None, description="End date (default: today)"),
    db: Session = Depends(get_db),
) -> PortfolioHistoryResponse:
    user_id = _get_user_id(request)
    profile = _get_or_create_profile(user_id, db)
    user_currency = profile.currency_preference or "USD"
    investment_repo = InvestmentRepository(db)

    if end_date is None:
        end_date = date.today()
    if start_date is None:
        start_date = end_date - timedelta(days=30)

    investments = investment_repo.get_by_user(user_id=user_id, active_only=True, skip=0, limit=1000)

    # Collect exchange rate histories for all needed currencies
    currencies = set(inv.currency for inv in investments if inv.currency != user_currency)
    exchange_rate_histories = {}
    for currency in currencies:
        exchange_rate_histories[currency] = CurrencyConverter.get_exchange_rate_history(
            currency, user_currency, start_date, end_date
        )

    totals: dict[date, float] = defaultdict(float)
    costs: dict[date, float] = defaultdict(float)

    for investment in investments:
        if investment.purchase_date and investment.purchase_date > end_date:
            continue
        history_start = (
            max(start_date, investment.purchase_date)
            if investment.purchase_date
            else start_date
        )
        history = YahooFinanceClient.get_price_history(investment.symbol, history_start, end_date)

        purchase_price_in_user_currency = float(investment.purchase_price)
        if investment.currency != user_currency and investment.purchase_date:
            exchange_rate = CurrencyConverter.get_exchange_rate(
                investment.currency, user_currency, investment.purchase_date
            )
            if exchange_rate:
                purchase_price_in_user_currency = float(investment.purchase_price) * exchange_rate

        for point in history:
            price = point.price
            if price is None:
                continue
            point_date = point.timestamp.date()

            if investment.currency == user_currency:
                converted_price = price
            else:
                rates = exchange_rate_histories.get(investment.currency, {})
                exchange_rate = rates.get(datetime.combine(point_date, datetime.min.time()))
                converted_price = price * exchange_rate if exchange_rate else price

            totals[point_date] += float(converted_price) * float(investment.quantity)
            costs[point_date] += float(purchase_price_in_user_currency) * float(investment.quantity)

    data_points = [
        PortfolioHistoryPoint(
            timestamp=date_val,
            total_value=totals[date_val],
            total_cost=costs[date_val],
            total_gain_loss=totals[date_val] - costs[date_val],
        )
        for date_val in sorted(totals.keys())
    ]

    return PortfolioHistoryResponse(
        user_id=user_id,
        data_points=data_points,
        total_points=len(data_points),
        start_date=data_points[0].timestamp if data_points else None,
        end_date=data_points[-1].timestamp if data_points else None,
    )


# --- Recommendations ---

@investment_router.get("/recommendations/generate")
async def generate_recommendation(
    request: Request,
    db: Session = Depends(get_db),
) -> StreamingResponse:
    """Generate AI-powered investment recommendations with SSE streaming."""
    user_id = _get_user_id(request)
    profile = _get_or_create_profile(user_id, db)
    user_currency = profile.currency_preference or "USD"

    investment_repo = InvestmentRepository(db)
    calculator = PortfolioCalculator(db)

    investments = investment_repo.get_by_user(user_id=user_id, active_only=True, skip=0, limit=1000)
    portfolio = [_db_investment_to_domain(inv) for inv in investments]
    portfolio_metrics = calculator.calculate_portfolio_metrics(user_id, user_currency)

    async def event_generator():
        try:
            async for event in launch_agents_stream(portfolio, portfolio_metrics):
                yield event.to_sse()
        except Exception as e:
            yield f"data: {{'type': 'error', 'message': '{str(e)}'}}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


# --- Profile ---

@investment_router.get("/profile", response_model=InvestmentProfileResponse)
def get_investment_profile(
    request: Request,
    db: Session = Depends(get_db),
) -> InvestmentProfileResponse:
    user_id = _get_user_id(request)
    profile = _get_or_create_profile(user_id, db)
    return InvestmentProfileResponse(
        currency_preference=profile.currency_preference,
        risk_tolerance=profile.risk_tolerance.value if profile.risk_tolerance else None,
        investment_horizon=profile.investment_horizon,
        ethical_exclusions=profile.ethical_exclusions,
        country=profile.country,
        interests=profile.interests,
        last_macro_context=profile.last_macro_context,
    )


@investment_router.patch("/profile", response_model=InvestmentProfileResponse)
def update_investment_profile(
    payload: InvestmentProfileUpdate,
    request: Request,
    db: Session = Depends(get_db),
) -> InvestmentProfileResponse:
    user_id = _get_user_id(request)
    profile = _get_or_create_profile(user_id, db)

    if payload.currency_preference is not None:
        profile.currency_preference = payload.currency_preference
    if payload.risk_tolerance is not None:
        profile.risk_tolerance = RiskTolerance(payload.risk_tolerance)
    if payload.investment_horizon is not None:
        profile.investment_horizon = payload.investment_horizon
    if payload.ethical_exclusions is not None:
        profile.ethical_exclusions = payload.ethical_exclusions
    if payload.country is not None:
        profile.country = payload.country
    if payload.interests is not None:
        profile.interests = payload.interests

    db.commit()
    db.refresh(profile)

    return InvestmentProfileResponse(
        currency_preference=profile.currency_preference,
        risk_tolerance=profile.risk_tolerance.value if profile.risk_tolerance else None,
        investment_horizon=profile.investment_horizon,
        ethical_exclusions=profile.ethical_exclusions,
        country=profile.country,
        interests=profile.interests,
        last_macro_context=profile.last_macro_context,
    )


# --- Recommendations v2 (DeepAgents) ---

@investment_router.get("/recommendations/generate/v2")
async def generate_recommendation_v2(
    request: Request,
    budget_eur: float = Query(..., description="Budget available for investment (EUR)", gt=0),
) -> StreamingResponse:
    """V2: DeepAgents monthly investment workflow with SSE streaming.

    Runs a structured workflow (portfolio review → macro scan →
    opportunity research → decision & thesis) and streams progress events.

    The `budget_eur` parameter is required: the agent will not recommend
    any asset whose unit price exceeds this value.

    Event types:
    - workflow_start: workflow begins
    - step_start / step_complete: sub-agent step lifecycle
    - tool_call: base tool invocations (web search, yfinance, etc.)
    - token: streaming LLM tokens from any agent
    - workflow_complete: report saved, report_id included
    - error: unrecoverable error
    """
    user_id = _get_user_id(request)
    workflow = InvestmentWorkflowV2(user_id=user_id, budget_eur=budget_eur)

    async def event_generator():
        async for sse_line in workflow.stream():
            yield sse_line

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@investment_router.get("/recommendations/history", response_model=list[InvestmentReportResponse])
def list_monthly_reports(
    request: Request,
    db: Session = Depends(get_db),
) -> list[InvestmentReportResponse]:
    """List the last 12 completed monthly reports for the authenticated user."""
    user_id = _get_user_id(request)
    reports = (
        db.query(InvestmentReport)
        .filter(
            InvestmentReport.user_id == user_id,
            InvestmentReport.status == "completed",
        )
        .order_by(InvestmentReport.report_date.desc())
        .limit(12)
        .all()
    )
    return reports


# --- Watchlist ---

@investment_router.get("/watchlist", response_model=list[WatchlistItemResponse])
def list_watchlist(
    request: Request,
    db: Session = Depends(get_db),
) -> list[WatchlistItemResponse]:
    """Return the user's active watchlist items."""
    user_id = _get_user_id(request)
    items = (
        db.query(InvestmentWatchlist)
        .filter(
            InvestmentWatchlist.user_id == user_id,
            InvestmentWatchlist.is_active == True,
        )
        .order_by(InvestmentWatchlist.created_at.desc())
        .all()
    )
    return items


@investment_router.post("/watchlist", response_model=WatchlistItemResponse, status_code=201)
def add_watchlist_item(
    payload: WatchlistItemCreate,
    request: Request,
    db: Session = Depends(get_db),
) -> WatchlistItemResponse:
    """Add a new item to the user's watchlist."""
    from uuid import uuid4 as _uuid4
    user_id = _get_user_id(request)
    item = InvestmentWatchlist(
        id=str(_uuid4()),
        user_id=user_id,
        name=payload.name,
        symbol=payload.symbol,
        sector=payload.sector,
        country=payload.country,
        reason=payload.reason,
        priority=payload.priority,
        source="manual",
        is_active=True,
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


@investment_router.delete("/watchlist/{item_id}")
def remove_watchlist_item(
    item_id: str,
    request: Request,
    db: Session = Depends(get_db),
) -> dict:
    """Remove an item from the watchlist (soft-delete)."""
    user_id = _get_user_id(request)
    item = db.query(InvestmentWatchlist).filter(InvestmentWatchlist.id == item_id).first()
    if not item:
        raise HTTPException(status_code=404, detail="Watchlist item not found.")
    if item.user_id != user_id:
        raise HTTPException(status_code=403, detail="Not authorized.")
    item.is_active = False
    db.commit()
    return {"detail": "Item removed from watchlist."}
