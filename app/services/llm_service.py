"""Answer a user's question with the Groq LLM, grounded in the knowledge base (RAG)."""

import logging
import shelve
import threading
from pathlib import Path

from app.config import settings
from app.services.groq_client import get_client
from knowledge import retriever

logger = logging.getLogger(__name__)

# How many past messages we send to the model each time
MAX_HISTORY = 20
# How many knowledge-base chunks we give the model per question
TOP_K = 6

# The history file can only be opened by one thread at a time
history_lock = threading.Lock()
Path(settings.history_db_path).parent.mkdir(parents=True, exist_ok=True)


SYSTEM_PROMPT = """You are Ilm Assist, a friendly WhatsApp assistant that helps students and parents in Pakistan with higher education:
universities and their policies, admissions, fee structures, scholarships and financial aid, degree attestation, and scholarships to study abroad.

How to answer:
- Use ONLY the facts in the CONTEXT section of the user's message. Never invent fees, deadlines, amounts, eligibility rules or links.
- If the context does not contain the answer, say you do not have verified information on that, and point the user to the most relevant official website (for example https://www.hec.gov.pk).
- Fees, deadlines and amounts change every year. When you give one, mention the year or session if the context shows it, and suggest confirming on the official page.
- Only help with education topics. Greetings and small talk are fine: reply briefly and say what you can help with. Politely decline anything unrelated.
- Never mention the word "context" or the numbers of the context entries. Speak as if you simply know the information.
- Reply in the same language the user writes in (English, Urdu or Roman Urdu).
- Keep replies short and clear, unless the person asks for more detail."""

# Extra rules for text replies
TEXT_RULES = """
Your reply is a WhatsApp text message.
Use WhatsApp formatting only: *bold* and simple lists starting with "- ". No tables or headings.
End with the official link(s) you used, like: Source: https://..."""

# Extra rules that only apply when the reply will be read out loud
SPOKEN_RULES = """
Your reply will be read out loud as a voice message.
Always reply in English.
Use at most three short sentences.
Do not use lists, markdown, emojis, links or special symbols.
Write everything exactly as it should be spoken."""


# Get the saved chat history for this user (empty list if new user)
def get_history(wa_id: str) -> list[dict]:
    with history_lock:
        with shelve.open(settings.history_db_path) as threads_shelf:
            return threads_shelf.get(wa_id, [])


# Save the chat history for this user
def save_history(wa_id: str, history: list[dict]) -> None:
    with history_lock:
        with shelve.open(settings.history_db_path) as threads_shelf:
            threads_shelf[wa_id] = history


def build_search_query(message: str, history: list[dict]) -> str:
    """Short follow-ups ("what is the deadline?") need the earlier question to be searchable."""
    if len(message.split()) >= 6:
        return message
    previous = [m["content"] for m in history if m["role"] == "user"]
    return f"{previous[-1]} {message}" if previous else message


def format_context(hits: list[dict]) -> str:
    if not hits:
        return "CONTEXT:\n(nothing relevant found in the knowledge base)"
    blocks = []
    for i, hit in enumerate(hits, start=1):
        heading = f" > {hit['heading']}" if hit.get("heading") else ""
        blocks.append(
            f"[{i}] {hit['title']}{heading}\n"
            f"Source: {hit['url']} (retrieved {hit.get('fetched_at', '')[:10]})\n"
            f"{hit['text']}"
        )
    return "CONTEXT:\n" + "\n\n".join(blocks)


def generate_response(message_body: str, wa_id: str, name: str, spoken: bool = False) -> str:
    history = get_history(wa_id)
    logger.info("%s chat for %s (%s)", "Continuing" if history else "Starting new", name, wa_id)

    # Look up the knowledge base
    try:
        hits = retriever.search(build_search_query(message_body, history), top_k=TOP_K)
    except Exception:
        logger.exception("Knowledge base search failed")
        hits = []
    logger.info("Found %d knowledge chunks", len(hits))

    # The context is only added to the current message, not stored in history
    system_prompt = SYSTEM_PROMPT + (SPOKEN_RULES if spoken else TEXT_RULES)
    user_turn = f"{format_context(hits)}\n\nUSER MESSAGE:\n{message_body}"
    past = history[-(MAX_HISTORY - 1):]
    messages = [{"role": "system", "content": system_prompt}, *past, {"role": "user", "content": user_turn}]

    completion = get_client().chat.completions.create(
        model=settings.groq_model,
        messages=messages,
        max_tokens=250 if spoken else 1000,
        temperature=0.3,
    )
    new_message = (completion.choices[0].message.content or "").strip()
    logger.info("Generated message: %s", new_message)

    # Save the plain question and reply so the next message remembers them
    history = past + [
        {"role": "user", "content": message_body},
        {"role": "assistant", "content": new_message},
    ]
    save_history(wa_id, history)
    return new_message

