"""Value Object for representing money with currency."""
from decimal import Decimal
from typing import Union
from pydantic import BaseModel, Field, field_validator


class Money(BaseModel):
    """Value Object for a monetary amount with currency."""

    amount: Decimal = Field(..., decimal_places=4, description="Amount")
    currency: str = Field(..., min_length=3, max_length=3, description="ISO 4217 currency code")

    @field_validator('amount')
    def validate_amount(cls, v):
        if v < 0:
            raise ValueError('Amount cannot be negative')
        return v

    @field_validator('currency')
    def validate_currency(cls, v):
        if not v.isalpha() or not v.isupper():
            raise ValueError('Currency must be an uppercase ISO 4217 code (e.g. USD, EUR)')
        return v

    def __add__(self, other: 'Money') -> 'Money':
        if not isinstance(other, Money):
            raise TypeError('Can only add with another Money object')
        if self.currency != other.currency:
            raise ValueError(f'Cannot add {self.currency} and {other.currency}')
        return Money(amount=self.amount + other.amount, currency=self.currency)

    def __sub__(self, other: 'Money') -> 'Money':
        if not isinstance(other, Money):
            raise TypeError('Can only subtract with another Money object')
        if self.currency != other.currency:
            raise ValueError(f'Cannot subtract {self.currency} and {other.currency}')
        return Money(amount=self.amount - other.amount, currency=self.currency)

    def __mul__(self, multiplier: Union[int, float, Decimal]) -> 'Money':
        if not isinstance(multiplier, (int, float, Decimal)):
            raise TypeError('Multiplier must be a number')
        return Money(amount=self.amount * Decimal(str(multiplier)), currency=self.currency)

    def __truediv__(self, divisor: Union[int, float, Decimal]) -> 'Money':
        if not isinstance(divisor, (int, float, Decimal)):
            raise TypeError('Divisor must be a number')
        if divisor == 0:
            raise ValueError('Division by zero')
        return Money(amount=self.amount / Decimal(str(divisor)), currency=self.currency)

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Money):
            return False
        return self.amount == other.amount and self.currency == other.currency

    def __lt__(self, other: 'Money') -> bool:
        if not isinstance(other, Money):
            raise TypeError('Can only compare with another Money object')
        if self.currency != other.currency:
            raise ValueError(f'Cannot compare {self.currency} and {other.currency}')
        return self.amount < other.amount

    def __le__(self, other: 'Money') -> bool:
        return self < other or self == other

    def __gt__(self, other: 'Money') -> bool:
        return not self <= other

    def __ge__(self, other: 'Money') -> bool:
        return not self < other

    def to_float(self) -> float:
        return float(self.amount)

    def round_to_cents(self) -> 'Money':
        return Money(
            amount=self.amount.quantize(Decimal('0.01')),
            currency=self.currency
        )

    def format_currency(self, locale: str = 'en_US') -> str:
        currency_symbols = {
            'USD': '$', 'EUR': '€', 'GBP': '£', 'JPY': '¥',
            'CAD': 'C$', 'CHF': 'CHF', 'AUD': 'A$', 'CNY': '¥',
            'SEK': 'kr', 'NOK': 'kr', 'DKK': 'kr',
        }
        symbol = currency_symbols.get(self.currency, self.currency)
        if self.currency in ['JPY', 'KRW', 'VND', 'IDR']:
            return f"{symbol}{self.amount:.0f}"
        else:
            return f"{symbol}{self.amount:.2f}"

    def __str__(self) -> str:
        return self.format_currency()

    def __repr__(self) -> str:
        return f"Money(amount={self.amount}, currency='{self.currency}')"


class MoneyZero(Money):
    def __init__(self, currency: str = "USD"):
        super().__init__(amount=Decimal('0'), currency=currency)


USD_ZERO = MoneyZero("USD")
EUR_ZERO = MoneyZero("EUR")
