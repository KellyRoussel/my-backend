"""Firebase Cloud Messaging client for sending push notifications."""
import json
import logging
import threading

import firebase_admin
from firebase_admin import credentials, exceptions as fb_exceptions, messaging

from config import settings

logger = logging.getLogger(__name__)

_init_lock = threading.Lock()
_app = None


def _get_app():
    """Lazily initialize the firebase_admin app from the service account JSON in settings."""
    global _app
    if _app is not None:
        return _app
    with _init_lock:
        if _app is not None:
            return _app
        if not settings.firebase_credentials_json:
            raise RuntimeError("FIREBASE_CREDENTIALS_JSON is not configured")
        cred = credentials.Certificate(json.loads(settings.firebase_credentials_json))
        _app = firebase_admin.initialize_app(cred)
        return _app


def send_push(token: str, title: str, body: str) -> bool:
    """Send a push notification to a single device token.

    Returns True if delivered. Returns False if the token is no longer valid
    (unregistered / invalid argument) so the caller can deactivate it.
    Other transient errors are re-raised.
    """
    _get_app()
    message = messaging.Message(
        token=token,
        notification=messaging.Notification(title=title, body=body),
    )
    try:
        messaging.send(message)
        return True
    except (messaging.UnregisteredError, ValueError) as exc:
        logger.warning("FCM token invalid, will deactivate: %s", exc)
        return False
    except fb_exceptions.InvalidArgumentError as exc:
        logger.warning("FCM invalid argument for token, will deactivate: %s", exc)
        return False
