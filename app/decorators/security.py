import hashlib
import hmac
import logging
from functools import wraps

from flask import jsonify, request

from app.config import settings


def validate_signature(payload: bytes, signature: str) -> bool:
    """Check that the request really comes from Meta (signed with our App Secret)."""
    expected_signature = hmac.new(
        settings.app_secret.encode("latin-1"),
        msg=payload,
        digestmod=hashlib.sha256,
    ).hexdigest()
    return hmac.compare_digest(expected_signature, signature)


def signature_required(f):
    """Decorator: reject webhook requests without a valid X-Hub-Signature-256 header."""

    @wraps(f)
    def decorated_function(*args, **kwargs):
        signature = request.headers.get("X-Hub-Signature-256", "").removeprefix("sha256=")
        if not validate_signature(request.get_data(), signature):
            logging.info("Signature verification failed!")
            return jsonify({"status": "error", "message": "Invalid signature"}), 403
        return f(*args, **kwargs)

    return decorated_function
