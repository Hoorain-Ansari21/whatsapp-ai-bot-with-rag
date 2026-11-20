"""Split extracted pages into small, overlapping chunks for retrieval."""

import hashlib
import re

# The embedding model reads about 128 tokens, so chunks are kept small.
# Neighbouring chunks overlap a little so a sentence cut in two is not lost.
CHUNK_CHARS = 700
OVERLAP_CHARS = 120

_HEADING = re.compile(r"^#{1,6}\s+(.*)$")


def _sections(text: str) -> list[tuple[str, str]]:
    """Split markdown text into (heading, body) sections."""
    sections, heading, lines = [], "", []
    for line in text.splitlines():
        match = _HEADING.match(line.strip())
        if match:
            if lines:
                sections.append((heading, "\n".join(lines).strip()))
            heading, lines = match.group(1).strip(), []
        else:
            lines.append(line)
    if lines:
        sections.append((heading, "\n".join(lines).strip()))
    return [(h, b) for h, b in sections if b]


def _pieces(body: str) -> list[str]:
    """Paragraphs, with any paragraph longer than a chunk cut at sentence ends."""
    pieces = []
    for paragraph in re.split(r"\n\s*\n", body):
        paragraph = paragraph.strip()
        if not paragraph:
            continue
        if len(paragraph) <= CHUNK_CHARS:
            pieces.append(paragraph)
            continue
        current = ""
        for sentence in re.split(r"(?<=[.!?۔])\s+|\n", paragraph):
            while len(sentence) > CHUNK_CHARS:  # one huge "sentence", e.g. a table row dump
                pieces.append(sentence[:CHUNK_CHARS])
                sentence = sentence[CHUNK_CHARS:]
            if current and len(current) + len(sentence) + 1 > CHUNK_CHARS:
                pieces.append(current)
                current = sentence
            else:
                current = f"{current} {sentence}".strip()
        if current:
            pieces.append(current)
    return pieces


def _pack(pieces: list[str]) -> list[str]:
    """Join small pieces into chunks of about CHUNK_CHARS, with overlap."""
    chunks, current = [], ""
    for piece in pieces:
        if current and len(current) + len(piece) + 2 > CHUNK_CHARS:
            chunks.append(current)
            tail = current[-OVERLAP_CHARS:]
            tail = tail[tail.find(" ") + 1:] if " " in tail else tail
            current = f"{tail}\n\n{piece}"
        else:
            current = f"{current}\n\n{piece}" if current else piece
    if current:
        chunks.append(current)
    return chunks


def chunk_page(page: dict) -> list[dict]:
    chunks = []
    for heading, body in _sections(page["text"]):
        for text in _pack(_pieces(body)):
            chunks.append(
                {
                    "text": text,
                    "heading": heading,
                    "title": page["title"],
                    "url": page["url"],
                    "source": page["source"],
                    "category": page["category"],
                    "fetched_at": page.get("fetched_at", ""),
                }
            )
    return chunks


def chunk_pages(pages: list[dict]) -> list[dict]:
    """Chunk every page and drop exact duplicates (menus repeated on every page etc.)."""
    seen, result = set(), []
    for page in pages:
        for chunk in chunk_page(page):
            key = hashlib.sha1(chunk["text"].lower().encode("utf-8")).hexdigest()
            if key in seen or len(chunk["text"]) < 40:
                continue
            seen.add(key)
            result.append(chunk)
    return result


def embedding_text(chunk: dict) -> str:
    """What gets embedded: the page title and heading give the chunk its context."""
    parts = [chunk["title"], chunk["heading"], chunk["text"]]
    return "\n".join(p for p in parts if p)
