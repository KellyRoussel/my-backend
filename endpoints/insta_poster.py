import io
from typing import Optional
from openai import AsyncOpenAI
from fastapi import APIRouter, UploadFile, File
from config import settings

insta_poster_router = APIRouter(prefix="/insta_poster", tags=["Insta Poster"])

@insta_poster_router.post("/transcript")
async def transcribe_with_openai(
        audio_file: UploadFile = File(...),
        model: str = "gpt-4o-transcribe",
        response_format: str = "json",
        language: Optional[str] = None,
        prompt: Optional[str] = None
) -> dict:
    openai_client = AsyncOpenAI(api_key=settings.openai_instaposter_key)

    # Lire le contenu du fichier audio
    audio_bytes = await audio_file.read()

    # Obtenir le nom du fichier
    filename = audio_file.filename

    # Créer un objet file-like à partir des bytes
    audio_file_obj = io.BytesIO(audio_bytes)
    audio_file_obj.name = filename  # OpenAI utilise le nom pour déterminer le format

    # Préparer les paramètres pour l'API
    transcription_params = {
        "file": audio_file_obj,
        "model": model,
        "response_format": response_format
    }

    # Ajouter les paramètres optionnels
    if language:
        transcription_params["language"] = language

    if prompt:
        transcription_params["prompt"] = prompt

    # Faire l'appel à l'API OpenAI
    transcription = await openai_client.audio.transcriptions.create(**transcription_params)

    # Traiter la réponse selon le format
    if response_format == "json":
        return {"text": transcription.text}
    elif response_format == "verbose_json":
        return {
            "text": transcription.text,
            "language": getattr(transcription, 'language', None),
            "duration": getattr(transcription, 'duration', None),
            "segments": getattr(transcription, 'segments', None),
            "words": getattr(transcription, 'words', None)
        }
    else:  # text, srt, vtt
        return {"text": transcription}


