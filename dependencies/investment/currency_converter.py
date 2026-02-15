"""Service for converting currencies using historical exchange rates from Yahoo Finance."""
from datetime import date, datetime, timedelta
from typing import Dict, Optional
from functools import lru_cache

from dependencies.investment.yahoo_finance import YahooFinanceClient


class CurrencyConverter:
    """Service for currency conversion using Yahoo Finance exchange rates."""

    @staticmethod
    def _get_currency_pair_symbol(from_currency: str, to_currency: str) -> Optional[str]:
        if from_currency == to_currency:
            return None
        return f"{from_currency}{to_currency}=X"

    @staticmethod
    @lru_cache(maxsize=1000)
    def get_exchange_rate(from_currency: str, to_currency: str, target_date: date) -> Optional[float]:
        if from_currency == to_currency:
            return 1.0

        symbol = CurrencyConverter._get_currency_pair_symbol(from_currency, to_currency)
        if not symbol:
            return 1.0

        try:
            history = YahooFinanceClient.get_price_history(
                symbol,
                target_date - timedelta(days=7),
                target_date,
            )
            if not history:
                return None
            return history[-1].price
        except Exception:
            return None

    @staticmethod
    def get_exchange_rate_history(
        from_currency: str,
        to_currency: str,
        start_date: date,
        end_date: date,
    ) -> Dict[datetime, float]:
        if from_currency == to_currency:
            result = {}
            current = datetime.combine(start_date, datetime.min.time())
            end = datetime.combine(end_date, datetime.min.time())
            while current <= end:
                result[current] = 1.0
                current += timedelta(days=1)
            return result

        symbol = CurrencyConverter._get_currency_pair_symbol(from_currency, to_currency)
        if not symbol:
            return {}

        try:
            history = YahooFinanceClient.get_price_history(symbol, start_date, end_date)
            return {
                datetime.combine(point.timestamp.date(), datetime.min.time()): point.price
                for point in history
                if point.price is not None
            }
        except Exception:
            return {}

    @staticmethod
    def convert_amount(
        amount: float,
        from_currency: str,
        to_currency: str,
        conversion_date: date = None,
    ) -> Optional[float]:
        if conversion_date is None:
            conversion_date = date.today()
        rate = CurrencyConverter.get_exchange_rate(from_currency, to_currency, conversion_date)
        if rate is None:
            return None
        return amount * rate
