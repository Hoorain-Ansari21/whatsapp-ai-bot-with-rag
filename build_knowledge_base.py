"""Run the website extraction agent and build the RAG knowledge base.

Runs only once: if the knowledge base already exists it does nothing.

    python build_knowledge_base.py                 # first build (skips if already built)
    python build_knowledge_base.py --force         # crawl everything again from scratch
    python build_knowledge_base.py --reindex       # keep crawled pages, only re-embed
    python build_knowledge_base.py --only "PEEF (Punjab Educational Endowment Fund)"
                                                   # re-crawl one source, keep the rest

Restart the bot after rebuilding so it loads the new data.
"""

import argparse
import logging
import sys

from knowledge.builder import build_knowledge_base
from knowledge.crawler import DEFAULT_MAX_DEPTH, DEFAULT_MAX_PAGES
from knowledge.sources import SOURCES


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--force", action="store_true", help="delete old data and crawl all sites again")
    parser.add_argument("--reindex", action="store_true", help="re-chunk and re-embed already crawled pages")
    parser.add_argument("--only", action="append", metavar="SOURCE", help="re-crawl only this source (repeatable)")
    parser.add_argument("--depth", type=int, default=DEFAULT_MAX_DEPTH, help="link depth to follow (default 2)")
    parser.add_argument("--max-pages", type=int, default=DEFAULT_MAX_PAGES, help="page budget per site (default 300)")
    parser.add_argument("--list-sources", action="store_true", help="print the source names and exit")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(message)s",
        stream=sys.stdout,
    )
    # These libraries are very chatty at INFO level
    for noisy in ("trafilatura", "urllib3", "pypdf"):
        logging.getLogger(noisy).setLevel(logging.ERROR)

    names = [s.name for s in SOURCES]
    if args.list_sources:
        print("\n".join(names))
        return 0
    unknown = [n for n in args.only or [] if n not in names]
    if unknown:
        logging.error("Unknown source(s): %s. Use --list-sources to see the names.", ", ".join(unknown))
        return 2

    try:
        build_knowledge_base(
            force=args.force,
            reindex_only=args.reindex,
            only=args.only,
            max_depth=args.depth,
            max_pages=args.max_pages,
        )
    except KeyboardInterrupt:
        logging.warning("Stopped. Run the same command again to resume the crawl.")
        return 130
    except RuntimeError as error:
        logging.error("%s", error)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
