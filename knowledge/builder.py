"""Build the knowledge base once: crawl -> chunk -> embed -> save to data/index/."""

import json
import logging
import shutil
from collections import Counter
from datetime import datetime, timezone

import numpy as np

from . import crawler
from .chunker import chunk_pages, embedding_text
from .embeddings import embed_texts
from .paths import (
    CHUNKS_FILE,
    EMBEDDING_MODEL,
    EMBEDDINGS_FILE,
    INDEX_DIR,
    MANIFEST_FILE,
    RAW_DIR,
)
from .retriever import index_exists

logger = logging.getLogger(__name__)


def build_index() -> dict:
    """Chunk and embed the crawled pages, and save the index to disk."""
    pages = crawler.load_pages()
    if not pages:
        raise RuntimeError(
            "No pages were extracted, so there is nothing to index. "
            "Check your internet connection and run again."
        )

    chunks = chunk_pages(pages)
    logger.info("Split %d pages into %d chunks. Embedding...", len(pages), len(chunks))
    vectors = embed_texts([embedding_text(c) for c in chunks])

    # Write to temporary files first so a crash never leaves a half-written index
    INDEX_DIR.mkdir(parents=True, exist_ok=True)
    tmp_chunks = CHUNKS_FILE.with_suffix(".tmp")
    with tmp_chunks.open("w", encoding="utf-8") as f:
        for chunk in chunks:
            f.write(json.dumps(chunk, ensure_ascii=False) + "\n")
    tmp_vectors = INDEX_DIR / "embeddings.tmp.npy"
    np.save(tmp_vectors, vectors)
    tmp_chunks.replace(CHUNKS_FILE)
    tmp_vectors.replace(EMBEDDINGS_FILE)

    manifest = {
        "built_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "embedding_model": EMBEDDING_MODEL,
        "pages": len(pages),
        "chunks": len(chunks),
        "pages_per_source": dict(Counter(p["source"] for p in pages)),
    }
    MANIFEST_FILE.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    return manifest


def build_knowledge_base(
    force: bool = False,
    reindex_only: bool = False,
    only: list[str] | None = None,
    max_depth: int = crawler.DEFAULT_MAX_DEPTH,
    max_pages: int = crawler.DEFAULT_MAX_PAGES,
) -> dict | None:
    """Run the extraction agent and build the index - but only if it was not built before.

    force:        delete everything and crawl all sites again
    reindex_only: keep the crawled pages, only redo chunking + embedding
    only:         re-crawl just these sources (by name), keep the rest
    """
    if index_exists() and not (force or reindex_only or only):
        manifest = json.loads(MANIFEST_FILE.read_text(encoding="utf-8"))
        logger.info(
            "Knowledge base already built on %s (%d chunks). Skipping. "
            "Use --force to crawl again.",
            manifest["built_at"],
            manifest["chunks"],
        )
        return None

    if force:
        logger.info("--force: deleting old crawl data and index")
        shutil.rmtree(RAW_DIR, ignore_errors=True)
        shutil.rmtree(INDEX_DIR, ignore_errors=True)

    if only:
        state = crawler.load_state()
        for name in only:
            state["completed_sources"].pop(name, None)
        crawler.save_state(state)

    if not reindex_only:
        crawler.crawl_all(max_depth=max_depth, max_pages=max_pages)

    manifest = build_index()
    logger.info("Knowledge base ready: %d pages, %d chunks", manifest["pages"], manifest["chunks"])
    for source, count in manifest["pages_per_source"].items():
        logger.info("  %-45s %4d pages", source, count)
    return manifest
