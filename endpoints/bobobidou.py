import base64
import json

from openai import AsyncOpenAI
from fastapi import APIRouter, UploadFile, File, HTTPException

from config import settings

bobobidou_router = APIRouter(prefix="/bobobidou", tags=["Bobobidou"])


@bobobidou_router.post("/ingredients")
async def get_ingredients(language: str, file: UploadFile = File(...)):
    client = AsyncOpenAI(api_key=settings.openai_bobobidou_key)

    try:
        # Read image data
        image_bytes = await file.read()
        base64_image = base64.b64encode(image_bytes).decode("utf-8")

        # Send image to OpenAI API
        response = await client.responses.create(
            model="gpt-4o-mini-2024-07-18",
            temperature=0,
            input=[
                {
                    "role": "system",
                    "content": "You are a helpful assistant that can extract ingredients from an image."
                               "The image provided should contain cooked food. "
                               "Your role is to extrapolate what ingredients may be present in the food."
                               "You have to go deep into to include root ingredients. For example, if you see pasta, include in the list both pasta AND flour"
                               "Return a list of ingredients in required language. Every ingredient name should be in the singular form."
                               f"Language: {language}",
                },
                {
                    "role": "user",
                    "content": [
                        {"type": "input_image", "image_url": f"data:image/jpeg;base64,{base64_image}"},
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
        raise HTTPException(status_code=500, detail=str(e))
