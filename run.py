"""Start the WhatsApp bot.

On the very first start the knowledge base does not exist yet, so the website
extraction agent runs once (this can take a while) before the bot starts.
After that it is never run again unless you call build_knowledge_base.py --force.
"""

import logging
import os

from app import create_app
from app.config import configure_logging
from knowledge.builder import build_knowledge_base
from knowledge.retriever import index_exists

if __name__ == "__main__":
    configure_logging()
    if not index_exists() and os.getenv("AUTO_BUILD_KB", "true").lower() == "true":
        logging.info("First start: building the knowledge base (one time only)...")
        try:
            build_knowledge_base()
        except RuntimeError as error:
            logging.error("Knowledge base could not be built: %s", error)

    app = create_app()
    logging.info("Flask app started")
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "8000")))
else:
    # For production servers like gunicorn: `gunicorn run:app`
    app = create_app()
