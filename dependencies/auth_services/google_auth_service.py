import secrets
from datetime import datetime, timedelta
from typing import Dict
import httpx
from sqlalchemy.orm import Session
from fastapi import HTTPException
from starlette import status

from config import settings
from models.authentication import User as UserResponse
from models.database_models import User, GoogleToken, AuthState, AuthProvider
from dependencies.auth_services.base_auth_service import BaseAuthService


class GoogleAuthService(BaseAuthService):

    async def get_auth_url(self, app: str, db: Session = None) -> str:
        # Generate state for CSRF protection
        state = secrets.token_urlsafe(32)

        # Store state in database if provided
        if db:
            expires_at = datetime.utcnow() + timedelta(minutes=10)
            auth_state = AuthState(
                state=state,
                app_name=app,
                provider=AuthProvider.GOOGLE.value,
                expires_at=expires_at
            )
            db.add(auth_state)
            db.commit()

        params = {
            "client_id": settings.google_client_id,
            "redirect_uri": settings.auth_redirect_uri + f"/{app}",
            "response_type": "code",
            "scope": "email profile",
            "access_type": "offline",
            "include_granted_scopes": "true",
            "state": state,  # Add CSRF protection
        }

        query_string = "&".join([f"{key}={value}" for key, value in params.items()])
        auth_url = f"{settings.google_auth_url}?{query_string}"

        return auth_url

    async def exchange_code_for_token(self, code: str, app: str, state: str = None, db: Session = None) -> Dict:
        # Validate state parameter if provided
        if state and db:
            auth_state = db.query(AuthState).filter(
                AuthState.state == state,
                AuthState.app_name == app,
                AuthState.provider == AuthProvider.GOOGLE,
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

        token_request_data = {
            "code": code,
            "client_id": settings.google_client_id,
            "client_secret": settings.google_client_secret,
            "redirect_uri": settings.auth_redirect_uri + f"/{app}",
            "grant_type": "authorization_code",
        }

        async with httpx.AsyncClient() as client:
            token_response = await client.post(settings.google_token_url, data=token_request_data)
            token_response_data = token_response.json()

            if "error" in token_response_data:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Google authentication error: {token_response_data['error']}"
                )

            return token_response_data

    async def get_user_info(self, access_token: str) -> UserResponse:
        async with httpx.AsyncClient() as client:
            headers = {"Authorization": f"Bearer {access_token}"}
            user_info_response = await client.get(settings.google_user_info_url, headers=headers)
            user_info = user_info_response.json()

            if "error" in user_info:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Error getting user info: {user_info['error']}"
                )

            return UserResponse(
                email=user_info["email"],
                name=user_info.get("name"),
                picture=user_info.get("picture"),
                id=user_info["sub"]
            )

    async def save_user_and_token(self, user_info: UserResponse, token_data: Dict, db: Session) -> User:
        """Save or update user and their Google token"""

        # Check if user exists (by Google ID)
        existing_user = db.query(User).filter(User.id == user_info.id).first()

        if existing_user:
            # Update existing user
            existing_user.email = user_info.email
            existing_user.display_name = user_info.name
            existing_user.profile_picture_url = user_info.picture
            existing_user.updated_at = datetime.utcnow()
            user_record = existing_user
        else:
            # Check if user exists by email (they might have signed up with Instagram first)
            existing_user_by_email = db.query(User).filter(User.email == user_info.email).first()

            if existing_user_by_email:
                # Link Google account to existing user
                user_record = existing_user_by_email
                user_record.display_name = user_info.name
                user_record.profile_picture_url = user_info.picture
                user_record.updated_at = datetime.utcnow()
            else:
                # Create new user
                user_record = User(
                    id=user_info.id,
                    email=user_info.email,
                    username=user_info.email.split('@')[0],  # Use email prefix as username
                    display_name=user_info.name,
                    profile_picture_url=user_info.picture,
                    primary_provider=AuthProvider.GOOGLE.value
                )
                db.add(user_record)

        # Calculate expiration time
        expires_at = None
        if "expires_in" in token_data:
            expires_at = datetime.utcnow() + timedelta(seconds=token_data["expires_in"])

        # Deactivate old Google tokens
        db.query(GoogleToken).filter(
            GoogleToken.user_id == user_record.id,
            GoogleToken.is_active == "true"
        ).update({"is_active": "false"})

        # Save new Google token
        google_token = GoogleToken(
            user_id=user_record.id,
            access_token=token_data["access_token"],
            refresh_token=token_data.get("refresh_token"),  # Google provides refresh tokens
            token_type=token_data.get("token_type", "bearer"),
            expires_in=token_data.get("expires_in"),
            expires_at=expires_at,
            scope=token_data.get("scope", "email profile")
        )
        db.add(google_token)

        db.commit()
        db.refresh(user_record)

        return user_record

    async def refresh_token(self, refresh_token: str) -> Dict:
        """Refresh Google access token using refresh token"""
        if not refresh_token:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No refresh token available"
            )

        token_request_data = {
            "client_id": settings.google_client_id,
            "client_secret": settings.google_client_secret,
            "refresh_token": refresh_token,
            "grant_type": "refresh_token",
        }

        async with httpx.AsyncClient() as client:
            token_response = await client.post(settings.google_token_url, data=token_request_data)
            refreshed_token = token_response.json()

            if "error" in refreshed_token:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Error refreshing Google token: {refreshed_token['error']}"
                )

            return refreshed_token

    async def get_active_token(self, user_id: str, db: Session) -> GoogleToken:
        """Get active Google token for user"""
        token = db.query(GoogleToken).filter(
            GoogleToken.user_id == user_id,
            GoogleToken.is_active == "true"
        ).first()

        if not token:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="No active Google token found"
            )

        # Check if token is expired
        if token.expires_at and token.expires_at < datetime.utcnow():
            # Try to refresh token
            if token.refresh_token:
                try:
                    refreshed_data = await self.refresh_token(token.refresh_token)

                    # Update token
                    token.access_token = refreshed_data["access_token"]
                    if "expires_in" in refreshed_data:
                        token.expires_at = datetime.utcnow() + timedelta(seconds=refreshed_data["expires_in"])

                    # Update refresh token if provided (Google sometimes provides new ones)
                    if "refresh_token" in refreshed_data:
                        token.refresh_token = refreshed_data["refresh_token"]

                    token.updated_at = datetime.utcnow()

                    db.commit()

                except Exception as e:
                    # Mark token as inactive
                    token.is_active = "false"
                    db.commit()
                    raise HTTPException(
                        status_code=status.HTTP_401_UNAUTHORIZED,
                        detail="Google token expired and refresh failed"
                    )
            else:
                # No refresh token available
                token.is_active = "false"
                db.commit()
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Google token expired and no refresh token available"
                )

        return token


google_auth_service = GoogleAuthService()