import logging
from concurrent.futures import ThreadPoolExecutor

from flask import Blueprint, current_app, jsonify, request

from app.config import settings
from app.decorators.security import signature_required
from app.utils.whatsapp_utils import is_valid_whatsapp_message, process_whatsapp_message

webhook_blueprint = Blueprint("webhook", __name__)

# Replies are made in the background so WhatsApp gets its "200 OK" right away
# (otherwise it retries the webhook). A small pool keeps a burst of messages
# from starting hundreds of threads.
_workers = ThreadPoolExecutor(max_workers=8, thread_name_prefix="reply")


def process_in_background(app, body: dict) -> None:
    # A worker thread has no app context, so we open one here
    with app.app_context():
        try:
            process_whatsapp_message(body)
        except Exception:
            logging.exception("Failed to process the message")


def handle_message():
    """Handle incoming webhook events from the WhatsApp API.

    Every message we send triggers more webhook calls (sent, delivered, read);
    those status updates are acknowledged and ignored.
    """
    body = request.get_json(silent=True)
    if not isinstance(body, dict):
        logging.error("Webhook body is not valid JSON")
        return jsonify({"status": "error", "message": "Invalid JSON provided"}), 400

    value = (body.get("entry") or [{}])[0].get("changes", [{}])[0].get("value", {})
    if value.get("statuses"):
        return jsonify({"status": "ok"}), 200

    if not is_valid_whatsapp_message(body):
        return jsonify({"status": "error", "message": "Not a WhatsApp API event"}), 404

    app = current_app._get_current_object()
    _workers.submit(process_in_background, app, body)
    return jsonify({"status": "ok"}), 200


# Required webhook verification for WhatsApp
def verify():
    mode = request.args.get("hub.mode")
    token = request.args.get("hub.verify_token")
    challenge = request.args.get("hub.challenge")

    if not (mode and token):
        logging.info("MISSING_PARAMETER")
        return jsonify({"status": "error", "message": "Missing parameters"}), 400
    if mode == "subscribe" and token == settings.verify_token:
        logging.info("WEBHOOK_VERIFIED")
        return challenge, 200
    logging.info("VERIFICATION_FAILED")
    return jsonify({"status": "error", "message": "Verification failed"}), 403


@webhook_blueprint.route("/webhook", methods=["GET"])
def webhook_get():
    return verify()


@webhook_blueprint.route("/webhook", methods=["POST"])
@signature_required
def webhook_post():
    return handle_message()
