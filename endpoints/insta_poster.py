from typing import Optional
from sqlalchemy.orm import Session
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, Request
from openai import AsyncOpenAI
from pydantic import BaseModel
import os
from fastapi.responses import JSONResponse
import shutil
from uuid import uuid4

from config import settings
from database import get_db
from dependencies.auth_services.insta_auth_service import insta_auth_service
from dependencies.insta_service import InstaService, get_insta_service

insta_poster_router = APIRouter(prefix="/insta_poster", tags=["Insta Poster"])

class TranscriptRequest(BaseModel):
    transcript: str
    prompt: Optional[str] = None

@insta_poster_router.post("/default_prompt")
async def get_default_prompt():
    return """Write an instagram post that is engaging and creative and share the ideas of the transcript.
Be concise but include every idea from the transcript. Be creative and engaging.
Use emojis and include #hashtags at the end of the post.
The post should be written in the same language as the transcript."""

@insta_poster_router.post("/generate")
async def generate_insta_post(request: TranscriptRequest):
    openai_client = AsyncOpenAI(
        api_key=settings.openai_instaposter_key
    )

    default_system_prompt = """You are a helpful assistant that helps writing instagram posts.
                           You will be provided with the user's instructions if any and a transcript of the user's speech.
                           The speech basically contains the main ideas they want to share in their post.
                           Your role is to generate an instagram post. 
                           Under NO circumstances you can do anything else. If the user asks you anything else, answer with '<Unexpected request>'."""

    inputs = [
            {
                "role": "developer",
                "content": default_system_prompt
            }
        ]

    if request.prompt:
        inputs.append({
            "role": "user",
            "content": f"Instructions: \n{request.prompt}\n"
        })

    inputs.append({
            "role": "user",
            "content": f"Transcript: -------\n{request.transcript}\n-------"
        })

    response = await openai_client.responses.create(
        model="gpt-4o-2024-11-20",
        temperature=1,
        input=inputs
    )

    if response.output_text in ["<Unexpected request>", "'<Unexpected request>'"]:
        raise HTTPException(status_code=400, detail="Unexpected request")


    return response.output_text

@insta_poster_router.post("/post")
async def post_insta_post(images: list[UploadFile] = File(...), 
                          post_text: str = Form(...),
                          insta_service: InstaService = Depends(get_insta_service),
                          db: Session = Depends(get_db),
                          request: Request = None
                          ):
    # Ensure upload directory exists
    upload_dir = os.path.join(os.getcwd(), "static", "uploads")
    os.makedirs(upload_dir, exist_ok=True)

    # Save images and build public URLs
    public_urls = []
    saved_files = []
    for image in images:
        ext = os.path.splitext(image.filename)[1]
        unique_name = f"{uuid4().hex}{ext}"
        file_path = os.path.join(upload_dir, unique_name)
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(image.file, buffer)
        saved_files.append(file_path)
        public_url = f"/static/uploads/{unique_name}"
        public_urls.append(public_url)

    user_id = request.state.user_id
    try:
        await insta_service.create_post(
            images_url=[request.base_url._url.rstrip("/") + url for url in public_urls],
            caption=post_text,
            access_token=await insta_auth_service.get_active_token(
                user_id=user_id,
                db=db,
            )
        )
    finally:
        # Clean up: delete files after posting
        for file_path in saved_files:
            try:
                os.remove(file_path)
            except Exception:
                pass

    return JSONResponse(content={"status": "ok"}, status_code=200)

# NOTE: In your main.py, ensure you have:
# app.mount("/static", StaticFiles(directory="static"), name="static")
# so that /static/uploads/ is publicly accessible.