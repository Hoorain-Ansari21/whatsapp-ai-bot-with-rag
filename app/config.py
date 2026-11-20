"""All settings come from environment variables (.env file)."""

import logging
import os
import sys
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class Settings:
    # WhatsApp Cloud API
    access_token: str = os.getenv("ACCESS_TOKEN", "")
    app_secret: str = os.getenv("APP_SECRET", "")
    phone_number_id: str = os.getenv("PHONE_NUMBER_ID", "")
    version: str = os.getenv("VERSION", "v21.0")
    verify_token: str = os.getenv("VERIFY_TOKEN", "")

    # Groq models
    groq_api_key: str = os.getenv("GROQ_API_KEY", "")
    groq_model: str = os.getenv("GROQ_MODEL") or "llama-3.3-70b-versatile"
    stt_model: str = os.getenv("STT_MODEL") or "whisper-large-v3-turbo"
    tts_model: str = os.getenv("TTS_MODEL") or "canopylabs/orpheus-v1-english"
    # English voices: autumn, diana, hannah (female) and austin, daniel, troy (male)
    tts_voice: str = os.getenv("TTS_VOICE") or "troy"

    # Chat history
    history_db_path: str = os.getenv("HISTORY_DB_PATH") or "data/threads_db"

    @property
    def graph_url(self) -> str:
        return f"https://graph.facebook.com/{self.version}"


settings = Settings()

REQUIRED = {
    "ACCESS_TOKEN": settings.access_token,
    "APP_SECRET": settings.app_secret,
    "PHONE_NUMBER_ID": settings.phone_number_id,
    "VERIFY_TOKEN": settings.verify_token,
    "GROQ_API_KEY": settings.groq_api_key,
}


def check_settings() -> None:
    missing = [name for name, value in REQUIRED.items() if not value]
    if missing:
        raise RuntimeError(f"Missing settings in .env: {', '.join(missing)} (see .env.example)")


def configure_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        stream=sys.stdout,
    )
    for noisy in ("httpx", "urllib3", "trafilatura"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
