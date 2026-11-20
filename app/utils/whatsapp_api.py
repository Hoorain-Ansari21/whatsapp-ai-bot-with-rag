"""Calls to the WhatsApp Cloud API (Meta Graph API)."""

import logging

import requests

from app.config import settings

logger = logging.getLogger(__name__)

# WhatsApp rejects text messages longer than 4096 characters
MAX_TEXT_CHARS = 4096


def _auth_headers() -> dict:
    return {"Authorization": f"Bearer {settings.access_token}"}


def send_message(payload: dict) -> bool:
    """Send any message payload. Returns True if WhatsApp accepted it."""
    url = f"{settings.graph_url}/{settings.phone_number_id}/messages"
    try:
        response = requests.post(url, json=payload, headers=_auth_headers(), timeout=10)
        response.raise_for_status()
    except requests.Timeout:
        logger.error("Timeout while sending message")
        return False
    except requests.RequestException as error:
        logger.error("Sending failed: %s | body: %s", error, getattr(error.response, "text", None))
        return False
    logger.info("Message sent (status %s)", response.status_code)
    return True


def send_text(recipient: str, text: str) -> bool:
    if len(text) > MAX_TEXT_CHARS:
        text = text[: MAX_TEXT_CHARS - 1] + "…"
    return send_message(
        {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": recipient,
            "type": "text",
            "text": {"preview_url": False, "body": text},
        }
    )


def send_voice(recipient: str, media_id: str) -> bool:
    return send_message(
        {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": recipient,
            "type": "audio",
            "audio": {"id": media_id, "voice": True},
        }
    )


def download_media(media_id: str) -> bytes:
    # Step 1: ask WhatsApp for the temporary download link
    info = requests.get(f"{settings.graph_url}/{media_id}", headers=_auth_headers(), timeout=10)
    info.raise_for_status()
    # Step 2: download the file from that link
    media = requests.get(info.json()["url"], headers=_auth_headers(), timeout=30)
    media.raise_for_status()
    return media.content


def upload_audio(ogg_bytes: bytes) -> str:
    """Upload a voice note and return its media id."""
    response = requests.post(
        f"{settings.graph_url}/{settings.phone_number_id}/media",
        headers=_auth_headers(),
        data={"messaging_product": "whatsapp", "type": "audio/ogg"},
        files={"file": ("reply.ogg", ogg_bytes, "audio/ogg")},
        timeout=30,
    )
    response.raise_for_status()
    return response.json()["id"]
