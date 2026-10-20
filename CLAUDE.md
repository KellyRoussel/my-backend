# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

FastAPI backend serving as a multi-feature authentication and social media management API. Supports OAuth (Google & Instagram), Instagram posting with AI-generated content, image analysis, and audio transcription via OpenAI.

## Commands

```bash
# Install dependencies
pip install -r requirements.txt

# Run dev server (auto-reload)
uvicorn main:app --reload

# Run production
uvicorn main:app --host 0.0.0.0 --port $PORT

# VS Code debugging: Run and Debug → "Python Debugger: FastAPI"
```

Deployment is on Render.com (`render.yaml`). Build: `pip install -r requirements.txt`, Start: `uvicorn main:app --host 0.0.0.0 --port $PORT`.

No test suite or linter is currently configured.

## Architecture

**Entry point**: `main.py` — FastAPI app with lifespan context manager that initializes `GoogleAuthService` on startup. Registers routers with auth dependencies and mounts `static/uploads/` for temporary image storage.

**Layer structure**:
- `endpoints/` — FastAPI routers (request handling, validation)
- `dependencies/` — Service layer (business logic, external API calls)
- `models/` — Pydantic schemas (`authentication.py`) and SQLAlchemy ORM models (`database_models.py`)
- `config.py` — Pydantic `BaseSettings` loading from `.env`
- `database.py` — SQLAlchemy session management (NullPool for Supabase free-tier). Two engines: `SessionLocal` (main `DATABASE_URL`) and `BobobidouSessionLocal` (`BOBOBIDOU_DATABASE_URL`, role `bobobidou_app`, falls back to the main URL when unset)

**Routers**:
- `authentication_router` — OAuth flows (Google, Instagram), JWT token management (access/refresh)
- `insta_poster_router` — AI content generation via OpenAI + Instagram Graph API posting
- `bobobidou_router` — Image-to-ingredients extraction via OpenAI vision, limited per day by `dependencies/photo_quota_service.py` (`BOBOBIDOU_DAILY_PHOTO_LIMIT` per user, `BOBOBIDOU_GLOBAL_DAILY_PHOTO_LIMIT` for everyone, UTC days, 429 with a `code` when reached). The counters in `bobobidou.photo_usage` are keyed by an HMAC of the user id and have no FK to `users`: they survive an account deletion, so deleting/recreating an account does not reset the limit. `daily_photo_limit()` is where subscribers will get more
- `utils_router` — Audio transcription via OpenAI Whisper
- `account_deletion_router` — Public HTML pages at `/account/delete` to delete one's Bobobidou account without the app (Google sign-in → confirmation; the fresh Google token is revoked). The authenticated API equivalent is `DELETE /bobobidou/account`. Both use `dependencies/account_service.py`, which only deletes the user and refresh tokens in the `bobobidou` schema

**Auth flow**: OAuth state stored in `AuthState` DB table for CSRF protection. After OAuth callback, JWT access (60min) and refresh (30day) tokens are issued and stored in DB. Token validation happens via `auth_handler.py` dependency.

**Service pattern**: `BaseAuthService` abstract class in `dependencies/auth_services/` with concrete implementations for Google and Instagram. `InstaService` handles Instagram Graph API interactions (single/carousel posts).

**Key conventions**:
- All endpoints are async; external HTTP calls use `httpx.AsyncClient`
- OpenAI calls use `AsyncOpenAI` with separate API keys per feature
- User ID set on `request.state.user_id` by auth middleware
- Images uploaded to `static/uploads/` with UUID filenames, deleted after Instagram posting
- Tokens use soft-delete (`is_active` flag); old tokens deactivated on re-auth
- Database: PostgreSQL via Supabase, SQLAlchemy ORM with `declarative_base()`
- Bobobidou data is isolated in the `bobobidou` Postgres schema (`models/bobobidou_models.py`, own `BobobidouBase`), reachable only by the `bobobidou_app` role. Its users and refresh tokens never go to `public`: `dependencies/app_auth.py` picks the store from the `{app}` path param, and the JWTs carry an `app` claim. `bobobidou_auth_handler` only accepts `app=bobobidou` tokens and `auth_handler` refuses them. Bobobidou is moving to its own repo, `bobobidou_backend` (Cloud Run): since then that repo owns the `bobobidou` schema's migrations (version table `bobobidou.alembic_version`) and this repo's Alembic ignores the schema. New Bobobidou tables and Bobobidou changes go there
