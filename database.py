from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import NullPool

from config import settings

# Get database URL from environment
DATABASE_URL = settings.database_url

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