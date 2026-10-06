import base64
import json

from openai import AsyncOpenAI
from fastapi import APIRouter, UploadFile, File, HTTPException

from config import settings

bobobidou_router = APIRouter(prefix="/bobobidou", tags=["Bobobidou"])

# The language is injected in the prompt: only accept the languages the app supports
SUPPORTED_LANGUAGES = {"en": "English", "fr": "French"}
ALLOWED_IMAGE_TYPES = {"image/jpeg", "image/png", "image/webp"}


@bobobidou_router.post("/ingredients")
async def get_ingredients(language: str, file: UploadFile = File(...)):
    language_name = SUPPORTED_LANGUAGES.get(language.lower())
    if language_name is None:
        raise HTTPException(status_code=400, detail="Unsupported language")

    content_type = file.content_type or "image/jpeg"
    if content_type not in ALLOWED_IMAGE_TYPES:
        raise HTTPException(status_code=415, detail="Unsupported image type")

    # Read image data, refusing files bigger than the limit
    max_bytes = settings.bobobidou_max_image_mb * 1024 * 1024
    image_bytes = await file.read(max_bytes + 1)
    if len(image_bytes) > max_bytes:
        raise HTTPException(status_code=413, detail="Image too large")
    if not image_bytes:
        raise HTTPException(status_code=400, detail="Empty image")

    client = AsyncOpenAI(api_key=settings.openai_bobobidou_key)

    try:
        base64_image = base64.b64encode(image_bytes).decode("utf-8")

        # Send image to OpenAI API
        response = await client.responses.create(
            model=settings.bobobidou_model,
            temperature=0,
            input=[
                {
                    "role": "system",
                    "content": "You are a helpful assistant that can extract ingredients from an image."
                               "The image provided should contain cooked food. "
                               "Your role is to extrapolate what ingredients may be present in the food."
                               "You have to go deep into to include root ingredients. For example, if you see pasta, include in the list both pasta AND flour"
                               "Return a list of ingredients in required language. Every ingredient name should be in the singular form."
                               f"Language: {language_name}",
                },
                {
                    "role": "user",
                    "content": [
                        {"type": "input_image", "image_url": f"data:{content_type};base64,{base64_image}"},
                    ],
                }
            ],
            text={
                "format": {
                    "type": "json_schema",
                    "name": "ingredients_list",
                    "schema": {
                        "type": "object",
                        "properties": {
                            "ingredients": {
                                "type": "array",
                                "items": {
                                    "type": "string"
                                }
                            }
                        },
                        "required": ["ingredients"],
                        "additionalProperties": False
                    },
                    "strict": True
                }
            },
        )

        ingredients = json.loads(response.output_text)["ingredients"]
        ingredients = [ingredients.lower().strip() for ingredients in ingredients]

        return {"ingredients": ingredients}
    except Exception as e:
        # Don't leak internal errors (OpenAI messages, keys config...) to the client
        print(f"🔴 Bobobidou ingredients error: {e}")
        raise HTTPException(status_code=502, detail="Ingredient recognition failed")
