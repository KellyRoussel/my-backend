import secrets
import uuid
from datetime import datetime, timedelta
from typing import Dict
import httpx
from sqlalchemy.orm import Session
from fastapi import HTTPException
from starlette import status

from config import settings
from models.authentication import User as UserResponse
from models.database_models import User, InstagramToken, AuthState, AuthProvider
from dependencies.auth_services.base_auth_service import BaseAuthService


class InstaAuthService(BaseAuthService):

    async def get_auth_url(self, app: str, db: Session = None) -> str:
        # Generate state for CSRF protection
        state = secrets.token_urlsafe(32)

        # Store state in database if provided
        if db:
            expires_at = datetime.utcnow() + timedelta(minutes=10)
            auth_state = AuthState(
                state=state,
                app_name=app,
                provider=AuthProvider.INSTAGRAM.value,
                expires_at=expires_at
            )
            db.add(auth_state)
            db.commit()

        params = {
            "client_id": settings.insta_client_id,
            "redirect_uri": settings.auth_redirect_uri + f"/{app}",
            "response_type": "code",
            "scope": "instagram_business_basic instagram_business_content_publish",
            "state": state,
            "enable_fb_login": 0,
            "force_authentication": 1
        }

        query_string = "&".join([f"{key}={value}" for key, value in params.items()])
        auth_url = f"{settings.insta_auth_url}?{query_string}"

        return auth_url

    async def exchange_code_for_token(self, code: str, app: str, state: str = None, db: Session = None) -> str:
        # Validate state parameter if provided
        if state and db:
            print(f"==> AuthProvider.INSTAGRAM value: {AuthProvider.INSTAGRAM.value}")
            print(f"==> AuthProvider.INSTAGRAM: {AuthProvider.INSTAGRAM}")
            auth_state = db.query(AuthState).filter(
                AuthState.state == state,
                AuthState.app_name == app,
                AuthState.provider == AuthProvider.INSTAGRAM,
                AuthState.expires_at > datetime.utcnow()
            ).first()

            if not auth_state:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Invalid or expired state parameter"
                )

            # Clean up used state
            db.delete(auth_state)
            db.commit()

        if code.endswith("#_"):
            code = code[:-2]

        token_request_data = {
            "code": code,
            "client_id": settings.insta_client_id,
            "client_secret": settings.insta_client_secret,
            "redirect_uri": settings.auth_redirect_uri + f"/{app}",
            "grant_type": "authorization_code",
        }

        async with httpx.AsyncClient() as client:
            token_response = await client.post(settings.insta_token_url, data=token_request_data)
            token_response_data = token_response.json()

            if "error" in token_response_data:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Instagram authentication error: {token_response_data['error']}"
                )

        access_token = token_response_data["access_token"]
        print(f"🔵 token_response_data: {token_response_data}")

        # Get long-lived token
        try:
            long_lived_token = await self._get_long_lived_token(access_token)
            print(f"🔵 Long-lived token: {long_lived_token}")
        except Exception as e:
            print(f"🔴 Error getting long-lived token: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to get long-lived token"
            )

        return  long_lived_token

    async def get_user_info(self, access_token: str) -> UserResponse:
        async with httpx.AsyncClient() as client:
            url = f"{settings.insta_user_info_url}?fields=id,username,profile_picture_url&access_token={access_token}"
            user_info_response = await client.get(url)
            user_info = user_info_response.json()

            if "error" in user_info:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Error getting user info: {user_info['error']}"
                )

            return UserResponse(
                email=user_info.get("email"),
                name=user_info.get("username"),
                picture=user_info.get("profile_picture_url"),
                id=user_info["id"]
            )

    async def save_user_and_token(self, user_info: UserResponse, access_token: str, db: Session) -> User:
        """Save or update user and their Instagram token"""

        # Check if user exists
        existing_user = db.query(User).filter(User.id == user_info.id).first()

        if existing_user:
            # Update existing user
            existing_user.username = user_info.name
            existing_user.profile_picture_url = user_info.picture
            existing_user.updated_at = datetime.utcnow()
            user_record = existing_user
        else:
            print("❤️ Creating new user")
            # Create new user
            user_record = User(
                id=str(uuid.uuid4()),
                email=user_info.email,
                username=user_info.name,
                display_name=user_info.name,
                profile_picture_url=user_info.picture,
                primary_provider=AuthProvider.INSTAGRAM
            )
            db.add(user_record)
            db.flush()
            db.refresh(user_record)
            print(f"🌟 New user id: {user_record.id}")

        # Deactivate old tokens
        db.query(InstagramToken).filter(
            InstagramToken.user_id == user_record.id,
            InstagramToken.is_active == "true"
        ).update({"is_active": "false"})

        # Save new Instagram token
        instagram_token = InstagramToken(
            user_id=user_record.id,
            access_token=access_token,
            scope="instagram_business_basic instagram_business_content_publish"
        )
        db.add(instagram_token)

        db.commit()
        db.refresh(user_record)

        return user_record

    async def refresh_token(self, access_token: str) -> str:
        async with httpx.AsyncClient() as client:
            url = f"{settings.insta_refresh_token_url}?grant_type=ig_refresh_token&access_token={access_token}&client_secret={settings.insta_client_secret}"
            refresh_token_response = await client.get(url)
            refreshed_token = refresh_token_response.json()

            if "error" in refreshed_token:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Error refreshing token: {refreshed_token['error']}"
                )

            return refreshed_token["access_token"]

    async def get_active_token(self, user_id: str, db: Session) -> InstagramToken:
        """Get active Instagram token for user"""
        token = db.query(InstagramToken).filter(
            InstagramToken.user_id == user_id,
            InstagramToken.is_active == "true"
        ).first()

        if not token:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="No active Instagram token found"
            )

        # Always refresh token if possible
        
        # Try to refresh token
        try:
            refreshed_access_token = await self.refresh_token(token.access_token)

            # Update token
            token.access_token = refreshed_access_token
            token.updated_at = datetime.utcnow()

            db.commit()

        except Exception as e:
            # Mark token as inactive
            token.is_active = "false"
            db.commit()
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Instagram token expired and refresh failed"
            )

        return token

    async def _get_long_lived_token(self, access_token: str) -> str:
        """Private method to get long-lived token"""
        async with httpx.AsyncClient() as client:
            url = f"{settings.insta_long_lived_token_url}?grant_type=ig_exchange_token&access_token={access_token}&client_secret={settings.insta_client_secret}"
            long_lived_token_response = await client.get(url)
            long_lived_token = long_lived_token_response.json()

            if "error" in long_lived_token:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Error getting long-lived token: {long_lived_token['error']}"
                )

        return long_lived_token["access_token"]


insta_auth_service = InstaAuthService()