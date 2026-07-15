"""Client for Yahoo Finance via yfinance."""
import logging
import time
from datetime import date, datetime, timedelta
from typing import Callable, Optional, TypeVar

import yfinance as yf
from curl_cffi import requests as _cffi_requests
from yfinance.exceptions import YFRateLimitError

from models.database_models import AssetType, MarketCapCategory
from models.investment import DataQuality, PriceHistoryPoint

logger = logging.getLogger(__name__)

# A single browser-impersonating session shared by every Ticker. Yahoo aggressively
# 429s "unbranded" clients coming from datacenter IPs (e.g. Render on a cold start),
# so impersonating Chrome dramatically cuts down on YFRateLimitError.
_SESSION = _cffi_requests.Session(impersonate="chrome")

_MAX_RETRIES = 4
_BASE_DELAY_SECONDS = 2.0

_T = TypeVar("_T")


class YahooFinanceClient:
    """Client for Yahoo Finance via yfinance."""

    @staticmethod
    def _ticker(ticker_symbol: str) -> yf.Ticker:
        return yf.Ticker(ticker_symbol, session=_SESSION)

    @staticmethod
    def _with_retry(fn: Callable[[], _T], *, what: str) -> _T:
        """Run ``fn``, retrying with exponential backoff on Yahoo rate limits.

        A cold Render instance has no cached Yahoo cookie/crumb, so the first
        burst of requests can be rate limited; a couple of backed-off retries is
        usually enough for the crumb to be established and the call to succeed.
        """
        delay = _BASE_DELAY_SECONDS
        for attempt in range(1, _MAX_RETRIES + 1):
            try:
                return fn()
            except YFRateLimitError:
                if attempt == _MAX_RETRIES:
                    logger.warning("Yahoo rate limited on %s, giving up after %d attempts", what, attempt)
                    raise
                logger.warning(
                    "Yahoo rate limited on %s (attempt %d/%d), retrying in %.1fs",
                    what, attempt, _MAX_RETRIES, delay,
                )
                time.sleep(delay)
                delay *= 2
        raise AssertionError("unreachable")  # pragma: no cover

    @staticmethod
    def _map_asset_type(quote_type: Optional[str]) -> AssetType:
        mapping = {
            "EQUITY": AssetType.STOCK,
            "ETF": AssetType.ETF,
            "CRYPTOCURRENCY": AssetType.CRYPTO,
            "BOND": AssetType.BOND,
            "MUTUALFUND": AssetType.MUTUAL_FUND,
            "REIT": AssetType.REIT,
        }
        return mapping.get((quote_type or "").upper(), AssetType.STOCK)

    @staticmethod
    def _map_country(country: Optional[str]) -> str:
        if not country:
            return "UNK"

        upper = country.upper()
        if len(upper) in (2, 3) and upper.isalpha():
            return upper

        name_mapping = {
            "UNITED STATES": "USA",
            "UNITED KINGDOM": "GBR",
            "CANADA": "CAN",
            "FRANCE": "FRA",
            "GERMANY": "DEU",
            "SPAIN": "ESP",
            "ITALY": "ITA",
            "SWITZERLAND": "CHE",
            "NETHERLANDS": "NLD",
            "BELGIUM": "BEL",
            "PORTUGAL": "PRT",
            "IRELAND": "IRL",
            "JAPAN": "JPN",
            "CHINA": "CHN",
            "HONG KONG": "HKG",
            "SINGAPORE": "SGP",
            "AUSTRALIA": "AUS",
            "NEW ZEALAND": "NZL",
            "BRAZIL": "BRA",
            "INDIA": "IND",
            "SWEDEN": "SWE",
            "NORWAY": "NOR",
            "DENMARK": "DNK",
            "FINLAND": "FIN",
            "AUSTRIA": "AUT",
        }
        return name_mapping.get(upper, "UNK")

    @staticmethod
    def _map_market_cap_category(market_cap: Optional[int]) -> Optional[MarketCapCategory]:
        if market_cap is None:
            return None
        if market_cap > 10_000_000_000:
            return MarketCapCategory.LARGE_CAP
        if market_cap > 2_000_000_000:
            return MarketCapCategory.MID_CAP
        if market_cap > 300_000_000:
            return MarketCapCategory.SMALL_CAP
        return MarketCapCategory.MICRO_CAP

    @staticmethod
    def _get_current_price(ticker: yf.Ticker, info: dict) -> Optional[float]:
        price = info.get("regularMarketPrice") or info.get("currentPrice")
        if price is not None:
            return float(price)

        data = YahooFinanceClient._with_retry(
            lambda: ticker.history(period="1d"), what="current price (1d)"
        )
        if not data.empty:
            return float(data["Close"].iloc[-1])
        data = YahooFinanceClient._with_retry(
            lambda: ticker.history(period="5d"), what="current price (5d)"
        )
        if not data.empty:
            return float(data["Close"].iloc[-1])
        return None

    @staticmethod
    def get_purchase_price(ticker_symbol: str, purchase_date: date) -> Optional[float]:
        ticker = YahooFinanceClient._ticker(ticker_symbol)
        start = datetime.combine(purchase_date - timedelta(days=7), datetime.min.time())
        end = datetime.combine(purchase_date + timedelta(days=1), datetime.min.time())
        data = YahooFinanceClient._with_retry(
            lambda: ticker.history(start=start, end=end),
            what=f"purchase price {ticker_symbol}",
        )
        if data.empty:
            return None
        if getattr(data.index, "tz", None) is not None:
            data = data.tz_convert("UTC")
            data.index = data.index.tz_localize(None)
        cutoff = datetime.combine(purchase_date, datetime.max.time())
        data = data.loc[:cutoff]
        if data.empty:
            return None
        return float(data["Close"].iloc[-1])

    @staticmethod
    def get_latest_close(ticker_symbol: str) -> Optional[float]:
        ticker = YahooFinanceClient._ticker(ticker_symbol)
        data = YahooFinanceClient._with_retry(
            lambda: ticker.history(period="5d"),
            what=f"latest close {ticker_symbol}",
        )
        if data.empty:
            return None
        return float(data["Close"].iloc[-1])

    @staticmethod
    def get_investment_profile(ticker_symbol: str) -> dict:
        ticker = YahooFinanceClient._ticker(ticker_symbol)
        info = YahooFinanceClient._with_retry(
            lambda: ticker.info, what=f"info {ticker_symbol}"
        ) or {}

        return {
            "symbol": (info.get("symbol") or ticker_symbol).upper(),
            "name": info.get("shortName") or info.get("longName") or ticker_symbol.upper(),
            "asset_type": YahooFinanceClient._map_asset_type(info.get("quoteType")),
            "country": YahooFinanceClient._map_country(info.get("country")),
            "sector": info.get("sector"),
            "industry": info.get("industry"),
            "market_cap_category": YahooFinanceClient._map_market_cap_category(info.get("marketCap")),
            "currency": (info.get("currency") or "USD").upper(),
            "current_price": YahooFinanceClient._get_current_price(ticker, info),
        }

    @staticmethod
    def get_price_history(ticker_symbol: str, start_date: date, end_date: date) -> list[PriceHistoryPoint]:
        ticker = YahooFinanceClient._ticker(ticker_symbol)
        fetch_start_date = start_date - timedelta(days=7)
        start = datetime.combine(fetch_start_date, datetime.min.time())
        end = datetime.combine(end_date + timedelta(days=1), datetime.min.time())
        data = YahooFinanceClient._with_retry(
            lambda: ticker.history(start=start, end=end),
            what=f"price history {ticker_symbol}",
        )
        if data.empty:
            return []
        if getattr(data.index, "tz", None) is not None:
            data = data.tz_convert("UTC")
            data.index = data.index.tz_localize(None)

        def _clean_float(value: object) -> Optional[float]:
            if value is None:
                return None
            try:
                numeric = float(value)
            except (TypeError, ValueError):
                return None
            if numeric != numeric:
                return None
            return numeric

        def _clean_int(value: object) -> Optional[int]:
            numeric = _clean_float(value)
            if numeric is None:
                return None
            return int(numeric)

        points_by_date: dict[date, PriceHistoryPoint] = {}
        last_point: Optional[PriceHistoryPoint] = None
        for timestamp, row in data.iterrows():
            close_price = _clean_float(row.get("Close"))
            open_price = _clean_float(row.get("Open"))
            high_price = _clean_float(row.get("High"))
            low_price = _clean_float(row.get("Low"))
            adjusted_close = _clean_float(row.get("Adj Close"))
            volume = _clean_int(row.get("Volume"))
            dividend_amount = _clean_float(row.get("Dividends"))
            split_ratio = _clean_float(row.get("Stock Splits"))
            if dividend_amount == 0:
                dividend_amount = None
            if split_ratio == 0:
                split_ratio = None
            if close_price is None:
                continue
            point = PriceHistoryPoint(
                timestamp=timestamp,
                price=close_price,
                open_price=open_price,
                high_price=high_price,
                low_price=low_price,
                close_price=close_price,
                adjusted_close=adjusted_close,
                volume=volume,
                market_cap=None,
                dividend_amount=dividend_amount,
                split_ratio=split_ratio,
                source="yahoo_finance",
                data_quality=DataQuality.GOOD,
            )
            point_date = timestamp.date()
            if point_date < start_date:
                last_point = point
                continue
            if point_date > end_date:
                continue
            points_by_date[point_date] = point

        history: list[PriceHistoryPoint] = []
        current_date = start_date
        while current_date <= end_date:
            point = points_by_date.get(current_date)
            if point is not None:
                history.append(point)
                last_point = point
            elif last_point is not None:
                last_price = last_point.close_price or last_point.price
                history.append(
                    PriceHistoryPoint(
                        timestamp=datetime.combine(current_date, datetime.min.time()),
                        price=last_price,
                        open_price=last_price,
                        high_price=last_price,
                        low_price=last_price,
                        close_price=last_price,
                        adjusted_close=last_point.adjusted_close or last_price,
                        volume=None,
                        market_cap=None,
                        dividend_amount=None,
                        split_ratio=None,
                        source="yahoo_finance",
                        data_quality=DataQuality.ESTIMATED,
                    )
                )
            current_date += timedelta(days=1)

        return history
