import httpx
from fastapi import HTTPException
from starlette import status

from config import settings
from models.authentication import User


class InstaAuthService:
    #https://developers.facebook.com/docs/instagram-platform/instagram-api-with-instagram-login/business-login

    @staticmethod
    async def get_auth_url(app:str):
        params = {
            "client_id": settings.insta_client_id,
            "redirect_uri": settings.auth_redirect_uri + f"/{app}",
            "response_type": "code",
            "scope": "instagram_business_basic instagram_business_content_publish",
            "enable_fb_login": 0,
            "force_authentication": 1
        }

        query_string = "&".join([f"{key}={value}" for key, value in params.items()])
        auth_url = f"{settings.insta_auth_url}?{query_string}"

        return auth_url

    @staticmethod
    async def exchange_code_for_token(code: str, app: str):
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
                    detail=f"Insta authentication error: {token_response_data['error']}"
                )

            return token_response_data

    @staticmethod
    async def get_user_info(access_token: str):
        async with httpx.AsyncClient() as client:
            url = f"{settings.insta_user_info_url}?fields=id,username,profile_picture_url&access_token={access_token}"


            user_info_response = await client.get(url)
            user_info = user_info_response.json()

            print(f"USER INFO: {user_info}")

            if "error" in user_info:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Error getting user info: {user_info['error']}"
                )

            try:
                url = f"https://graph.instagram.com/v22.0/{user_info['id']}?fields=name,profile_picture_url&access_token={access_token}"

                more_user_info_response = await client.get(url)
                more_user_info = more_user_info_response.json()
                print(f"MORE USER INFO: {more_user_info}")
            except Exception as e:
                print(f"🔴 Error getting more user info: {e}")

            return User(
                email=user_info.get("email"),
                name=user_info.get("username"),
                picture=user_info.get("profile_picture_url"),
                id=user_info["id"]
            )

    @staticmethod
    async def get_long_lived_token(access_token: str):
        async with httpx.AsyncClient() as client:
            url = f"{settings.insta_long_lived_token_url}?grant_type=ig_exchange_token&access_token={access_token}&client_secret={settings.insta_client_secret}"
            long_lived_token_response = await client.get(url)
            long_lived_token = long_lived_token_response.json()

            # {
            #   "access_token":"EAACEdEose0...",
            #   "token_type": "bearer",
            #   "expires_in": 5183944  // Number of seconds until token expires
            # }

            if "error" in long_lived_token:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Error getting long-lived token: {long_lived_token['error']}"
                )

            return long_lived_token

insta_auth_service = InstaAuthService()
