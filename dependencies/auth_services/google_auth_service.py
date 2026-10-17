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
from models.database_models import User, GoogleToken, AuthState, AuthProvider
from dependencies.auth_services.base_auth_service import BaseAuthService


class GoogleAuthService(BaseAuthService):

    def __init__(self, user_model=User, auth_state_model=AuthState, token_model=GoogleToken, provider=AuthProvider.GOOGLE):
        # Models are injected so that each app can store its users in its own schema.
        # token_model=None: the Google tokens are not stored (the app only uses Google to log in)
        self.user_model = user_model
        self.auth_state_model = auth_state_model
        self.token_model = token_model
        # Google member of the provider enum used by these models
        self.provider = provider

    async def get_auth_url(self, app: str, db: Session = None, override_redirect_uri: str = None) -> str:
        # Generate state for CSRF protection
        state = secrets.token_urlsafe(32)

        # Store state in database if provided
        if db:
            expires_at = datetime.utcnow() + timedelta(minutes=10)
            auth_state = self.auth_state_model(
                state=state,
                app_name=app,
                provider=self.provider.value,
                expires_at=expires_at
            )
            db.add(auth_state)
            db.commit()

        redirect_uri = override_redirect_uri or (settings.auth_redirect_uri + f"/{app}")
        params = {
            "client_id": settings.google_client_id,
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "scope": "email profile",
            "access_type": "offline",
            "include_granted_scopes": "true",
            "state": state,  # Add CSRF protection
        }

        query_string = "&".join([f"{key}={value}" for key, value in params.items()])
        auth_url = f"{settings.google_auth_url}?{query_string}"

        return auth_url

    async def exchange_code_for_token(self, code: str, app: str, state: str = None, db: Session = None, override_redirect_uri: str = None) -> Dict:
        # Validate state parameter if provided
        if state and db:
            auth_state = db.query(self.auth_state_model).filter(
                self.auth_state_model.state == state,
                self.auth_state_model.app_name == app,
                self.auth_state_model.provider == self.provider,
                self.auth_state_model.expires_at > datetime.utcnow()
            ).first()

            if not auth_state:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Invalid or expired state parameter"
                )

            # Clean up used state
            db.delete(auth_state)
            db.commit()

        redirect_uri = override_redirect_uri or (settings.auth_redirect_uri + f"/{app}")
        token_request_data = {
            "code": code,
            "client_id": settings.google_client_id,
            "client_secret": settings.google_client_secret,
            "redirect_uri": redirect_uri,
            "grant_type": "authorization_code",
        }

        async with httpx.AsyncClient() as client:
            token_response = await client.post(settings.google_token_url, data=token_request_data)
            token_response_data = token_response.json()

            if "error" in token_response_data:
                print(f"🔴 Google token exchange error: {token_response_data}")
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Google authentication error: {token_response_data['error']}"
                )

            return token_response_data

    async def get_user_info(self, access_token: str) -> UserResponse:
        async with httpx.AsyncClient() as client:
            headers = {"Authorization": f"Bearer {access_token['access_token']}"}
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

    async def save_user_and_token(self, user_info: UserResponse, token_info: Dict, db: Session) -> User:
        """Save or update user and their Google token"""

        # Check if user exists (by Google ID)
        existing_user = db.query(self.user_model).filter(self.user_model.id == user_info.id).first()

        if existing_user:
            # Update existing user
            existing_user.email = user_info.email
            existing_user.display_name = user_info.name
            existing_user.profile_picture_url = user_info.picture
            existing_user.updated_at = datetime.utcnow()
            user_record = existing_user
        else:
            # Check if user exists by email (they might have signed up with Instagram first)
            existing_user_by_email = db.query(self.user_model).filter(self.user_model.email == user_info.email).first()

            if existing_user_by_email:
                # Link Google account to existing user
                user_record = existing_user_by_email
                user_record.display_name = user_info.name
                user_record.profile_picture_url = user_info.picture
                user_record.updated_at = datetime.utcnow()
            else:
                # Create new user
                # create user_id as random uuid
                user_record = self.user_model(
                    id=str(uuid.uuid4()),
                    email=user_info.email,
                    username=user_info.email.split('@')[0],  # Use email prefix as username
                    display_name=user_info.name,
                    profile_picture_url=user_info.picture,
                    primary_provider=self.provider
                )
                db.add(user_record)
                db.flush()
                db.refresh(user_record)

        if self.token_model is not None:
            # Calculate expiration time
            expires_at = None
            if "expires_in" in token_info:
                expires_at = datetime.utcnow() + timedelta(seconds=token_info["expires_in"])

            # Deactivate old Google tokens
            db.query(self.token_model).filter(
                self.token_model.user_id == user_record.id,
                self.token_model.is_active == "true"
            ).update({"is_active": "false"})

            # Save new Google token
            google_token = self.token_model(
                user_id=user_record.id,
                access_token=token_info["access_token"],
                refresh_token=token_info.get("refresh_token"),  # Google provides refresh tokens
                token_type=token_info.get("token_type", "refresh"),
                expires_in=token_info.get("expires_in"),
                expires_at=expires_at,
                scope=token_info.get("scope", "email profile")
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
        token = db.query(self.token_model).filter(
            self.token_model.user_id == user_id,
            self.token_model.is_active == "true"
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