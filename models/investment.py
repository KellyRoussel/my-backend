"""Pydantic schemas for the investment feature."""
from datetime import date, datetime
from decimal import Decimal
from enum import Enum as PyEnum
from typing import Dict, List, Optional, Literal

from pydantic import BaseModel, Field, model_validator


# --- Request schemas ---

class InvestmentCreateRequest(BaseModel):
    account_type: Literal["CTO", "PEA"] = Field(..., description="Investment account type")
    ticker_symbol: Optional[str] = Field(None, min_length=1, max_length=20)
    isin: Optional[str] = Field(None, min_length=12, max_length=12)
    quantity: float = Field(..., gt=0)
    purchase_date: date
    notes: Optional[str] = None
    investment_thesis: Optional[str] = None
    thesis_status: Optional[str] = Field(None, pattern="^(valid|watch|reconsider)$")
    alert_threshold_pct: Optional[float] = Field(None, description="Alert threshold in %, e.g. -20.0")

    @model_validator(mode="after")
    def validate_identifiers(self) -> "InvestmentCreateRequest":
        if self.account_type == "PEA":
            if not self.ticker_symbol:
                raise ValueError("ticker_symbol is required when account_type is PEA")
        else:
            if not self.isin:
                raise ValueError("isin is required when account_type is CTO")
        return self


class InvestmentUpdateRequest(BaseModel):
    ticker_symbol: str = Field(..., min_length=1, max_length=20)


class InvestmentProfileUpdate(BaseModel):
    currency_preference: Optional[str] = Field(None, min_length=3, max_length=3)
    risk_tolerance: Optional[str] = Field(None)
    investment_horizon: Optional[str] = Field(None, max_length=50)
    ethical_exclusions: Optional[str] = None
    country: Optional[str] = Field(None, max_length=100, description="Country name or ISO code (e.g. France, FRA)")
    interests: Optional[str] = None


# --- Response schemas ---

class InvestmentResponse(BaseModel):
    model_config = {"from_attributes": True}

    id: str
    created_at: datetime
    updated_at: datetime
    user_id: str
    symbol: str
    name: str
    asset_type: str
    country: str
    sector: Optional[str] = None
    industry: Optional[str] = None
    market_cap_category: Optional[str] = None
    purchase_date: date
    purchase_price: float
    quantity: float
    currency: str
    dividend_yield: Optional[float] = None
    expense_ratio: Optional[float] = None
    notes: Optional[str] = None
    investment_thesis: Optional[str] = None
    thesis_status: Optional[str] = None
    alert_threshold_pct: Optional[float] = None
    account_type: Optional[str] = None
    is_active: bool


# --- Price history schemas ---

class DataQuality(PyEnum):
    GOOD = "good"
    DELAYED = "delayed"
    ESTIMATED = "estimated"
    MISSING = "missing"


class PriceHistoryPoint(BaseModel):
    model_config = {"from_attributes": True}

    timestamp: datetime
    price: float
    open_price: Optional[float] = None
    high_price: Optional[float] = None
    low_price: Optional[float] = None
    close_price: Optional[float] = None
    adjusted_close: Optional[float] = None
    volume: Optional[int] = None
    market_cap: Optional[int] = None
    dividend_amount: Optional[float] = None
    split_ratio: Optional[float] = None
    source: str
    data_quality: DataQuality


class PriceHistoryResponse(BaseModel):
    investment_id: str
    symbol: str
    data_points: List[PriceHistoryPoint]
    total_points: int
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None


# --- Portfolio schemas ---

class PortfolioHistoryPoint(BaseModel):
    model_config = {"from_attributes": True}

    timestamp: date
    total_value: float
    total_cost: float
    total_gain_loss: float


class PortfolioHistoryResponse(BaseModel):
    user_id: str
    data_points: List[PortfolioHistoryPoint]
    total_points: int
    start_date: Optional[date] = None
    end_date: Optional[date] = None


# --- Portfolio metrics schemas ---

class PortfolioBreakdownItem(BaseModel):
    value: float
    percentage: float
    count: int = Field(..., ge=0)


class PortfolioBreakdownMap(BaseModel):
    breakdowns: Dict[str, PortfolioBreakdownItem] = Field(default_factory=dict)


class PortfolioPerformer(BaseModel):
    investment_id: str
    symbol: str
    name: str
    gain_loss_percent: Decimal


class PortfolioPerformers(BaseModel):
    top_performers: List[PortfolioPerformer] = Field(default_factory=list)
    worst_performers: List[PortfolioPerformer] = Field(default_factory=list)


class DiversificationScore(BaseModel):
    score: float = Field(..., ge=0)


class PortfolioMetrics(BaseModel):
    user_id: str
    total_value: Decimal
    total_cost: Decimal
    total_gain_loss: Decimal
    total_gain_loss_percent: Decimal
    diversification_score: float
    investment_count: int
    breakdown_by_country: Dict[str, PortfolioBreakdownItem] = Field(default_factory=dict)
    breakdown_by_sector: Dict[str, PortfolioBreakdownItem] = Field(default_factory=dict)
    breakdown_by_asset_type: Dict[str, PortfolioBreakdownItem] = Field(default_factory=dict)
    top_performers: List[PortfolioPerformer] = Field(default_factory=list)
    worst_performers: List[PortfolioPerformer] = Field(default_factory=list)
    currency: str


class InvestmentMetrics(BaseModel):
    current_value: Optional[float]
    gain_loss: Optional[float]
    gain_loss_percent: Optional[float]
    performance_status: str


# --- Investment profile response ---

class InvestmentProfileResponse(BaseModel):
    model_config = {"from_attributes": True}

    currency_preference: str
    risk_tolerance: Optional[str] = None
    investment_horizon: Optional[str] = None
    ethical_exclusions: Optional[str] = None
    country: Optional[str] = None
    interests: Optional[str] = None
    last_macro_context: Optional[str] = None


# --- Watchlist schemas ---

class WatchlistItemCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    symbol: Optional[str] = Field(None, max_length=20)
    sector: Optional[str] = None
    country: Optional[str] = Field(None, min_length=2, max_length=3)
    reason: Optional[str] = None
    priority: str = Field(default="normal", pattern="^(high|normal|low)$")


class WatchlistItemResponse(BaseModel):
    model_config = {"from_attributes": True}

    id: str
    symbol: Optional[str] = None
    name: str
    sector: Optional[str] = None
    country: Optional[str] = None
    reason: Optional[str] = None
    source: Optional[str] = None
    priority: Optional[str] = None
    is_active: bool
    created_at: datetime


# --- Monthly report schemas ---

class InvestmentReportResponse(BaseModel):
    model_config = {"from_attributes": True}

    id: str
    user_id: str
    report_date: date
    final_recommendation: Optional[str] = None
    status: str
    created_at: datetime
    completed_at: Optional[datetime] = None
    tokens_input: Optional[int] = None
    tokens_cached: Optional[int] = None
    tokens_output: Optional[int] = None
    cost_usd: Optional[float] = None
    model_used: Optional[str] = None
