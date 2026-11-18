from openai import AsyncOpenAI
from pydantic import BaseModel

from config import settings
from dependencies.motivation.prompts import build_system_prompt, build_user_prompt


class _Phrases(BaseModel):
    phrases: list[str]


async def generate_phrases(count: int = 1, theme: str | None = None) -> list[str]:
    """Generate `count` motivation phrases in the style defined in prompts.py."""
    client = AsyncOpenAI(api_key=settings.openai_motivation_key)
    response = await client.responses.parse(
        model=settings.motivation_model,
        temperature=settings.motivation_temperature,
        input=[
            {"role": "system", "content": build_system_prompt()},
            {"role": "user", "content": build_user_prompt(count, theme)},
        ],
        text_format=_Phrases,
    )
    phrases = [p.strip() for p in response.output_parsed.phrases if p.strip()]
    if not phrases:
        raise ValueError("The model returned no phrase")
    return phrases[:count]
