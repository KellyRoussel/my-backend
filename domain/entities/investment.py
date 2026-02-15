"""Investment domain entity."""
from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from typing import Optional
from uuid import uuid4

from pydantic import BaseModel, Field, field_validator

from domain.value_objects import Money


class AssetType(str, Enum):
    STOCK = "stock"
    ETF = "etf"
    CRYPTO = "crypto"
    BOND = "bond"
    COMMODITY = "commodity"
    REIT = "reit"
    MUTUAL_FUND = "mutual_fund"


class MarketCapCategory(str, Enum):
    LARGE_CAP = "large_cap"
    MID_CAP = "mid_cap"
    SMALL_CAP = "small_cap"
    MICRO_CAP = "micro_cap"


class Vehicle(BaseModel):
    symbol: str = Field(..., min_length=1, max_length=20)
    name: str = Field(..., min_length=1, max_length=255)
    asset_type: AssetType
    country: str = Field(..., min_length=2, max_length=3)
    sector: Optional[str] = Field(None, max_length=100)
    industry: Optional[str] = Field(None, max_length=100)
    market_cap_category: Optional[MarketCapCategory] = None

    @field_validator('symbol')
    def validate_symbol(cls, v):
        if not v.replace('-', '').replace('.', '').isalnum():
            raise ValueError('Symbol can only contain letters, digits, hyphens and dots')
        return v.upper()

    @field_validator('country')
    def validate_country(cls, v):
        if not v.isalpha() or not v.isupper():
            raise ValueError('Country must be an uppercase ISO 3166-1 alpha-3 code')
        return v


class Investment(BaseModel):
    """Domain entity representing a portfolio investment."""

    id: str = Field(default_factory=lambda: str(uuid4()))
    user_id: str

    vehicle: Vehicle

    purchase_date: date
    purchase_price: Money
    quantity: int = Field(..., gt=0)

    @field_validator('purchase_date')
    def validate_purchase_date(cls, v):
        if v > date.today():
            raise ValueError('Purchase date cannot be in the future')
        return v

    def add_quantity(self, additional_quantity: Decimal, new_price: Money) -> None:
        if additional_quantity <= 0:
            raise ValueError('Additional quantity must be positive')
        if new_price.currency != self.purchase_price.currency:
            raise ValueError(
                f'New price currency ({new_price.currency}) must match '
                f'purchase price currency ({self.purchase_price.currency})'
            )
        total_current_value = self.purchase_price * self.quantity
        additional_value = new_price * additional_quantity
        total_new_quantity = self.quantity + additional_quantity
        self.purchase_price = Money(
            amount=(total_current_value.amount + additional_value.amount) / total_new_quantity,
            currency=self.purchase_price.currency
        )
        self.quantity = total_new_quantity

    def remove_quantity(self, quantity_to_remove: Decimal) -> Decimal:
        if quantity_to_remove <= 0:
            raise ValueError('Quantity to remove must be positive')
        if quantity_to_remove > self.quantity:
            raise ValueError('Quantity to remove exceeds held quantity')
        remaining_quantity = self.quantity - quantity_to_remove
        self.quantity = remaining_quantity
        return remaining_quantity

    def calculate_total_cost(self) -> Money:
        return self.purchase_price * self.quantity

    class Config:
        use_enum_values = True
        validate_assignment = True
        arbitrary_types_allowed = True
