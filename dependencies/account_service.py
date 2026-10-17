"""Bobobidou account deletion (required by Google Play).

Only touches the `bobobidou` schema: the user and their refresh tokens. The
personal apps' users in `public` are never deleted here.
"""
import logging

import httpx
from sqlalchemy.orm import Session

from config import settings
from models.bobobidou_models import BobobidouUser, BobobidouRefreshToken

logger = logging.getLogger(__name__)


async def revoke_google_token(token: str) -> None:
    """Revoke a Google token, and with it the user's grant to our client (best effort).

    Bobobidou does not store Google tokens: this is only possible when we have just
    obtained one, i.e. on the web deletion page after the Google sign-in.
    """
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.post(
                settings.google_revoke_url,
                data={"token": token},
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
        # 400 = token already expired or revoked: nothing left to revoke
        if response.status_code not in (200, 400):
            logger.warning("Google revoke returned %s", response.status_code)
    except httpx.HTTPError as e:
        logger.warning("Google revoke failed: %s", e)


def delete_bobobidou_account(user_id: str, db: Session) -> bool:
    """Delete a Bobobidou user and their refresh tokens.

    `db` must be a Bobobidou session. Returns False if the user does not exist.
    """
    user = db.query(BobobidouUser).filter(BobobidouUser.id == user_id).first()
    if not user:
        return False

    try:
        # Also removed by ON DELETE CASCADE, deleted explicitly to not depend on it
        db.query(BobobidouRefreshToken).filter(
            BobobidouRefreshToken.user_id == user_id
        ).delete(synchronize_session=False)
        db.delete(user)
        db.commit()
    except Exception:
        db.rollback()
        raise

    logger.info("Deleted Bobobidou account %s", user_id)
    return True
