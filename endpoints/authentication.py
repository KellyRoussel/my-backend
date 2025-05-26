from datetime import timedelta, datetime
from typing import Optional, Dict

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
from models.database_models import User, AuthProvider, MyBackendToken

authentication_router = APIRouter(tags=["Authentication"])


def create_access_token(data: dict, type="access", expires_delta: Optional[timedelta] = None):
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.now() + expires_delta
    else:
        expire = datetime.now() + timedelta(minutes=settings.access_token_expire_minutes)
    to_encode.update({"exp": expire, "type": type})
    encoded_jwt = jwt.encode(to_encode, settings.secret_key, algorithm=settings.algorithm)
    return encoded_jwt

async def save_my_backend_refresh_token(user_id: str, refresh_token_data: Dict, db: Session) -> User:
    """Save or update user and their Google token"""

    # Check if user exists (by Google ID)
    user_record = db.query(User).filter(User.id == user_id).first()

    if not user_record:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User not found"
        )


    # Calculate expiration time
    expires_at = None
    if "expires_in" in refresh_token_data:
        expires_at = datetime.utcnow() + timedelta(seconds=refresh_token_data["expires_in"])

    # Deactivate old backend tokens
    db.query(MyBackendToken).filter(
        MyBackendToken.user_id == user_id,
        MyBackendToken.is_active == "true"
    ).update({"is_active": "false"})

    # Save new MyBackend token
    my_backend_token = MyBackendToken(
        user_id=user_record.id,
        access_token=refresh_token_data["access_token"],
        refresh_token=refresh_token_data.get("refresh_token"),  # Google provides refresh tokens
        token_type=refresh_token_data.get("token_type", "refresh"),
        expires_in=refresh_token_data.get("expires_in"),
        expires_at=expires_at,
        scope=refresh_token_data.get("scope", "email profile")
    )
    db.add(my_backend_token)

    db.commit()

    return user_record


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
# used for redirecting back to the app
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
    if service == AuthProvider.GOOGLE.value:
        auth_service = google_auth_service
    elif service == AuthProvider.INSTAGRAM.value:
        auth_service = insta_auth_service
    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid service. Must be 'GOOGLE' or 'INSTAGRAM'"
        )

    try:
        # Exchange code for token
        print(f"🙂 Exchanging code for token for {service}")
        token_data = await auth_service.exchange_code_for_token(code, app, state, db)
        service_access_token = token_data["access_token"]
        service_refresh_token = token_data["refresh_token"]

        # Get user info
        print(f"🙂 Collecting user info for {service}")
        user_info = await auth_service.get_user_info(service_access_token)

        # Save user and token to database
        print(f"🙂 Saving user and refresh token to DB")
        user_record = await auth_service.save_user_and_token(user_info, service_refresh_token, db)

        # Create access token
        print(f"🙂 Creating access token")
        access_token = create_access_token({"sub": str(user_record.id)}, type="access", expires_delta=timedelta(minutes=settings.access_token_expire_minutes))

        # Create refresh token
        print(f"🙂 Creating refresh token")
        refresh_token = create_access_token({"sub": str(user_record.id)}, type="refresh", expires_delta=timedelta(days=settings.refresh_token_expire_days))

        # Save refresh token to database
        print(f"🙂 Saving refresh token to DB")
        await save_my_backend_refresh_token(user_record, refresh_token, db)

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


@authentication_router.post("/auth/refresh-token")
async def get_refresh_token(request: Request, db: Session = Depends(get_db)):
    refresh_token = request.headers.get("X-Refresh-Token")
    if not refresh_token:
        raise HTTPException(status_code=400, detail="Missing refresh token")

    try:
        payload = jwt.decode(refresh_token, settings.secret_key, algorithms=[settings.algorithm])
        user_id = payload.get("sub")
        if not user_id:
            raise HTTPException(status_code=401, detail="Invalid refresh token")

        # Optional: Check token against database (e.g., revoked or not)
        # Optional: Ensure the refresh token hasn’t expired manually

        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        new_access_token = create_access_token(
            data={
                "sub": user.id,
                "email": user.email,
                "name": user.display_name,
                "picture": user.profile_picture_url,
                "provider": user.primary_provider.value
            }
        )

        return {"access_token": new_access_token}

    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Refresh token expired")
    except jwt.PyJWTError:
        raise HTTPException(status_code=401, detail="Invalid refresh token")
