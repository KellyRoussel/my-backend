from datetime import datetime
from sqlalchemy import Column, String, DateTime, ForeignKey, Integer, Text, Enum
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship
import enum

Base = declarative_base()


class AuthProvider(enum.Enum):
    GOOGLE = "GOOGLE"
    INSTAGRAM = "INSTAGRAM"


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
    access_token = Column(Text, nullable=False)
    token_type = Column(String, default="bearer")
    expires_in = Column(Integer, nullable=True)
    expires_at = Column(DateTime, nullable=True)
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