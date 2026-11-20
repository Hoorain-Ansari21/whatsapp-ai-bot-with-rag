"""Voice notes: speech-to-text for incoming audio, text-to-speech for replies."""

import logging
import os
import re
import subprocess
import tempfile
from concurrent.futures import ThreadPoolExecutor

from app.config import settings
from app.services.groq_client import get_client

logger = logging.getLogger(__name__)

# Orpheus accepts at most 200 characters per request, so we stay below that
MAX_TTS_CHARS = 180


def transcribe_audio(audio_bytes: bytes) -> str:
    # WhatsApp voice notes are ogg files, and Groq accepts ogg directly
    result = get_client().audio.transcriptions.create(
        file=("voice.ogg", audio_bytes),
        model=settings.stt_model,
        language="en",
        temperature=0.0,
    )
    return result.text.strip()


def clean_for_speech(text: str) -> str:
    # Remove links
    text = re.sub(r"https?://\S+", "", text)
    # Square brackets are voice directions for Orpheus, so remove any from the reply
    text = re.sub(r"\[.*?\]", "", text)
    # Turn fancy quotes into normal ones and dashes into commas
    text = text.replace("\u2019", "'").replace("\u2018", "'")
    text = text.replace("\u201c", '"').replace("\u201d", '"')
    text = re.sub(r"\s*[\u2014\u2013]\s*", ", ", text)
    # Remove markdown symbols
    text = re.sub(r"[*_#`>~]", "", text)
    # Remove emojis and any other non-English characters
    text = re.sub(r"[^\x00-\x7F]", "", text)
    # Turn line breaks into spaces
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def split_text(text: str, limit: int = MAX_TTS_CHARS) -> list[str]:
    # Cut the text into sentences first
    sentences = re.split(r"(?<=[.!?])\s+", text.strip())
    chunks = []
    current = ""

    for sentence in sentences:
        # A sentence that is still too long gets cut at a space
        while len(sentence) > limit:
            cut = sentence.rfind(" ", 0, limit)
            if cut <= 0:
                cut = limit
            piece, sentence = sentence[:cut], sentence[cut:].strip()
            if current:
                chunks.append(current)
                current = ""
            chunks.append(piece)

        if not sentence:
            continue

        # Join short sentences together while they still fit
        if current and len(current) + 1 + len(sentence) > limit:
            chunks.append(current)
            current = sentence
        else:
            current = f"{current} {sentence}".strip()

    if current:
        chunks.append(current)
    return chunks


def speak_chunk(chunk: str) -> bytes:
    # Turn one short piece of text into wav audio
    response = get_client().audio.speech.create(
        model=settings.tts_model,
        voice=settings.tts_voice,
        input=chunk,
        response_format="wav",
    )
    return response.read()


def wavs_to_ogg_opus(wav_list: list[bytes]) -> bytes:
    # Join all wav pieces and convert to the format WhatsApp needs for voice notes:
    # ogg file, opus codec, mono
    with tempfile.TemporaryDirectory() as folder:
        inputs = []
        for i, data in enumerate(wav_list):
            path = os.path.join(folder, f"part{i}.wav")
            with open(path, "wb") as f:
                f.write(data)
            inputs += ["-i", path]

        count = len(wav_list)
        join_filter = "".join(f"[{i}:a]" for i in range(count)) + f"concat=n={count}:v=0:a=1[out]"
        out_path = os.path.join(folder, "reply.ogg")

        command = (
            ["ffmpeg", "-y", "-loglevel", "error"]
            + inputs
            + [
                "-filter_complex", join_filter,
                "-map", "[out]",
                "-ac", "1",
                "-ar", "48000",
                "-c:a", "libopus",
                "-b:a", "24k",
                "-application", "voip",
                out_path,
            ]
        )
        subprocess.run(command, check=True, capture_output=True)

        with open(out_path, "rb") as f:
            return f.read()


def text_to_voice_note(text: str) -> bytes:
    text = clean_for_speech(text)
    chunks = split_text(text)
    if not chunks:
        raise ValueError("Nothing to speak")

    logger.info("Speaking %d chunk(s)", len(chunks))
    # map keeps the original order even though the calls run at the same time
    with ThreadPoolExecutor(max_workers=4) as pool:
        wav_list = list(pool.map(speak_chunk, chunks))

    return wavs_to_ogg_opus(wav_list)
