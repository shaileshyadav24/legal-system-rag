# API Reference

Base URL (local dev): `http://localhost:8000`

All endpoints are JSON in / JSON out. CORS currently allows all origins (`allow_origins=["*"]` in `app.py`).

## Auth

Auth is JWT-based. `POST /auth/register` and `POST /auth/login` return an `access_token`. Send it on every subsequent request as:

```
Authorization: Bearer <access_token>
```

Tokens expire after `JWT_EXPIRE_MINUTES` (server-configured, currently 1440 = 24h). Calling `POST /auth/logout` invalidates the token immediately server-side (it doesn't just expire on its own) — the FE should discard the stored token on logout regardless, but a revoked token will get `401` if reused (e.g. from another open tab).

**Rate limiting:** `POST /auth/register`, `POST /auth/login`, `POST /auth/forgot-password`, and `POST /auth/reset-password` are each capped at **4 requests per client IP per 15 minutes**, tracked independently per endpoint. Exceeding it returns:
```json
{ "detail": "Too many attempts. Try again in up to 15 minutes." }
```
with status `429`. The FE should surface this distinctly from a normal `401`/`422` (e.g. "too many attempts, please wait" rather than "wrong password").

### `POST /auth/register`

Create an account and get a token in one call.

Request body:
```json
{
  "email": "user@example.com",
  "password": "at-least-something-reasonable",
  "full_name": "Jane Doe"
}
```

Response `200`:
```json
{
  "access_token": "eyJhbGciOi...",
  "token_type": "bearer",
  "user": {
    "id": "6a4ad88dcd56258f7ba07ff6",
    "email": "user@example.com",
    "full_name": "Jane Doe",
    "role": "user"
  }
}
```

Errors:
- `409` — email already registered
- `422` — validation error (bad email format, missing field, etc. — standard FastAPI/pydantic shape)
- `429` — rate limited (see above)

### `POST /auth/login`

Request body:
```json
{ "email": "user@example.com", "password": "..." }
```

Response `200`: same shape as `/auth/register`.

Errors:
- `401` — incorrect email or password
- `403` — account disabled
- `429` — rate limited (see above)

### `GET /auth/me`

Requires `Authorization` header. Returns the current user's profile.

Response `200`:
```json
{ "id": "...", "email": "...", "full_name": "...", "role": "user" }
```

Errors: `401` — missing/invalid/expired/revoked token, or user no longer exists.

### `POST /auth/logout`

Requires `Authorization` header. Revokes the current token so it can no longer be used, even if not yet expired.

Response: `204 No Content`.

Errors: `401` — token already invalid/expired/revoked.

### `POST /auth/forgot-password`

Request body:
```json
{ "email": "user@example.com" }
```

Response `200` (always this shape, whether or not the email is registered — avoids leaking which emails have accounts):
```json
{
  "detail": "If an account with that email exists, a password reset token has been generated.",
  "reset_token": "8WyuTrDrVJEev3-5FL1BHGpdRkyaju39qJEZGUuGJNA"
}
```

> **Dev-only note:** no email delivery is wired up on the backend yet, so `reset_token` is a real, usable value in the response right now (it'll be `null` if the email doesn't match an account). Once email sending is added server-side, this field will be removed and the token will only ever reach the user via email — **don't build permanent FE UI that displays `reset_token` to the user**; treat it as a temporary stand-in for local/dev testing only.

The token expires in 30 minutes and is single-use.

Errors: `429` — rate limited (see above).

### `POST /auth/reset-password`

Request body:
```json
{ "token": "<reset_token from forgot-password>", "new_password": "new-password-value" }
```

Response: `204 No Content`.

Errors:
- `400` — token invalid, expired, or already used
- `429` — rate limited (see above)

## Chat queries

Both endpoints require `Authorization`. They differ only in answer tone/vocabulary (`/user` = plain language for non-lawyers, `/lawyer` = precise legal terminology) — same request/response shape.

### `POST /query/user` and `POST /query/lawyer`

Request body:
```json
{
  "query": "What did the court say about unreasonable search and seizure?",
  "collection_name": null,
  "session_id": null
}
```

- `collection_name` (optional) — restrict retrieval to one dataset. Valid values: `SCC`, `FCA`, `FC`, `TCC`, `CMAC`, `CHRT`, `SST`, `RPD`, `RAD`, `RLLR`, `ONCA`. Omit to search across all of them.
- `session_id` (optional) — pass the `session_id` returned by a previous call to continue the same conversation (server loads recent turns from that session as context). Omit on the first message of a new conversation; the server creates one and returns its id.

Response `200`:
```json
{
  "answer": "In R v Smith, the Supreme Court of Canada held that...",
  "urls": ["https://example.com/case.pdf"],
  "session_id": "6a4ad75d123aeb6c54a06e41"
}
```

**Always store `session_id` from the response and pass it back on the next call in the same conversation** — the server no longer accepts client-supplied chat history; it's all loaded server-side by `session_id`.

Errors:
- `401` — missing/invalid/expired/revoked token
- `404` — `collection_name` isn't one of the valid dataset codes above
- `204 No Content` — no relevant context was found for the query (empty body — don't try to parse JSON on this status)
- `500` — the LLM failed to generate a response

## Chat history

All require `Authorization` and only ever return/act on sessions owned by the calling user.

### `GET /chat/sessions`

Response `200`:
```json
[
  {
    "id": "6a4ad75d123aeb6c54a06e41",
    "role": "user",
    "title": "What did the court say about unreasonable search and seizure",
    "created_at": "2026-07-05T22:14:53.760000",
    "updated_at": "2026-07-05T22:14:55.560000"
  }
]
```
Sorted most-recently-updated first. `title` is auto-set to the first ~60 characters of the session's first query.

### `GET /chat/sessions/{session_id}/messages`

Response `200`:
```json
[
  {
    "query": "What did the court say about unreasonable search and seizure?",
    "answer": "In R v Smith, the Supreme Court of Canada held that...",
    "urls": ["https://example.com/case.pdf"],
    "created_at": "2026-07-05T22:14:55.560000"
  }
]
```
Sorted oldest-first (chronological conversation order).

Errors: `404` — session doesn't exist or isn't owned by the caller.

### `DELETE /chat/sessions/{session_id}`

Response: `204 No Content`. Deletes the session and all its messages.

Errors: `404` — session doesn't exist or isn't owned by the caller.
