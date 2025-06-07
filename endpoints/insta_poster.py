from fastapi import APIRouter
from openai import AsyncOpenAI

from config import settings

insta_poster_router = APIRouter(prefix="/insta_poster", tags=["Insta Poster"])

@insta_poster_router.post("/generate")
async def generate_insta_post(transcript: str):
    openai_client = AsyncOpenAI(
        api_key=settings.openai_instaposter_key
    )

    default_system_prompt = """You are a helpful assistant that helps writing instagram posts.
                           You will be provided with a transcript of the user's speech.
                           The speech basically contains the main ideas they want to share in their post.
                           Your role is to generate a post that is engaging and creative and share the ideas of the transcript.
                           Be concise but include every idea from the transcript. Be creative and engaging.
                           Use emojis and include #hashtags at the end of the post.
                           The post should be written in the same language as the transcript."""


    response = await openai_client.responses.create(
        model="gpt-4o-transcribe",
        temperature=1,
        input=[
            {
                "role": "system",
                "content": default_system_prompt
            },
            {
                "role": "user",
                "content": f"Transcript: {transcript}"
            }
        ]
    )

    return response.output_text