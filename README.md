# MyBackend

A shared FastAPI backend powering multiple personal apps. Each feature module serves a different application, all sharing a common authentication layer (Google & Instagram OAuth, JWT).

## Apps & Features

| App | Module | Description |
|---|---|---|
| **Bobobidou** | `/bobobidou` | Extracts ingredients from food photos using OpenAI vision |
| **Insta Poster** | `/insta_poster` | Generates Instagram captions from voice transcripts and posts to Instagram |
| **Investment** | `/investment` | Portfolio tracker with AI-generated recommendations (SSE streaming) |
| **Quiz Host** | `/quiz` | Party quiz with an ElevenLabs voice host and phone buzzers (WebSockets, no auth) — see [quiz_host/README.md](quiz_host/README.md) |
| *(shared)* | `/utils` | Audio transcription via OpenAI Whisper |
| *(shared)* | `/auth` | OAuth 2.0 (Google & Instagram) + JWT access/refresh tokens |

## Stack

- [FastAPI](https://fastapi.tiangolo.com/) + [SQLAlchemy](https://www.sqlalchemy.org/) (ORM)
- PostgreSQL via [Supabase](https://supabase.com/)
- [OpenAI](https://platform.openai.com/) — vision, transcription, chat completion
- [DeepAgents](https://pypi.org/project/deepagents/) + [LangChain](https://www.langchain.com/) — investment agent workflow
- [Tavily](https://tavily.com/) — web search for investment agents
- [yfinance](https://pypi.org/project/yfinance/) — stock price data
- [Langfuse](https://langfuse.com/) — optional LLM tracing
- Deployed on [Render.com](https://render.com/)

## Getting Started

### 1. Clone & install

```bash
git clone https://github.com/KellyRoussel/my-backend.git
cd my-backend
pip install -r requirements.txt
```

### 2. Configure environment

```bash
cp .env.example .env
```

Fill in the values in `.env` (see [.env.example](.env.example) for all required keys).

**Required secrets:**

| Variable | Where to get it |
|---|---|
| `openai_bobobidou_key` / `openai_instaposter_key` / `openai_investment_key` | [platform.openai.com](https://platform.openai.com/api-keys) |
| `google_client_id` / `google_client_secret` | [Google Cloud Console](https://console.cloud.google.com/) → APIs & Services → Credentials |
| `insta_client_id` / `insta_client_secret` | [Meta for Developers](https://developers.facebook.com/) |
| `secret_key` | Generate with `python -c "import secrets; print(secrets.token_hex(32))"` |
| `database_url` | PostgreSQL connection string (e.g. Supabase) |
| `openfigi_api_key` | [openfigi.com](https://www.openfigi.com/api) |
| `TAVILY_API_KEY` | [tavily.com](https://tavily.com/) |

### 3. Run database migrations

```bash
alembic upgrade head
```

### 4. Start the server

```bash
# Development (auto-reload)
uvicorn main:app --reload

# Production
uvicorn main:app --host 0.0.0.0 --port $PORT
```

API docs available at `http://localhost:8000/docs`.

## Project Structure

```
myBackend/
├── main.py                  # FastAPI app, middleware, router registration
├── config.py                # Pydantic Settings (reads from .env)
├── database.py              # SQLAlchemy session (NullPool for Supabase)
├── endpoints/               # FastAPI routers (one per app/feature)
│   ├── authentication.py    # Shared OAuth flows, token exchange & refresh
│   ├── bobobidou.py         # Bobobidou — ingredient extraction
│   ├── insta_poster.py      # Insta Poster — caption generation & posting
│   ├── investment.py        # Investment — portfolio CRUD, metrics, AI reco
│   ├── quiz.py              # Quiz Host — pages, REST & WebSockets (public)
│   └── utils.py             # Shared — audio transcription
├── dependencies/            # Business logic & service layer
│   ├── auth_handler.py      # JWT validation middleware (used by all apps)
│   ├── auth_services/       # Google & Instagram OAuth implementations
│   ├── insta_service.py     # Instagram Graph API (single & carousel posts)
│   ├── investment/          # Investment agents, tools, prompts
│   └── quiz/                # Quiz Host game state machine, rooms, ElevenLabs token
├── models/                  # Pydantic schemas + SQLAlchemy ORM models
├── domain/                  # Domain entities and value objects
├── repositories/            # Data access layer
├── alembic/                 # DB migrations
├── quiz_host/               # Quiz Host docs, agent config, question bank, standalone app
├── tests/quiz/              # Quiz Host tests (pytest)
├── static/quiz/             # Quiz Host web pages (host screen, player buzzer)
└── static/uploads/          # Temporary image storage (auto-cleaned after posting)
```

## API Overview

All endpoints except the auth ones require a JWT Bearer token in the `Authorization` header.

### Authentication (shared)

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/login/google/{app}` | Get Google OAuth URL |
| `GET` | `/login/insta/{app}` | Get Instagram OAuth URL |
| `GET` | `/auth/callback/{app}` | OAuth callback → redirects to app deep link |
| `GET` | `/auth/web-callback/{app}` | OAuth callback → redirects to web frontend |
| `GET` | `/auth/exchange/{app}` | Exchange OAuth code for JWT tokens |
| `POST` | `/auth/refresh-token` | Refresh access token |
| `POST` | `/auth/validate-token` | Validate an access token |
| `DELETE` | `/auth/revoke/{user_id}/{provider}` | Revoke a provider token |

### Bobobidou

| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/bobobidou/ingredients` | Extract ingredients from a food image |

### Insta Poster

| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/insta_poster/generate` | Generate an Instagram caption from a transcript |
| `POST` | `/insta_poster/post` | Post image(s) + caption to Instagram |
| `POST` | `/insta_poster/default_prompt` | Get the default caption generation prompt |

### Utils (shared)

| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/utils/transcript` | Transcribe an audio file |

### Investment

| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/investment/investments` | Add an investment (ISIN or ticker) |
| `GET` | `/investment/investments` | List portfolio investments |
| `PATCH` | `/investment/investments/{id}` | Update an investment |
| `DELETE` | `/investment/investments/{id}` | Soft-delete an investment |
| `GET` | `/investment/investments/{id}/price-history` | Price history for a single investment |
| `GET` | `/investment/portfolio/metrics` | Aggregated portfolio metrics |
| `GET` | `/investment/portfolio/price-history` | Portfolio value over time |
| `GET` | `/investment/profile` | Get investment profile |
| `PATCH` | `/investment/profile` | Update investment profile |
| `GET` | `/investment/recommendations/generate` | AI recommendations — SSE stream (v1) |
| `GET` | `/investment/recommendations/generate/v2` | AI recommendations — SSE stream (v2 DeepAgents) |
| `GET` | `/investment/recommendations/history` | List past recommendation reports |
| `GET` | `/investment/watchlist` | List watchlist items |
| `POST` | `/investment/watchlist` | Add to watchlist |
| `DELETE` | `/investment/watchlist/{id}` | Remove from watchlist |
| `GET` | `/investment/models` | List available LLM models |

### Quiz Host (public)

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/quiz` | Landing page: create or join a room |
| `GET` | `/quiz/host/{code}` · `/quiz/play/{code}` | Host screen (TV) · player buzzer (phone) |
| `POST` | `/quiz/api/rooms` | Create a room, returns its host key |
| `GET` | `/quiz/api/rooms/{code}/qr.svg` | QR code of the join URL |
| `GET` | `/quiz/api/rooms/{code}/eleven-token` | ElevenLabs conversation token (host key required) |
| `WS` | `/quiz/ws/{code}/player` · `/quiz/ws/{code}/host` | Buzzes and game state · host actions and agent tool calls |

## Deployment

Deployment is configured for Render.com via [`render.yaml`](render.yaml).

- **Build:** `pip install -r requirements.txt && alembic upgrade head`
- **Start:** `uvicorn main:app --host 0.0.0.0 --port $PORT`

Set all environment variables from `.env.example` in your Render dashboard (Settings → Environment).

## Health Check

```
GET /health → {"status": "ok"}
```
