"""Service for calculating portfolio metrics on the fly."""
from datetime import date
from decimal import Decimal
from typing import Dict, List, Optional

from sqlalchemy.orm import Session

from dependencies.investment.yahoo_finance import YahooFinanceClient
from dependencies.investment.currency_converter import CurrencyConverter
from models.database_models import Investment as InvestmentModel
from models.investment import (
    PortfolioMetrics,
    PortfolioBreakdownItem,
    PortfolioBreakdownMap,
    PortfolioPerformer,
    PortfolioPerformers,
    DiversificationScore,
    InvestmentMetrics,
)


class PortfolioCalculator:
    """Service for calculating real-time portfolio metrics."""

    def __init__(self, db: Session):
        self.db = db

    def _fetch_fresh_prices(self, investments: List[InvestmentModel]) -> Dict[str, Optional[Decimal]]:
        prices: Dict[str, Optional[Decimal]] = {}
        for inv in investments:
            if inv.symbol not in prices:
                fresh_price = YahooFinanceClient.get_latest_close(inv.symbol)
                prices[inv.symbol] = Decimal(str(fresh_price)) if fresh_price is not None else None
        return prices

    def calculate_portfolio_metrics(self, user_id: str, user_currency: str = "USD") -> PortfolioMetrics:
        investments = self.db.query(InvestmentModel).filter(
            InvestmentModel.user_id == user_id,
            InvestmentModel.is_active == True,
        ).all()

        if not investments:
            return self._empty_portfolio_metrics(user_id, user_currency)

        fresh_prices = self._fetch_fresh_prices(investments)

        total_value = Decimal(0)
        total_cost = Decimal(0)

        for inv in investments:
            current_price = fresh_prices.get(inv.symbol)
            if current_price is not None:
                current_value_original = current_price * inv.quantity
                rate = CurrencyConverter.get_exchange_rate(inv.currency, user_currency, date.today())
                if rate:
                    total_value += current_value_original * Decimal(str(rate))
                else:
                    total_value += current_value_original

            cost_original = inv.purchase_price * inv.quantity
            rate = CurrencyConverter.get_exchange_rate(inv.currency, user_currency, inv.purchase_date)
            if rate:
                total_cost += cost_original * Decimal(str(rate))
            else:
                total_cost += cost_original

        total_gain_loss = total_value - total_cost
        total_gain_loss_percent = (total_gain_loss / total_cost) * 100 if total_cost > 0 else Decimal(0)

        breakdown_by_country = self._calculate_country_breakdown(investments, total_value, user_currency, fresh_prices)
        breakdown_by_sector = self._calculate_sector_breakdown(investments, total_value, user_currency, fresh_prices)
        breakdown_by_asset_type = self._calculate_asset_type_breakdown(investments, total_value, user_currency, fresh_prices)

        performers = self._calculate_performers(investments, user_currency, fresh_prices)

        diversification_score = self._calculate_diversification_score(
            breakdown_by_country, breakdown_by_sector, breakdown_by_asset_type
        )

        return PortfolioMetrics(
            user_id=user_id,
            total_value=total_value,
            total_cost=total_cost,
            total_gain_loss=total_gain_loss,
            total_gain_loss_percent=total_gain_loss_percent,
            diversification_score=diversification_score.score,
            investment_count=len(investments),
            breakdown_by_country=breakdown_by_country.breakdowns,
            breakdown_by_sector=breakdown_by_sector.breakdowns,
            breakdown_by_asset_type=breakdown_by_asset_type.breakdowns,
            top_performers=performers.top_performers,
            worst_performers=performers.worst_performers,
            currency=user_currency,
        )

    def _empty_portfolio_metrics(self, user_id: str, user_currency: str = "USD") -> PortfolioMetrics:
        return PortfolioMetrics(
            user_id=user_id,
            total_value=Decimal(0),
            total_cost=Decimal(0),
            total_gain_loss=Decimal(0),
            total_gain_loss_percent=Decimal(0),
            diversification_score=0,
            investment_count=0,
            breakdown_by_country={},
            breakdown_by_sector={},
            breakdown_by_asset_type={},
            top_performers=[],
            worst_performers=[],
            currency=user_currency,
        )

    def _calculate_country_breakdown(
        self,
        investments: List[InvestmentModel],
        total_value: Decimal,
        user_currency: str,
        fresh_prices: Dict[str, Optional[Decimal]],
    ) -> PortfolioBreakdownMap:
        country_totals: Dict[str, Decimal] = {}
        country_counts: Dict[str, int] = {}

        for inv in investments:
            current_price = fresh_prices.get(inv.symbol)
            if current_price is None:
                continue
            country = inv.country
            value_original = current_price * inv.quantity
            rate = CurrencyConverter.get_exchange_rate(inv.currency, user_currency, date.today())
            value = value_original * Decimal(str(rate)) if rate else value_original

            if country not in country_totals:
                country_totals[country] = Decimal(0)
                country_counts[country] = 0
            country_totals[country] += value
            country_counts[country] += 1

        return PortfolioBreakdownMap(
            breakdowns={
                country: PortfolioBreakdownItem(
                    value=float(total),
                    percentage=float((total / total_value) * 100) if total_value > 0 else 0,
                    count=country_counts[country],
                )
                for country, total in country_totals.items()
            }
        )

    def _calculate_sector_breakdown(
        self,
        investments: List[InvestmentModel],
        total_value: Decimal,
        user_currency: str,
        fresh_prices: Dict[str, Optional[Decimal]],
    ) -> PortfolioBreakdownMap:
        sector_totals: Dict[str, Decimal] = {}
        sector_counts: Dict[str, int] = {}

        for inv in investments:
            current_price = fresh_prices.get(inv.symbol)
            if current_price is None or inv.sector is None:
                continue
            sector = inv.sector
            value_original = current_price * inv.quantity
            rate = CurrencyConverter.get_exchange_rate(inv.currency, user_currency, date.today())
            value = value_original * Decimal(str(rate)) if rate else value_original

            if sector not in sector_totals:
                sector_totals[sector] = Decimal(0)
                sector_counts[sector] = 0
            sector_totals[sector] += value
            sector_counts[sector] += 1

        return PortfolioBreakdownMap(
            breakdowns={
                sector: PortfolioBreakdownItem(
                    value=float(total),
                    percentage=float((total / total_value) * 100) if total_value > 0 else 0,
                    count=sector_counts[sector],
                )
                for sector, total in sector_totals.items()
            }
        )

    def _calculate_asset_type_breakdown(
        self,
        investments: List[InvestmentModel],
        total_value: Decimal,
        user_currency: str,
        fresh_prices: Dict[str, Optional[Decimal]],
    ) -> PortfolioBreakdownMap:
        asset_type_totals: Dict[str, Decimal] = {"stock": Decimal(0), "etf": Decimal(0)}
        asset_type_counts: Dict[str, int] = {"stock": 0, "etf": 0}

        for inv in investments:
            current_price = fresh_prices.get(inv.symbol)
            if current_price is None:
                continue
            asset_type = inv.asset_type.value
            value_original = current_price * inv.quantity
            rate = CurrencyConverter.get_exchange_rate(inv.currency, user_currency, date.today())
            value = value_original * Decimal(str(rate)) if rate else value_original

            if asset_type not in asset_type_totals:
                asset_type_totals[asset_type] = Decimal(0)
                asset_type_counts[asset_type] = 0
            asset_type_totals[asset_type] += value
            asset_type_counts[asset_type] += 1

        return PortfolioBreakdownMap(
            breakdowns={
                asset_type: PortfolioBreakdownItem(
                    value=float(total),
                    percentage=float((total / total_value) * 100) if total_value > 0 else 0,
                    count=asset_type_counts[asset_type],
                )
                for asset_type, total in asset_type_totals.items()
            }
        )

    def _calculate_performers(
        self,
        investments: List[InvestmentModel],
        user_currency: str,
        fresh_prices: Dict[str, Optional[Decimal]],
    ) -> PortfolioPerformers:
        investments_with_performance = [
            inv for inv in investments
            if fresh_prices.get(inv.symbol) is not None and fresh_prices.get(inv.symbol) > 0
        ]

        performances: List[PortfolioPerformer] = []
        for inv in investments_with_performance:
            current_price = fresh_prices.get(inv.symbol)
            cost_original = inv.purchase_price * inv.quantity
            current_value_original = current_price * inv.quantity

            cost_rate = CurrencyConverter.get_exchange_rate(inv.currency, user_currency, inv.purchase_date)
            current_rate = CurrencyConverter.get_exchange_rate(inv.currency, user_currency, date.today())

            cost = cost_original * Decimal(str(cost_rate)) if cost_rate else cost_original
            current_value = current_value_original * Decimal(str(current_rate)) if current_rate else current_value_original

            if cost > 0:
                gain_loss_percent = ((current_value - cost) / cost) * 100
                performances.append(
                    PortfolioPerformer(
                        investment_id=inv.id,
                        symbol=inv.symbol,
                        name=inv.name,
                        gain_loss_percent=gain_loss_percent,
                    )
                )

        performances.sort(key=lambda p: p.gain_loss_percent, reverse=True)

        return PortfolioPerformers(
            top_performers=performances[:3],
            worst_performers=performances[-3:],
        )

    def _calculate_diversification_score(
        self,
        country_breakdown: PortfolioBreakdownMap,
        sector_breakdown: PortfolioBreakdownMap,
        asset_type_breakdown: PortfolioBreakdownMap,
    ) -> DiversificationScore:
        country_herfindahl = sum(
            (breakdown.percentage / 100) ** 2
            for breakdown in country_breakdown.breakdowns.values()
        )
        sector_herfindahl = sum(
            (breakdown.percentage / 100) ** 2
            for breakdown in sector_breakdown.breakdowns.values()
        )
        asset_type_herfindahl = sum(
            (breakdown.percentage / 100) ** 2
            for breakdown in asset_type_breakdown.breakdowns.values()
        )

        avg_herfindahl = (country_herfindahl + sector_herfindahl + asset_type_herfindahl) / 3
        diversification_score = (1 - avg_herfindahl) * 100

        return DiversificationScore(score=max(0, diversification_score))

    def calculate_investment_metrics(
        self,
        investment: InvestmentModel,
        user_currency: str = None,
    ) -> InvestmentMetrics:
        fresh_price = YahooFinanceClient.get_latest_close(investment.symbol)
        current_price = Decimal(str(fresh_price)) if fresh_price is not None else None

        if current_price is None:
            return InvestmentMetrics(
                current_value=None,
                gain_loss=None,
                gain_loss_percent=None,
                performance_status="unknown",
            )

        current_value = current_price * investment.quantity
        total_cost = investment.purchase_price * investment.quantity

        if user_currency and user_currency != investment.currency:
            current_rate = CurrencyConverter.get_exchange_rate(investment.currency, user_currency, date.today())
            if current_rate:
                current_value = current_value * Decimal(str(current_rate))
            cost_rate = CurrencyConverter.get_exchange_rate(investment.currency, user_currency, investment.purchase_date)
            if cost_rate:
                total_cost = total_cost * Decimal(str(cost_rate))

        gain_loss = current_value - total_cost
        gain_loss_percent = (gain_loss / total_cost) * 100 if total_cost > 0 else 0

        if gain_loss_percent > 0:
            performance_status = "profitable"
        elif gain_loss_percent < 0:
            performance_status = "losing"
        else:
            performance_status = "neutral"

        return InvestmentMetrics(
            current_value=float(current_value),
            gain_loss=float(gain_loss),
            gain_loss_percent=float(gain_loss_percent),
            performance_status=performance_status,
        )
