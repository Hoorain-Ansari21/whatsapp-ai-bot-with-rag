"""One shared Groq client for chat, speech-to-text and text-to-speech."""

from functools import lru_cache

from groq import Groq

from app.config import settings


@lru_cache(maxsize=1)
def get_client() -> Groq:
    return Groq(api_key=settings.groq_api_key, max_retries=2, timeout=60)
