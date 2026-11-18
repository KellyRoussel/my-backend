import secrets
from urllib.parse import quote

from fastapi import APIRouter, Depends, Header, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel, Field

from config import settings
from dependencies.motivation.audio_mixer import mix_voice_with_music
from dependencies.motivation.music_catalog import TRACKS, get_track
from dependencies.motivation.phrase_generator import generate_phrases
from dependencies.motivation.voice_service import synthesize



def _verify_motivation_key(x_motivation_key: str = Header(default="")):
    # Refuse everything while no key is configured
    expected = settings.motivation_api_key
    if not expected or not secrets.compare_digest(x_motivation_key.encode(), expected.encode()):
        raise HTTPException(status_code=401, detail="Invalid API key")


motivation_router = APIRouter(
    prefix="/motivation", tags=["Motivation"], dependencies=[Depends(_verify_motivation_key)]
)

MAX_TEXT_LENGTH = 1000  # ElevenLabs bills per character


class PhrasesRequest(BaseModel):
    count: int = Field(default=1, ge=1, le=10)
    theme: str | None = Field(default=None, max_length=200)


class ClipRequest(BaseModel):
    track_id: str
    # Text to read; generated when missing
    text: str | None = Field(default=None, max_length=MAX_TEXT_LENGTH)
    theme: str | None = Field(default=None, max_length=200)


@motivation_router.get("/tracks")
async def list_tracks():
    return {"tracks": [{"id": t.id, "title": t.title} for t in TRACKS if t.path.is_file()]}


@motivation_router.post("/phrases")
async def create_phrases(body: PhrasesRequest):
    try:
        return {"phrases": await generate_phrases(body.count, body.theme)}
    except Exception as e:
        print(f"🔴 Motivation phrase generation error: {e}")
        raise HTTPException(status_code=502, detail="Phrase generation failed")


@motivation_router.post("/clip", response_class=Response)
async def create_clip(body: ClipRequest):
    """Return the MP3 clip. The text read is in the `X-Motivation-Text` header (URL-encoded)."""
    track = get_track(body.track_id)
    if track is None or not track.path.is_file():
        raise HTTPException(status_code=404, detail="Unknown track")

    text = (body.text or "").strip()
    if not text:
        try:
            text = (await generate_phrases(1, body.theme))[0]
        except Exception as e:
            print(f"🔴 Motivation phrase generation error: {e}")
            raise HTTPException(status_code=502, detail="Phrase generation failed")

    try:
        voice = await synthesize(text)
    except Exception as e:
        print(f"🔴 ElevenLabs error: {e}")
        raise HTTPException(status_code=502, detail="Voice synthesis failed")

    try:
        clip = await mix_voice_with_music(voice, track)
    except Exception as e:
        print(f"🔴 Motivation mixing error: {e}")
        raise HTTPException(status_code=500, detail="Audio mixing failed")

    return Response(
        content=clip,
        media_type="audio/mpeg",
        headers={
            "X-Motivation-Text": quote(text),
            "Access-Control-Expose-Headers": "X-Motivation-Text",
            "Content-Disposition": 'inline; filename="motivation.mp3"',
        },
    )
