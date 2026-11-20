"""Local text embeddings (no API key needed)."""

import logging
import threading

import numpy as np

from .paths import EMBEDDING_MODEL, MODEL_CACHE_DIR

logger = logging.getLogger(__name__)

_model = None
_model_lock = threading.Lock()


def get_model():
    """Load the embedding model once (downloads it on first use, ~220 MB)."""
    global _model
    with _model_lock:
        if _model is None:
            from fastembed import TextEmbedding

            logger.info("Loading embedding model %s ...", EMBEDDING_MODEL)
            MODEL_CACHE_DIR.mkdir(parents=True, exist_ok=True)
            _model = TextEmbedding(model_name=EMBEDDING_MODEL, cache_dir=str(MODEL_CACHE_DIR))
    return _model


def _normalize(vectors: np.ndarray) -> np.ndarray:
    norms = np.linalg.norm(vectors, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    return (vectors / norms).astype(np.float32)


def embed_texts(texts: list[str], batch_size: int = 64) -> np.ndarray:
    """Embed many texts. Returns an (n, dim) array of unit-length vectors."""
    model = get_model()
    vectors = []
    for i, vector in enumerate(model.embed(texts, batch_size=batch_size), start=1):
        vectors.append(vector)
        if i % 1000 == 0:
            logger.info("  embedded %d / %d chunks", i, len(texts))
    return _normalize(np.vstack(vectors))


def embed_query(text: str) -> np.ndarray:
    """Embed one search query. Returns a (dim,) unit-length vector."""
    return embed_texts([text])[0]
