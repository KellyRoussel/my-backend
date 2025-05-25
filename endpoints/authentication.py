from datetime import timedelta, datetime
from typing import Optional

import jwt
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from starlette.requests import Request
from starlette.responses import RedirectResponse
from starlette import status

from config import settings
from database import get_db
from dependencies.auth_services.google_auth_service import google_auth_service
from dependencies.auth_services.insta_auth_service import insta_auth_service
from models.database_models import User

authentication_router = APIRouter(tags=["Authentication"])


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.now() + expires_delta
    else:
        expire = datetime.now() + timedelta(minutes=settings.access_token_expire_minutes)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, settings.secret_key, algorithm=settings.algorithm)
    return encoded_jwt


# Google Authentication Endpoints
@authentication_router.get("/login/google/{app}")
async def get_google_auth_url(app: str, db: Session = Depends(get_db)):
    auth_url = await google_auth_service.get_auth_url(app, db)
    return {"authorization_url": auth_url}


# Instagram Authentication Endpoints
@authentication_router.get("/login/insta/{app}")
async def get_insta_auth_url(app: str, db: Session = Depends(get_db)):
    auth_url = await insta_auth_service.get_auth_url(app, db)
    return {"authorization_url": auth_url}


# Unified callback endpoint for both providers
@authentication_router.get("/auth/callback/{app}")
async def auth_callback(request: Request, app: str):
    code = request.query_params.get("code")
    state = request.query_params.get("state")
    error = request.query_params.get("error")

    if error:
        return RedirectResponse(f"{app}://auth?error={error}")

    if not code:
        return RedirectResponse(f"{app}://auth?error=no_code")

    # Redirect back to the app with the code and state
    redirect_url = f"{app}://auth?code={code}"
    if state:
        redirect_url += f"&state={state}"

    return RedirectResponse(redirect_url)


# Unified token exchange endpoint
@authentication_router.get("/auth/exchange/{app}")
async def exchange_code(
        app: str,
        code: str,
        service: str,  # 'google' or 'instagram'
        state: str = None,
        db: Session = Depends(get_db)
):
    # Select the appropriate service
    if service == "google":
        auth_service = google_auth_service
    elif service == "instagram":
        auth_service = insta_auth_service
    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid service. Must be 'google' or 'instagram'"
        )

    try:
        # Exchange code for token
        token_data = await auth_service.exchange_code_for_token(code, app, state, db)

        # Get user info
        user_info = await auth_service.get_user_info(token_data["access_token"])

        # Save user and token to database
        user_record = await auth_service.save_user_and_token(user_info, token_data, db)

        # Create JWT token
        access_token_expires = timedelta(minutes=settings.access_token_expire_minutes)
        access_token = create_access_token(
            data={
                "sub": user_record.id,
                "email": user_record.email,
                "name": user_record.display_name,
                "picture": user_record.profile_picture_url,
                "provider": user_record.primary_provider.value
            },
            expires_delta=access_token_expires
        )

        return {
            "access_token": access_token,
            "token_type": "bearer",
            "user": {
                "id": user_record.id,
                "email": user_record.email,
                "name": user_record.display_name,
                "username": user_record.username,
                "picture": user_record.profile_picture_url,
                "provider": user_record.primary_provider.value
            }
        }

    except HTTPException:
        raise
    except Exception as e:
        print(f"🔴 Error in token exchange: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Authentication failed"
        )


# Token refresh endpoints
@authentication_router.post("/auth/refresh-google/{user_id}")
async def refresh_google_token(
        user_id: str,
        db: Session = Depends(get_db)
):
    """Manually refresh a user's Google token"""
    try:
        # Get the current active token (this will automatically refresh if needed)
        token = await google_auth_service.get_active_token(user_id, db)

        return {
            "message": "Google token refreshed successfully",
            "token_info": {
                "expires_at": token.expires_at.isoformat() if token.expires_at else None,
                "scope": token.scope,
                "is_active": token.is_active
            }
        }

    except HTTPException:
        raise
    except Exception as e:
        print(f"🔴 Error refreshing Google token: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to refresh Google token"
        )


