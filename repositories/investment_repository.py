"""Repository for Investment database operations."""
from datetime import date
from decimal import Decimal
from typing import List, Optional

from sqlalchemy.orm import Session

from models.database_models import Investment as DBInvestment, AssetType, MarketCapCategory


class InvestmentRepository:
    """Repository for Investment CRUD operations."""

    def __init__(self, db: Session):
        self.db = db

    def create(
        self,
        user_id: str,
        symbol: str,
        name: str,
        asset_type: AssetType,
        country: str,
        purchase_date: date,
        purchase_price: Decimal,
        quantity: Decimal,
        currency: str = "USD",
        sector: Optional[str] = None,
        industry: Optional[str] = None,
        market_cap_category: Optional[MarketCapCategory] = None,
        dividend_yield: Optional[Decimal] = None,
        expense_ratio: Optional[Decimal] = None,
        notes: Optional[str] = None,
    ) -> DBInvestment:
        investment = DBInvestment(
            user_id=user_id,
            symbol=symbol,
            name=name,
            asset_type=asset_type,
            country=country,
            purchase_date=purchase_date,
            purchase_price=purchase_price,
            quantity=quantity,
            currency=currency,
            sector=sector,
            industry=industry,
            market_cap_category=market_cap_category,
            dividend_yield=dividend_yield,
            expense_ratio=expense_ratio,
            notes=notes,
        )
        self.db.add(investment)
        self.db.commit()
        self.db.refresh(investment)
        return investment

    def get_by_id(self, investment_id: str) -> Optional[DBInvestment]:
        return self.db.query(DBInvestment).filter(DBInvestment.id == investment_id).first()

    def get_by_user(
        self,
        user_id: str,
        active_only: bool = True,
        skip: int = 0,
        limit: int = 100,
    ) -> List[DBInvestment]:
        query = self.db.query(DBInvestment).filter(DBInvestment.user_id == user_id)
        if active_only:
            query = query.filter(DBInvestment.is_active == True)
        return query.offset(skip).limit(limit).all()

    def get_by_symbol(self, user_id: str, symbol: str) -> List[DBInvestment]:
        return self.db.query(DBInvestment).filter(
            DBInvestment.user_id == user_id,
            DBInvestment.symbol == symbol,
            DBInvestment.is_active == True,
        ).all()

    def get_by_asset_type(self, user_id: str, asset_type: AssetType) -> List[DBInvestment]:
        return self.db.query(DBInvestment).filter(
            DBInvestment.user_id == user_id,
            DBInvestment.asset_type == asset_type,
            DBInvestment.is_active == True,
        ).all()

    def update(self, investment: DBInvestment) -> DBInvestment:
        self.db.commit()
        self.db.refresh(investment)
        return investment

    def deactivate(self, investment_id: str) -> bool:
        investment = self.get_by_id(investment_id)
        if investment:
            investment.is_active = False
            self.db.commit()
            return True
        return False

    def delete(self, investment_id: str) -> bool:
        investment = self.get_by_id(investment_id)
        if investment:
            self.db.delete(investment)
            self.db.commit()
            return True
        return False
