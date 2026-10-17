"""SQLAlchemy models of the Bobobidou app, isolated in the `bobobidou` Postgres schema.

They have their own declarative base so that nothing links them to the personal
backend tables in `public`: the `bobobidou_app` Postgres role only has access to
this schema.
"""
from datetime import datetime

from sqlalchemy import Column, String, DateTime, ForeignKey, Integer, Text, Enum, MetaData
from sqlalchemy.orm import declarative_base, relationship

from models.database_models import AuthProvider

BOBOBIDOU_SCHEMA = "bobobidou"

BobobidouBase = declarative_base(metadata=MetaData(schema=BOBOBIDOU_SCHEMA))


class BobobidouUser(BobobidouBase):
    __tablename__ = "users"

    id = Column(String, primary_key=True)
    email = Column(String, nullable=True, index=True)
    username = Column(String, nullable=True)
    display_name = Column(String, nullable=True)
    profile_picture_url = Column(String, nullable=True)
    primary_provider = Column(Enum(AuthProvider, name="authprovider", schema=BOBOBIDOU_SCHEMA), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class BobobidouRefreshToken(BobobidouBase):
    """Refresh tokens issued by the backend (equivalent of `public.my_backend_tokens`)."""
    __tablename__ = "refresh_tokens"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    access_token = Column(Text, nullable=False)
    token_type = Column(String, default="refresh")
    expires_in = Column(Integer, nullable=True)
    expires_at = Column(DateTime, nullable=True)
    scope = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    # Kept as "true"/"false" strings to share the token code with `public.my_backend_tokens`
    is_active = Column(String, default="true")

    user = relationship("BobobidouUser")


class BobobidouAuthState(BobobidouBase):
    """OAuth state parameters (CSRF protection) of the Bobobidou login flow."""
    __tablename__ = "auth_states"

    state = Column(String, primary_key=True)
    app_name = Column(String, nullable=False)
    provider = Column(Enum(AuthProvider, name="authprovider", schema=BOBOBIDOU_SCHEMA), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    expires_at = Column(DateTime, nullable=False)
