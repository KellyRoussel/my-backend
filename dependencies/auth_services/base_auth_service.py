from abc import ABC, abstractmethod
from typing import Dict, Optional
from sqlalchemy.orm import Session
from models.authentication import User as UserResponse


class BaseAuthService(ABC):
    """Abstract base class for OAuth authentication services"""

    @abstractmethod
    async def get_auth_url(self, app: str, db: Session = None) -> str:
        """Generate OAuth authorization URL"""
        pass

    @abstractmethod
    async def exchange_code_for_token(self, code: str, app: str, state: str = None, db: Session = None) -> Dict:
        """Exchange authorization code for access token"""
        pass

    @abstractmethod
    async def get_user_info(self, access_token: str) -> UserResponse:
        """Get user information using access token"""
        pass

    @abstractmethod
    async def save_user_and_token(self, user_info: UserResponse, refresh_token_data: Dict, db: Session) -> object:
        """Save or update user and their tokens in database"""
        pass

    @abstractmethod
    async def refresh_token(self, access_token: str) -> Dict:
        """Refresh access token"""
        pass

    @abstractmethod
    async def get_active_token(self, user_id: str, db: Session) -> object:
        """Get active token for user"""
        pass