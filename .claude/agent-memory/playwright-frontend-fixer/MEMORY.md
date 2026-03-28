# Playwright Frontend Fixer — Memory Index

## Project

- [Portfolio chat rate-limit bug](project_portfolio_chat_ratelimit.md) — Silent bubble failure when `/portfolio/chat` returns plain JSON (rate-limited) instead of SSE stream; fix: content-type guard + `isRateLimited` state + `RateLimitCard` wiring
