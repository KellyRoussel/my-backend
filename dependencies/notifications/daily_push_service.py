"""Daily push notification job: send each user their cumulative portfolio gain/loss."""
import logging
from decimal import Decimal

from sqlalchemy.orm import Session

from database import SessionLocal
from dependencies.investment.portfolio_calculator import PortfolioCalculator
from dependencies.notifications import fcm_client
from models.database_models import DeviceToken, InvestmentProfile

logger = logging.getLogger(__name__)

_CURRENCY_SYMBOLS = {"EUR": "€", "USD": "$", "GBP": "£"}


def _fmt_amount(value: Decimal, currency: str) -> str:
    symbol = _CURRENCY_SYMBOLS.get(currency, currency)
    sign = "+" if value >= 0 else "-"
    grouped = f"{abs(round(value)):,.0f}".replace(",", " ")  # narrow no-break space
    return f"{sign}{grouped} {symbol}"


def _fmt_percent(value: Decimal) -> str:
    sign = "+" if value >= 0 else "-"
    return f"{sign}{abs(value):.1f}".replace(".", ",") + " %"


def _build_message(total_gain_loss: Decimal, pct: Decimal, currency: str) -> str:
    return f"Gain cumulé : {_fmt_amount(total_gain_loss, currency)} ({_fmt_percent(pct)})"


def run_daily_portfolio_push() -> dict:
    """Compute cumulative gain/loss per user and send a push to each active device token.

    Returns a summary dict: {sent, failed, deactivated, users}.
    """
    db: Session = SessionLocal()
    sent = 0
    failed = 0
    deactivated = 0
    user_ids: set[str] = set()
    try:
        tokens = db.query(DeviceToken).filter(DeviceToken.is_active == True).all()

        # Group active tokens by user to compute portfolio metrics once per user.
        tokens_by_user: dict[str, list[DeviceToken]] = {}
        for tok in tokens:
            tokens_by_user.setdefault(tok.user_id, []).append(tok)

        calculator = PortfolioCalculator(db)

        for user_id, user_tokens in tokens_by_user.items():
            profile = db.query(InvestmentProfile).filter(
                InvestmentProfile.user_id == user_id
            ).first()
            currency = (profile.currency_preference if profile else None) or "USD"

            try:
                metrics = calculator.calculate_portfolio_metrics(user_id, currency)
            except Exception:
                logger.exception("Failed to compute metrics for user %s", user_id)
                failed += len(user_tokens)
                continue

            if metrics.investment_count == 0:
                logger.info("Skipping user %s: empty portfolio", user_id)
                continue

            body = _build_message(
                metrics.total_gain_loss, metrics.total_gain_loss_percent, currency
            )

            for tok in user_tokens:
                user_ids.add(user_id)
                try:
                    ok = fcm_client.send_push(tok.push_token, "Mon portefeuille", body)
                except Exception:
                    logger.exception("Push send error for token %s", tok.id)
                    failed += 1
                    continue
                if ok:
                    sent += 1
                else:
                    tok.is_active = False
                    deactivated += 1

        db.commit()
    finally:
        db.close()

    summary = {"sent": sent, "failed": failed, "deactivated": deactivated, "users": len(user_ids)}
    logger.info("Daily portfolio push summary: %s", summary)
    return summary
