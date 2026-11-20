"""Where the knowledge base is stored on disk, and the embedding model used."""

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = Path(os.getenv("DATA_DIR", PROJECT_ROOT / "data"))

# Output of the extraction agent (one JSON object per extracted page)
RAW_DIR = DATA_DIR / "raw"
PAGES_FILE = RAW_DIR / "pages.jsonl"
CRAWL_STATE_FILE = RAW_DIR / "crawl_state.json"

# Output of the indexing step (what the bot loads at runtime)
INDEX_DIR = DATA_DIR / "index"
CHUNKS_FILE = INDEX_DIR / "chunks.jsonl"
EMBEDDINGS_FILE = INDEX_DIR / "embeddings.npy"
MANIFEST_FILE = INDEX_DIR / "manifest.json"

# Small (~220 MB) multilingual model: understands English, Urdu and Roman Urdu.
# Runs locally on CPU, no API key needed. Downloaded once on first use.
EMBEDDING_MODEL = os.getenv(
    "EMBEDDING_MODEL", "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
)
MODEL_CACHE_DIR = DATA_DIR / "models"
