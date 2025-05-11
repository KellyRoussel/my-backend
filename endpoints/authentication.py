from datetime import timedelta, datetime
from typing import Optional

import jwt
from fastapi import APIRouter
from starlette.requests import Request
from starlette.responses import RedirectResponse

from config import settings
from dependencies.google_auth_service import google_auth_service
from dependencies.insta_auth_service import insta_auth_service

authentication_router = APIRouter(tags=["Authentication"])
@authentication_router.get("/login/google/{app}")
async def get_google_auth_url(app: str):
    auth_url = await google_auth_service.get_auth_url(app)
    return {"authorization_url": auth_url}

@authentication_router.get("/login/insta/{app}")
async def get_insta_auth_url(app: str):
    auth_url = await insta_auth_service.get_auth_url(app)
    return {"authorization_url": auth_url}

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.now() + expires_delta
    else:
        expire = datetime.now() + timedelta(minutes=settings.access_token_expire_minutes)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, settings.secret_key, algorithm=settings.algorithm)
    return encoded_jwt

@authentication_router.get("/auth/callback/{app}")
async def auth_callback(request: Request, app: str):
    code = request.query_params.get("code")
    if not code:
        return {"error": "No code provided"}

    # Redirect back to the app with the code in the custom scheme
    return RedirectResponse(f"{app}://auth?code={code}")


@authentication_router.get("/auth/exchange/{app}")
async def exchange_code(app: str, code: str, service_str: str = 'google'):
    service = google_auth_service if service_str == "google" else insta_auth_service
    # Échanger le code contre un token
    token_data = await service.exchange_code_for_token(code, app)

    raw_access_token = token_data["access_token"]

    # Obtenir les informations utilisateur
    user = await service.get_user_info(raw_access_token)

    # Créer un JWT contenant les informations utilisateur
    access_token_expires = timedelta(minutes=settings.access_token_expire_minutes)
    access_token = create_access_token(
        data={
            "sub": user.id,
            "email": user.email,
            "name": user.name,
            "picture": user.picture
        },
        expires_delta=access_token_expires
    )

    return {"access_token": access_token, "token_type": "bearer", "user": user}
