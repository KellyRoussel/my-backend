import httpx
from fastapi import HTTPException
from starlette import status

from config import settings
from models.authentication import User


class GoogleAuthService:
    @staticmethod
    async def get_auth_url():
        params = {
            "client_id": settings.google_client_id,
            "redirect_uri": settings.auth_redirect_uri,
            "response_type": "code",
            "scope": "email profile",
            "access_type": "offline",
            "include_granted_scopes": "true",
        }

        query_string = "&".join([f"{key}={value}" for key, value in params.items()])
        auth_url = f"{settings.google_auth_url}?{query_string}"

        return auth_url

    @staticmethod
    async def exchange_code_for_token(code: str):
        token_request_data = {
            "code": code,
            "client_id": settings.google_client_id,
            "client_secret": settings.google_client_secret,
            "redirect_uri": settings.auth_redirect_uri,
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

    @staticmethod
    async def get_user_info(access_token: str):
        async with httpx.AsyncClient() as client:
            headers = {"Authorization": f"Bearer {access_token}"}
            user_info_response = await client.get(settings.google_user_info_url, headers=headers)
            user_info = user_info_response.json()

            if "error" in user_info:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Error getting user info: {user_info['error']}"
                )

            return User(
                email=user_info["email"],
                name=user_info.get("name"),
                picture=user_info.get("picture"),
                id=user_info["sub"]
            )

google_auth_service = GoogleAuthService()
