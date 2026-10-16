"""Where each app stores its users and tokens.

Bobobidou has its own Postgres schema and role: its users and refresh tokens live
in `bobobidou.*` and are read through `BobobidouSessionLocal`. The personal apps
keep using the shared tables in `public`.

The app is carried by the `app` claim of the JWTs we issue, so that the
refresh endpoint and the auth dependencies know which store a token belongs to.
"""
from dataclasses import dataclass
from typing import Optional

from sqlalchemy.orm import sessionmaker

from database import SessionLocal, BobobidouSessionLocal
from dependencies.auth_handler import BOBOBIDOU_APP
from dependencies.auth_services.google_auth_service import GoogleAuthService, google_auth_service
from models.bobobidou_models import BobobidouUser, BobobidouRefreshToken, BobobidouAuthState
from models.database_models import User, MyBackendToken


@dataclass(frozen=True)
class AppAuthStore:
    session_factory: sessionmaker
    user_model: type
    refresh_token_model: type
    google_auth_service: GoogleAuthService
    supports_instagram: bool


PERSONAL_AUTH_STORE = AppAuthStore(
    session_factory=SessionLocal,
    user_model=User,
    refresh_token_model=MyBackendToken,
    google_auth_service=google_auth_service,
    supports_instagram=True,
)

BOBOBIDOU_AUTH_STORE = AppAuthStore(
    session_factory=BobobidouSessionLocal,
    user_model=BobobidouUser,
    refresh_token_model=BobobidouRefreshToken,
    # Bobobidou only uses Google to log in: its Google tokens are not stored
    google_auth_service=GoogleAuthService(
        user_model=BobobidouUser,
        auth_state_model=BobobidouAuthState,
        token_model=None,
    ),
    supports_instagram=False,
)


def get_auth_store(app: Optional[str]) -> AppAuthStore:
    return BOBOBIDOU_AUTH_STORE if app == BOBOBIDOU_APP else PERSONAL_AUTH_STORE


def get_app_db(app: str):
    """FastAPI dependency: database session of the app given in the `{app}` path parameter."""
    db = get_auth_store(app).session_factory()
    try:
        yield db
    finally:
        db.close()