@authentication_router.post("/auth/refresh-instagram/{user_id}")
async def refresh_instagram_token(
        user_id: str,
        db: Session = Depends(get_db)
):
    """Manually refresh a user's Instagram token"""
    try:
        # Get the current active token (this will automatically refresh if needed)
        token = await insta_auth_service.get_active_token(user_id, db)

        return {
            "message": "Instagram token refreshed successfully",
            "token_info": {
                "expires_at": token.expires_at.isoformat() if token.expires_at else None,
                "scope": token.scope,
                "is_active": token.is_active
            }
        }

    except HTTPException:
        raise
    except Exception as e:
        print(f"🔴 Error refreshing Instagram token: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to refresh Instagram token"
        )


# Get user's active tokens
@authentication_router.get("/auth/tokens/{user_id}")
async def get_user_tokens(
        user_id: str,
        db: Session = Depends(get_db)
):
    """Get all active tokens for a user"""
    try:
        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found"
            )

        tokens_info = {
            "user_id": user_id,
            "google_token": None,
            "instagram_token": None
        }

        # Check for Google token
        try:
            google_token = await google_auth_service.get_active_token(user_id, db)
            tokens_info["google_token"] = {
                "expires_at": google_token.expires_at.isoformat() if google_token.expires_at else None,
                "scope": google_token.scope,
                "is_active": google_token.is_active,
                "has_refresh_token": google_token.refresh_token is not None
            }
        except HTTPException:
            # No active Google token
            pass

        # Check for Instagram token
        try:
            instagram_token = await insta_auth_service.get_active_token(user_id, db)
            tokens_info["instagram_token"] = {
                "expires_at": instagram_token.expires_at.isoformat() if instagram_token.expires_at else None,
                "scope": instagram_token.scope,
                "is_active": instagram_token.is_active
            }
        except HTTPException:
            # No active Instagram token
            pass

        return tokens_info

    except HTTPException:
        raise
    except Exception as e:
        print(f"🔴 Error getting user tokens: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get user tokens"
        )


# Revoke tokens
@authentication_router.delete("/auth/revoke/{user_id}/{provider}")
async def revoke_token(
        user_id: str,
        provider: str,  # 'google' or 'instagram'
        db: Session = Depends(get_db)
):
    """Revoke (deactivate) a user's token for a specific provider"""
    if provider not in ["google", "instagram"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid provider. Must be 'google' or 'instagram'"
        )

    try:
        if provider == "google":
            from models.database_models import GoogleToken
            db.query(GoogleToken).filter(
                GoogleToken.user_id == user_id,
                GoogleToken.is_active == "true"
            ).update({"is_active": "false"})
        else:  # instagram
            from models.database_models import InstagramToken
            db.query(InstagramToken).filter(
                InstagramToken.user_id == user_id,
                InstagramToken.is_active == "true"
            ).update({"is_active": "false"})

        db.commit()

        return {
            "message": f"{provider.capitalize()} token revoked successfully",
            "user_id": user_id,
            "provider": provider
        }

    except Exception as e:
        print(f"🔴 Error revoking {provider} token: {e}")
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to revoke {provider} token"
        )


# Health check endpoint for tokens
@authentication_router.get("/auth/health/{user_id}")
async def check_tokens_health(
        user_id: str,
        db: Session = Depends(get_db)
):
    """Check the health status of all user tokens"""
    try:
        health_status = {
            "user_id": user_id,
            "google": {"status": "inactive", "needs_refresh": False, "expires_soon": False},
            "instagram": {"status": "inactive", "needs_refresh": False, "expires_soon": False}
        }

        # Check Google token
        try:
            google_token = await google_auth_service.get_active_token(user_id, db)
            health_status["google"]["status"] = "active"

            if google_token.expires_at:
                time_until_expiry = google_token.expires_at - datetime.utcnow()
                if time_until_expiry.total_seconds() < 3600:  # Less than 1 hour
                    health_status["google"]["expires_soon"] = True
                if time_until_expiry.total_seconds() < 0:  # Already expired
                    health_status["google"]["needs_refresh"] = True

        except HTTPException:
            pass

        # Check Instagram token
        try:
            instagram_token = await insta_auth_service.get_active_token(user_id, db)
            health_status["instagram"]["status"] = "active"

            if instagram_token.expires_at:
                time_until_expiry = instagram_token.expires_at - datetime.utcnow()
                if time_until_expiry.total_seconds() < 3600:  # Less than 1 hour
                    health_status["instagram"]["expires_soon"] = True
                if time_until_expiry.total_seconds() < 0:  # Already expired
                    health_status["instagram"]["needs_refresh"] = True

        except HTTPException:
            pass

        return health_status

    except Exception as e:
        print(f"🔴 Error checking token health: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to check token health"
        )