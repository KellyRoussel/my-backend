"""Portfolio chatbot endpoints — no auth required (public).

Two endpoints:
- GET  /portfolio/ping  — instant health check, used by frontend to warm up Render
- POST /portfolio/chat  — main chat endpoint, returns SSE stream
"""
import json
import logging
from datetime import datetime

from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from database import SessionLocal
from dependencies.portfolio.portfolio_agent import PortfolioAgent
from models.database_models import PortfolioSession

logger = logging.getLogger(__name__)

portfolio_router = APIRouter(prefix="/portfolio", tags=["Portfolio"])

_MESSAGE_LIMIT = 8


class ChatRequest(BaseModel):
    session_id: str | None = None
    message: str
    history: list[dict] = []


@portfolio_router.get("/ping")
def ping():
    """Instant health check — used by the frontend to warm up the Render instance."""
    return {"status": "awake"}


@portfolio_router.post("/chat")
async def chat(request: ChatRequest):
    """Portfolio chatbot — returns an SSE stream of token events.

    Rate limiting: each anonymous session gets _MESSAGE_LIMIT free messages.
    Sessions are identified by a UUID stored in the visitor's localStorage.
    If no session_id is provided (first visit), a new session is created and
    its ID is returned in the first SSE event so the frontend can persist it.
    """
    db = SessionLocal()
    try:
        # Upsert session
        session: PortfolioSession | None = None
        if request.session_id:
            session = (
                db.query(PortfolioSession)
                .filter(PortfolioSession.id == request.session_id)
                .first()
            )

        if session is None:
            session = PortfolioSession()
            db.add(session)
            db.flush()  # populate session.id without committing yet

        session_id = session.id

        # Rate limit check
        if session.message_count >= _MESSAGE_LIMIT:
            db.close()

            async def _rate_limited():
                yield f"data: {json.dumps({'type': 'session', 'session_id': session_id})}\n\n"
                yield f"data: {json.dumps({'type': 'rate_limited'})}\n\n"
                yield f"data: {json.dumps({'type': 'done'})}\n\n"

            return StreamingResponse(
                _rate_limited(),
                media_type="text/event-stream",
                headers={
                    "Cache-Control": "no-cache",
                    "Connection": "keep-alive",
                    "X-Accel-Buffering": "no",
                },
            )

        # Increment message count and persist before streaming
        session.message_count += 1
        session.last_message_at = datetime.utcnow()
        db.commit()
    finally:
        db.close()

    agent = PortfolioAgent(session_id=session_id)

    async def event_generator():
        async for sse_line in agent.stream(
            history=request.history,
            user_message=request.message,
            session_id=session_id,
        ):
            yield sse_line

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
