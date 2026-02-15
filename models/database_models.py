from datetime import datetime
from uuid import uuid4
from sqlalchemy import (
    Column, String, DateTime, ForeignKey, Integer, Text, Enum,
    Date, Numeric, Boolean, UniqueConstraint,
)
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship
import enum

Base = declarative_base()


class AuthProvider(enum.Enum):
    GOOGLE = "GOOGLE"
    INSTAGRAM = "INSTAGRAM"


class RiskTolerance(enum.Enum):
    CONSERVATIVE = "conservative"
    MODERATE = "moderate"
    AGGRESSIVE = "aggressive"


class AssetType(enum.Enum):
    STOCK = "stock"
    ETF = "etf"
    CRYPTO = "crypto"
    BOND = "bond"
    COMMODITY = "commodity"
    REIT = "reit"
    MUTUAL_FUND = "mutual_fund"


class MarketCapCategory(enum.Enum):
    LARGE_CAP = "large_cap"
    MID_CAP = "mid_cap"
    SMALL_CAP = "small_cap"
    MICRO_CAP = "micro_cap"


class TransactionType(enum.Enum):
    BUY = "buy"
    SELL = "sell"
    DIVIDEND = "dividend"
    SPLIT = "split"
    BONUS = "bonus"


class User(Base):
    __tablename__ = "users"

    id = Column(String, primary_key=True)  # Provider user ID
    email = Column(String, nullable=True)
    username = Column(String, nullable=True)
    display_name = Column(String, nullable=True)
    profile_picture_url = Column(String, nullable=True)
    primary_provider = Column(Enum(AuthProvider), nullable=False)  # Which service they signed up with
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships to tokens
    instagram_tokens = relationship("InstagramToken", back_populates="user")
    google_tokens = relationship("GoogleToken", back_populates="user")
    my_backend_tokens = relationship("MyBackendToken", back_populates="user")


class InstagramToken(Base):
    __tablename__ = "instagram_tokens"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String, ForeignKey("users.id"), nullable=False)
    account_id = Column(String, nullable=False)  # Instagram Business Account ID
    access_token = Column(Text, nullable=False)
    scope = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    is_active = Column(String, default="true")

    # Relationship to user
    user = relationship("User", back_populates="instagram_tokens")


class GoogleToken(Base):
    __tablename__ = "google_tokens"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String, ForeignKey("users.id"), nullable=False)
    access_token = Column(Text, nullable=False)
    refresh_token = Column(Text, nullable=True)  # Google provides refresh tokens
    token_type = Column(String, default="bearer")
    expires_in = Column(Integer, nullable=True)
    expires_at = Column(DateTime, nullable=True)
    scope = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    is_active = Column(String, default="true")

    # Relationship to user
    user = relationship("User", back_populates="google_tokens")

class MyBackendToken(Base):
    __tablename__ = "my_backend_tokens"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String, ForeignKey("users.id"), nullable=False)
    access_token = Column(Text, nullable=False)
    token_type = Column(String, default="bearer")
    expires_in = Column(Integer, nullable=True)
    expires_at = Column(DateTime, nullable=True)
    scope = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    is_active = Column(String, default="true")

    # Relationship to user
    user = relationship("User", back_populates="my_backend_tokens")



class AuthState(Base):
    """Store OAuth state parameters for CSRF protection"""
    __tablename__ = "auth_states"

    state = Column(String, primary_key=True)
    app_name = Column(String, nullable=False)
    provider = Column(Enum(AuthProvider), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    expires_at = Column(DateTime, nullable=False)


class InvestmentProfile(Base):
    """Investment-specific user preferences."""
    __tablename__ = "investment_profiles"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String, ForeignKey("users.id"), nullable=False, unique=True)
    currency_preference = Column(String(3), nullable=False, default="USD")
    risk_tolerance = Column(Enum(RiskTolerance), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    user = relationship("User")


class Investment(Base):
    __tablename__ = "investments"

    id = Column(String, primary_key=True, default=lambda: str(uuid4()))
    user_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    symbol = Column(String(20), nullable=False)
    name = Column(String(255), nullable=False)
    asset_type = Column(Enum(AssetType), nullable=False)
    country = Column(String(3), nullable=False)
    sector = Column(String(100), nullable=True)
    industry = Column(String(100), nullable=True)
    market_cap_category = Column(Enum(MarketCapCategory), nullable=True)
    purchase_date = Column(Date, nullable=False)
    purchase_price = Column(Numeric(15, 4), nullable=False)
    quantity = Column(Numeric(15, 8), nullable=False)
    currency = Column(String(3), nullable=False, default="USD")
    dividend_yield = Column(Numeric(5, 4), nullable=True)
    expense_ratio = Column(Numeric(5, 4), nullable=True)
    notes = Column(Text, nullable=True)
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    user = relationship("User")
    transactions = relationship("InvestmentTransaction", back_populates="investment", cascade="all, delete-orphan")


class InvestmentTransaction(Base):
    __tablename__ = "investment_transactions"

    id = Column(String, primary_key=True, default=lambda: str(uuid4()))
    investment_id = Column(String, ForeignKey("investments.id", ondelete="CASCADE"), nullable=False, index=True)
    transaction_type = Column(Enum(TransactionType), nullable=False)
    transaction_date = Column(Date, nullable=False, index=True)
    quantity = Column(Numeric(15, 8), nullable=False)
    price = Column(Numeric(15, 4), nullable=False)
    total_amount = Column(Numeric(15, 2), nullable=False)
    fees = Column(Numeric(10, 2), nullable=False, default=0)
    currency = Column(String(3), nullable=False, default="USD")
    exchange_rate = Column(Numeric(10, 6), nullable=False, default=1.0)
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    investment = relationship("Investment", back_populates="transactions")