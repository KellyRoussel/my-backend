---
name: Portfolio chat rate-limit bug
description: Silent failure when backend returns plain JSON for rate-limited sessions instead of SSE stream
type: project
---

When `session.message_count >= 8`, the `/portfolio/chat` endpoint returns a plain JSON dict `{"detail": "rate_limited", "session_id": ...}` with a 200 status, not a `StreamingResponse`. The frontend `useChatSession.ts` assumed all 200 responses were SSE streams and called `response.body.getReader()` on the JSON body. No `data:` lines were found, the reader finished without a `done` event, and the assistant placeholder message remained `{isStreaming: true, content: ""}` forever. `MessageBubble` returns `null` for that state — result: silent black hole with no visible bubble.

**Fix applied (2026-03-16):**
- `useChatSession.ts`: check `content-type` header before entering SSE reader loop; if not `text/event-stream`, parse as JSON and set `isRateLimited` state
- `ChatInterface.tsx`: import and render `RateLimitCard` (pre-existing component, never wired up) when `isRateLimited` is true; disable textarea and send button; show alternate placeholder

**Why:** The `RateLimitCard` component existed but was never connected. The non-SSE response path was never guarded.

**How to apply:** Any time the backend returns a mix of SSE and JSON from the same endpoint, guard the frontend stream reader with a content-type check first.
