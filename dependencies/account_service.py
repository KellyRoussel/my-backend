"""Account deletion: removes a user and everything tied to them from our database.

The `users` table is shared by every app of this backend (Bobobidou, portfolio,
Insta Poster, investment): deleting an account removes the user for all of them.
"""
import logging

import httpx
from sqlalchemy.orm import Session

from config import settings
from models.database_models import (
    User, GoogleToken, MyBackendToken, InstagramToken, DeviceToken,
    InvestmentProfile, Investment, InvestmentWatchlist, InvestmentReport,
)

logger = logging.getLogger(__name__)


async def revoke_google_grant(user_id: str, db: Session) -> None:
    """Revoke the user's Google grant (best effort: deletion must not depend on Google).

    Revoking a refresh token, or an access token that has one, revokes the whole
    grant. Google only sends the refresh token on the first consent, so we revoke
    the latest refresh token we have plus the active access token.
    """
    tokens = db.query(GoogleToken).filter(GoogleToken.user_id == user_id).order_by(GoogleToken.created_at.desc()).all()
    to_revoke = []
    latest_refresh = next((t.refresh_token for t in tokens if t.refresh_token), None)
    if latest_refresh:
        to_revoke.append(latest_refresh)
    active = next((t for t in tokens if t.is_active == "true"), None)
    if active and active.access_token not in to_revoke:
        to_revoke.append(active.access_token)

    async with httpx.AsyncClient(timeout=10) as client:
        for token in to_revoke:
            try:
                response = await client.post(
                    settings.google_revoke_url,
                    data={"token": token},
                    headers={"Content-Type": "application/x-www-form-urlencoded"},
                )
                # 400 = token already expired or revoked: nothing left to revoke
                if response.status_code not in (200, 400):
                    logger.warning("Google revoke returned %s for user %s", response.status_code, user_id)
            except httpx.HTTPError as e:
                logger.warning("Google revoke failed for user %s: %s", user_id, e)


async def delete_user_account(user_id: str, db: Session) -> bool:
    """Revoke the Google grant and delete the user with all their rows.

    Returns False if the user does not exist.
    """
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        return False

    await revoke_google_grant(user_id, db)

    try:
        # Rows referencing users.id, children first (investment_transactions
        # are removed by their ON DELETE CASCADE on investments).
        for model in (
            GoogleToken, MyBackendToken, InstagramToken, DeviceToken,
            InvestmentReport, InvestmentWatchlist, Investment, InvestmentProfile,
        ):
            db.query(model).filter(model.user_id == user_id).delete(synchronize_session=False)
        db.delete(user)
        db.commit()
    except Exception:
        db.rollback()
        raise

    logger.info("Deleted account %s", user_id)
    return True
