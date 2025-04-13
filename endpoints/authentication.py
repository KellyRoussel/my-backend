from datetime import timedelta, datetime
from typing import Optional

import jwt
from fastapi import APIRouter

from config import settings
from dependencies.google_auth_service import google_auth_service

authentication_router = APIRouter(tags=["Authentication"])
@authentication_router.get("/login/google")
async def get_google_auth_url():
    auth_url = await google_auth_service.get_auth_url()
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

@authentication_router.get("/auth/callback")
async def auth_callback(code: str):
    # Échanger le code contre un token
    token_data = await google_auth_service.exchange_code_for_token(code)
    google_access_token = token_data["access_token"]

    # Obtenir les informations utilisateur
    user = await google_auth_service.get_user_info(google_access_token)

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
