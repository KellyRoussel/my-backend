from typing import List

import httpx
from fastapi import HTTPException
from starlette import status

from config import settings
from dependencies.auth_services.insta_auth_service import InstaAuthService


class InstaService:


    async def _create_container(self, image_url: str, is_carousel_item: bool, access_token: str, caption: str = None, alt_text: str = None):
        try:
            print(f"ACCESS TOKEN: {access_token}")
            url = f"https://graph.instagram.com/v23.0/{settings.insta_client_id}/media"
            data = {
                "image_url": image_url,
                "access_token": access_token
            }
            if is_carousel_item:
                data["is_carousel_item"] = "true"
            if caption:
                data["caption"] = caption
            if alt_text:
                data["alt_text"] = alt_text
            async with httpx.AsyncClient() as client:
                response = await client.post(url=url, data=data)
                response_data = response.json()
                if "error" in response_data:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail=f"Insta create container error: {response_data['error']}"
                    )
            return response_data["id"]
        except Exception as e:
            raise Exception(f"_create_container: {e}")

    async def _create_carousel(self, container_ids: List[str], caption: str, access_token: str):
        try:
            url = f"https://graph.instagram.com/v23.0/{settings.insta_client_id}/media"
            header = {"Authorization": f"Bearer {access_token}"}
            data = {
                "caption": caption,
                "media_type": "CAROUSEL",
                "children": ",".join(container_ids)
            }
            async with httpx.AsyncClient() as client:
                response = await client.post(headers=header, data=data, url=url)

                response_data = response.json()

                if "error" in response_data:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail=f"Insta create carousel error: {response_data['error']}"
                    )

            return response_data["id"]
        except Exception as e:
            raise Exception(f"_create_carousel: {e}")

    async def _publish(self, container_or_carousel_id: str, access_token: str):
        try:
            url = f"https://graph.instagram.com/v23.0/{settings.insta_client_id}/media_publish"
            header = {"Authorization": f"Bearer {access_token}"}
            data = {
                "creation_id": container_or_carousel_id
            }
            async with httpx.AsyncClient() as client:
                response = await client.post(headers=header, data=data, url=url)

                response_data = response.json()

                if "error" in response_data:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail=f"Insta publish error: {response_data['error']}"
                    )

            return response_data["id"]
        except Exception as e:
            raise Exception(f"_publish: {e}")

    async def create_post(self, images_url: List[str], caption: str, access_token: str):
    
        is_carousel = len(images_url) > 1
        ids = []
        for image_url in images_url:
            container_id = await self._create_container(image_url, is_carousel, access_token)
            ids.append(container_id)

        if is_carousel:
            carousel_id = await self._create_carousel(ids, caption, access_token)
            ids = [carousel_id]

        await self._publish(ids[0], access_token)

        return
        

_insta_service = InstaService()

def get_insta_service():
    return _insta_service