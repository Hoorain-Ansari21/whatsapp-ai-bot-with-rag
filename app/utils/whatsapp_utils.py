"""Handle incoming WhatsApp messages.

Text message  -> answer as text.
Voice message -> transcribe -> answer -> reply as a voice note
                 (falls back to a text reply if the voice part fails).
"""

import logging
import re
import threading
from collections import deque

from app.services.audio_service import text_to_voice_note, transcribe_audio
from app.services.llm_service import generate_response
from app.utils.whatsapp_api import download_media, send_text, send_voice, upload_audio

logger = logging.getLogger(__name__)

SORRY_TEXT = "Sorry, something went wrong on my side. Please try again in a moment."

# Remember the latest message ids so a retry from WhatsApp is not answered twice
_seen_message_ids: deque[str] = deque(maxlen=500)
_seen_lock = threading.Lock()


def _already_handled(message_id: str | None) -> bool:
    if not message_id:
        return False
    with _seen_lock:
        if message_id in _seen_message_ids:
            return True
        _seen_message_ids.append(message_id)
        return False


def process_text_for_whatsapp(text: str) -> str:
    """Convert common markdown to WhatsApp formatting."""
    text = re.sub(r"【.*?】", "", text)  # citation marks some models add
    text = re.sub(r"\*\*(.+?)\*\*", r"*\1*", text)  # **bold** -> *bold*
    text = re.sub(r"^#{1,6}\s+(.+)$", r"*\1*", text, flags=re.MULTILINE)  # headings -> bold
    text = re.sub(r"\[([^\]]+)\]\((https?://[^)]+)\)", r"\1: \2", text)  # [text](url) -> text: url
    return text.strip()


def handle_text_message(message: dict, wa_id: str, name: str) -> None:
    try:
        answer = generate_response(message["text"]["body"], wa_id, name)
    except Exception:
        logger.exception("Could not generate a reply")
        send_text(wa_id, SORRY_TEXT)
        return
    send_text(wa_id, process_text_for_whatsapp(answer))


def handle_voice_message(message: dict, wa_id: str, name: str) -> None:
    # Voice note in -> text -> answer -> voice note out
    try:
        audio_bytes = download_media(message["audio"]["id"])
        question = transcribe_audio(audio_bytes)
    except Exception:
        logger.exception("Could not read the voice message")
        send_text(wa_id, "Sorry, I could not hear that. Please try again.")
        return

    logger.info("Heard: %s", question)
    if not question:
        send_text(wa_id, "Sorry, I could not hear anything. Please try again.")
        return

    try:
        answer = generate_response(question, wa_id, name, spoken=True)
    except Exception:
        logger.exception("Could not generate a reply")
        send_text(wa_id, SORRY_TEXT)
        return

    try:
        ogg_bytes = text_to_voice_note(answer)
        media_id = upload_audio(ogg_bytes)
        if not send_voice(wa_id, media_id):
            raise RuntimeError("WhatsApp did not accept the voice note")
    except Exception:
        # If the voice part breaks, still send the answer as text
        logger.exception("Voice reply failed, sending text instead")
        send_text(wa_id, process_text_for_whatsapp(answer))


def process_whatsapp_message(body: dict) -> None:
    value = body["entry"][0]["changes"][0]["value"]
    message = value["messages"][0]
    contact = (value.get("contacts") or [{}])[0]
    wa_id = contact.get("wa_id") or message["from"]
    name = contact.get("profile", {}).get("name", "there")

    # Skip a message we already handled
    if _already_handled(message.get("id")):
        return

    message_type = message.get("type")
    if message_type == "text":
        handle_text_message(message, wa_id, name)
    elif message_type == "audio":
        handle_voice_message(message, wa_id, name)
    elif message_type in ("image", "video", "document"):
        send_text(wa_id, "I can read text and voice messages. Please send your question as text or a voice note.")
    # Reactions, stickers and other types are ignored


def is_valid_whatsapp_message(body: dict) -> bool:
    """Check if the incoming webhook event has a valid WhatsApp message structure."""
    try:
        return bool(body.get("object") and body["entry"][0]["changes"][0]["value"]["messages"][0])
    except (KeyError, IndexError, TypeError, AttributeError):
        return False
