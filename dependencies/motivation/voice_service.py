import httpx

from config import settings

ELEVENLABS_TTS_URL = "https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"


async def synthesize(text: str) -> bytes:
    """Read `text` with the ElevenLabs voice and return MP3 bytes."""
    async with httpx.AsyncClient(timeout=60) as client:
        response = await client.post(
            ELEVENLABS_TTS_URL.format(voice_id=settings.elevenlabs_voice_id),
            params={"output_format": "mp3_44100_128"},
            headers={"xi-api-key": settings.elevenlabs_api_key, "Accept": "audio/mpeg"},
            json={
                "text": text,
                "model_id": settings.elevenlabs_model,
                "voice_settings": {
                    "stability": settings.elevenlabs_stability,
                    "similarity_boost": settings.elevenlabs_similarity_boost,
                    "style": settings.elevenlabs_style,
                },
            },
        )
    response.raise_for_status()
    return response.content
