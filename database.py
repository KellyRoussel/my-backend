from urllib.parse import urlparse, quote, urlunparse

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import NullPool

from config import settings


def _sanitize_db_url(url: str) -> str:
    """URL-encode the password in a database URL to handle special characters."""
    parsed = urlparse(url)
    if parsed.password:
        encoded_password = quote(parsed.password, safe="")
        netloc = f"{parsed.username}:{encoded_password}@{parsed.hostname}"
        if parsed.port:
            netloc += f":{parsed.port}"
        return urlunparse(parsed._replace(netloc=netloc))
    return url


# Get database URL from environment
DATABASE_URL = _sanitize_db_url(settings.database_url)

# Create engine
engine = create_engine(
    DATABASE_URL,
    poolclass=NullPool,  # Good for free tier to avoid connection limits
    echo=False,  # Set to True for debugging SQL queries
)

# Create session factory
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Dependency to get database session
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()