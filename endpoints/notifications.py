"""Push notification endpoints — device token registration + cron-triggered daily push."""
import logging
from datetime import datetime

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from config import settings
from database import get_db
from dependencies.notifications.daily_push_service import run_daily_portfolio_push
from models.database_models import DeviceToken

logger = logging.getLogger(__name__)

notifications_router = APIRouter(prefix="/notifications", tags=["Notifications"])
cron_router = APIRouter(prefix="/cron", tags=["Cron"])


class DeviceTokenRequest(BaseModel):
    push_token: str
    device_type: str = "android"


@notifications_router.post("/device-token")
def register_device_token(
    body: DeviceTokenRequest,
    request: Request,
    db: Session = Depends(get_db),
):
    """Register (or re-activate) the caller's FCM device token."""
    user_id = request.state.user_id

    existing = db.query(DeviceToken).filter(
        DeviceToken.push_token == body.push_token
    ).first()

    if existing:
        existing.user_id = user_id
        existing.device_type = body.device_type
        existing.is_active = True
        existing.updated_at = datetime.utcnow()
    else:
        db.add(DeviceToken(
            user_id=user_id,
            push_token=body.push_token,
            device_type=body.device_type,
            is_active=True,
        ))

    db.commit()
    return {"detail": "Device token registered."}


@cron_router.post("/daily-portfolio-push")
def daily_portfolio_push(x_cron_secret: str = Header(default="")):
    """Cron-triggered: send each user their cumulative portfolio gain/loss.

    Protected by the X-Cron-Secret header (no JWT, as this is called by a scheduler).
    Runs synchronously so the caller gets a real success/failure status.
    """
    if not settings.cron_secret or x_cron_secret != settings.cron_secret:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid cron secret")

    summary = run_daily_portfolio_push()
    return summary
