import logging

from flask import Flask

from app.config import check_settings, configure_logging
from app.views import webhook_blueprint
from knowledge import retriever
from knowledge.embeddings import get_model


def create_app() -> Flask:
    configure_logging()
    check_settings()

    app = Flask(__name__)
    app.register_blueprint(webhook_blueprint)

    # Load the knowledge base now, so the first WhatsApp message is not slow
    if retriever.get_retriever() is None:
        logging.warning(
            "Knowledge base not found. The bot will run but cannot answer from the "
            "scraped data until you run: python build_knowledge_base.py"
        )
    else:
        get_model()

    return app
