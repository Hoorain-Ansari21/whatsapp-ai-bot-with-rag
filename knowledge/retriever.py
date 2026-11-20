"""Search the knowledge base.

Hybrid search: meaning-based (embeddings) + keyword-based (BM25), merged with
reciprocal rank fusion. Embeddings find paraphrases ("money help for poor
students" -> need-based scholarship); BM25 catches exact names and acronyms
("PEEF", "HAT test", "Stipendium Hungaricum") that small embedding models miss.
"""

import json
import logging
import re
import threading

import numpy as np
from rank_bm25 import BM25Okapi

from .embeddings import embed_query
from .paths import CHUNKS_FILE, EMBEDDINGS_FILE, MANIFEST_FILE

logger = logging.getLogger(__name__)

RRF_K = 60  # standard constant for reciprocal rank fusion
CANDIDATES = 30  # how many results each method contributes before merging
MIN_VECTOR_SCORE = 0.25  # below this, a vector match is just noise

_STOPWORDS = set(
    "a an and are as at be by can do does for from how i in is it me my of on or "
    "the to what when where which who why will with you your hai ka ki ke ko se "
    "mein main kya kaise".split()
)


def tokenize(text: str) -> list[str]:
    return [t for t in re.findall(r"\w+", text.lower()) if t not in _STOPWORDS]


def index_exists() -> bool:
    return MANIFEST_FILE.exists() and CHUNKS_FILE.exists() and EMBEDDINGS_FILE.exists()


class Retriever:
    def __init__(self, chunks: list[dict], embeddings: np.ndarray):
        self.chunks = chunks
        self.embeddings = embeddings
        self.bm25 = BM25Okapi([tokenize(f"{c['title']} {c['heading']} {c['text']}") for c in chunks])

    @classmethod
    def load(cls) -> "Retriever":
        with CHUNKS_FILE.open(encoding="utf-8") as f:
            chunks = [json.loads(line) for line in f if line.strip()]
        embeddings = np.load(EMBEDDINGS_FILE)
        if len(chunks) != len(embeddings):
            raise ValueError("Knowledge base files do not match; rebuild with --force")
        logger.info("Knowledge base loaded: %d chunks", len(chunks))
        return cls(chunks, embeddings)

    def search(self, query: str, top_k: int = 6) -> list[dict]:
        if not query.strip() or not self.chunks:
            return []

        scores = self.embeddings @ embed_query(query)
        vector_ranked = [i for i in np.argsort(-scores)[:CANDIDATES] if scores[i] >= MIN_VECTOR_SCORE]

        bm25_scores = self.bm25.get_scores(tokenize(query))
        bm25_ranked = [i for i in np.argsort(-bm25_scores)[:CANDIDATES] if bm25_scores[i] > 0]

        fused: dict[int, float] = {}
        for ranked in (vector_ranked, bm25_ranked):
            for rank, i in enumerate(ranked):
                fused[int(i)] = fused.get(int(i), 0.0) + 1.0 / (RRF_K + rank + 1)

        best = sorted(fused, key=fused.get, reverse=True)[:top_k]
        return [{**self.chunks[i], "score": round(fused[i], 4)} for i in best]


_retriever: Retriever | None = None
_lock = threading.Lock()


def get_retriever() -> Retriever | None:
    """The shared retriever, loaded on first use. None if the index is not built yet."""
    global _retriever
    with _lock:
        if _retriever is None and index_exists():
            _retriever = Retriever.load()
    return _retriever


def search(query: str, top_k: int = 6) -> list[dict]:
    retriever = get_retriever()
    if retriever is None:
        logger.warning("Knowledge base not built yet. Run: python build_knowledge_base.py")
        return []
    return retriever.search(query, top_k)
