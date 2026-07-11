# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A FastAPI RAG (Retrieval-Augmented Generation) API for Canadian legal case law, split into **two independently deployable services** that share one MongoDB database and one Redis instance:
- **Auth service** (`apps/auth/app.py`, port 8001) — registration, login, logout, forgot/reset password.
- **Chat service** (`apps/chat/app.py`, port 8000) — the RAG query endpoints and chat session history. Embeds a query, retrieves the closest-matching chunk via MongoDB Atlas Vector Search, and generates a grounded answer with a local Ollama model (`OLLAMA_MODEL`, e.g. `tinyllama`).

## Commands

Requires a `.env` (see `.env.example`) with `MONGODB_URI` pointing at a MongoDB Atlas cluster (Atlas Vector Search is Atlas-only - it doesn't work against a plain self-hosted `mongod`), plus `MONGODB_DB_NAME`, `JWT_SECRET`, `JWT_EXPIRE_MINUTES`, `REDIS_URL`, `ALLOWED_ORIGINS`, `RESEND_API_KEY`, `RESEND_FROM_EMAIL`, `PASSWORD_RESET_URL`, `OLLAMA_HOST`, `OLLAMA_MODEL`. Both services read the same `.env` - `libs/shared/config.py` is shared. Also requires a reachable Redis instance (see below for local dev).

Run both services locally (separate terminals/processes):
```bash
uvicorn apps.auth.app:app --port 8001 --host 0.0.0.0
uvicorn apps.chat.app:app --port 8000 --host 0.0.0.0
```
Chat service requires Ollama running with the model pulled:
```bash
ollama serve
ollama pull tinyllama
```

Install dependencies (each service has its own requirements file, since they don't share all dependencies - e.g. only auth needs `bcrypt`/`resend`, only chat needs `ollama`/`chromadb`):
```bash
pip install -r apps/auth/requirements.txt -r apps/chat/requirements.txt   # for local dev running both
# or just one, if only working on one service:
pip install -r apps/auth/requirements.txt
pip install -r apps/chat/requirements.txt
```

Ingest datasets into MongoDB (populates the `case_law_documents` collection and creates its Atlas Search vector index, run once before querying - has its own `dataset/requirements.txt`, install that first: `pip install -r dataset/requirements.txt`):
```bash
python dataset/dataset.py
```

Docker (separate images per service): each runs as a non-root `appuser`, defines a `HEALTHCHECK` against `GET /health` (liveness only - no DB/Redis round trip, so a transient blip on either doesn't get the container killed by an orchestrator), and runs uvicorn with multiple worker processes (`UVICORN_WORKERS`, defaults to 4 if unset - tune to the container's CPU allocation, or leave at the default and scale horizontally by running more container replicas instead).
```bash
docker build -f apps/auth/Dockerfile -t nextwork-auth-service .
docker build -f apps/chat/Dockerfile -t nextwork-chat-service .
docker run -p 8001:8001 --env-file .env nextwork-auth-service
docker run -p 8000:8000 --env-file .env nextwork-chat-service
```

**Local testing without a real Atlas cluster**: `mongodb/mongodb-atlas-local` is a Docker image that bundles `mongot`, so `$vectorSearch` works against it — a plain `mongo:7` container cannot run `$vectorSearch` at all (`OperationFailure: $vectorSearch stage is only allowed on MongoDB Atlas`). Run it with `docker run -d -p 27017:27017 mongodb/mongodb-atlas-local`, and connect with `MONGODB_URI=mongodb://localhost:27017/?directConnection=true` (its replica set otherwise advertises an internal container hostname the host can't resolve).

**Local Redis**: plain upstream Redis is fine (no Atlas-style managed-only feature is used) — `docker run -d -p 6379:6379 redis:7`, then `REDIS_URL=redis://localhost:6379/0`.

There is no test suite (CI's `pytest` step is commented out in `.github/workflows/ci.yml`, and no test files exist).

## Architecture

Persistence is MongoDB (Atlas required — Atlas Vector Search is used for retrieval and doesn't work against a plain `mongod`; see "Local testing" above for a workaround) plus Redis for short-lived, high-churn data. `libs/shared/db.py` owns the single `pymongo.MongoClient` and five Mongo collections: `users`, `chat_sessions`, `chat_messages`, `case_law_documents`, `password_reset_tokens`. `libs/shared/redis_client.py` owns the single `redis.Redis` client, used for revoked-token lookups and auth rate-limit counters (previously the `revoked_tokens`/`rate_limit_attempts` Mongo collections — moved to Redis since neither needs durability and both are hit on close to every request). Both services connect to the *same* Mongo database and the *same* Redis instance — there's no data partitioning between them.

**Cross-service auth**: the chat service never calls the auth service over HTTP. It independently decodes and verifies JWTs using the shared `JWT_SECRET`, queries the shared `users` collection, and checks revocation against the shared Redis instance (`libs/shared/jwt_auth.py`, imported by both services). This avoids a synchronous runtime dependency between the two services for every chat/query request - if the auth service is down, already-issued tokens still work fine against the chat service. The tradeoff: if the chat service is the first thing ever started against a fresh database, `users` won't have its index yet until the auth service runs at least once and calls `ensure_auth_indexes()` (queries still work, just unindexed until then).

Request flow for a query: `apps/chat/app.py` → `apps/chat/query_routes.py` (auth-gated via `libs/shared/jwt_auth.py`) → `apps/chat/chat_service.py` (load history for `session_id`, if any) → `apps/chat/retrieval.py` (Atlas `$vectorSearch`, embedding query + history combined) → `apps/chat/llm.py` → `apps/chat/response_utils.py` → `apps/chat/chat_service.py` (save the turn).

**Shared by both services:**
- **`libs/shared/config.py`** — env-driven settings (`MONGODB_URI`, `MONGODB_DB_NAME`, `JWT_SECRET`, `JWT_ALGORITHM`, `JWT_EXPIRE_MINUTES`, `REDIS_URL`, `ALLOWED_ORIGINS`, `RESEND_API_KEY`, `RESEND_FROM_EMAIL`, `PASSWORD_RESET_URL`, `OLLAMA_HOST`, `OLLAMA_MODEL`), loaded via `python-dotenv`. Every one of these (aside from `JWT_ALGORITHM`, which is fixed) is required — `_require()` raises at import time if any are missing, no silent defaults. `ALLOWED_ORIGINS` is parsed from a comma-separated string into a list. See `.env.example`. (Note: `RESEND_*`/`PASSWORD_RESET_URL` are only actually used by the auth service and `OLLAMA_HOST`/`OLLAMA_MODEL` only by the chat service, but all live in the one shared config module both services import - each service still needs the other's unused vars set in its environment for `libs/shared/config.py` to import successfully.)
- **`libs/shared/db.py`** — the Mongo client/collections, `ensure_auth_indexes()` / `ensure_chat_indexes()` (split by which service owns which collections), and `ensure_vector_search_index()` (chat-service-only: creates the Atlas Search vector index `case_law_vector_index` on `case_law_documents.embedding`, 384 dims/cosine — idempotent, called from `dataset/dataset.py` and `apps/chat/app.py`'s startup).
- **`libs/shared/redis_client.py`** — the single `redis.Redis` client (`redis.Redis.from_url(REDIS_URL)`) and `ensure_connection()` (fail-fast `PING` check, called from both services' startup, mirroring `libs/shared/db.py`'s Mongo equivalent).
- **`libs/shared/jwt_auth.py`** — JWT issuing/decoding (`pyjwt`, each token carries a `jti`), and two dependencies: `get_token_payload` (Bearer token → decoded payload, 401 if invalid/expired/revoked) and `get_current_user` (built on top, looks up the `sub` in `users`). `revoke_token`/`is_token_revoked` back logout, backed by Redis (`revoked_token:<jti>` keys) — a revoked `jti` is set with a TTL equal to the token's own remaining lifetime, so the key self-cleans once the token would've expired anyway. `create_access_token` (token issuance) is only ever called by the auth service, but lives here since verification and issuance must always agree on the signing/decoding logic.

**Auth service only** (`apps/auth/app.py`, `apps/auth/Dockerfile`, `apps/auth/requirements.txt`):
- **`apps/auth/password_auth.py`** — password hashing/verification (`bcrypt`). Split out from `jwt_auth.py` so the chat service's image doesn't need to install `bcrypt` for code it never calls.
- **`apps/auth/models.py`** — `UserRegister`, `UserLogin`, `UserOut`, `Token`, `ForgotPasswordRequest`, `ResetPasswordRequest`.
- **`apps/auth/routes.py`** — `POST /auth/register`, `POST /auth/login`, `GET /auth/me`, `POST /auth/logout`, `POST /auth/forgot-password`, `POST /auth/reset-password`.
- **`apps/auth/user_service.py`** — user CRUD/auth logic (`create_user`, `authenticate_user`, `update_password`, etc.).
- **`apps/auth/password_reset_service.py`** — forgot-password flow: `create_reset_token` (only stores a SHA-256 hash of the raw token, in `password_reset_tokens`, TTL 30 min, then emails the raw token via `email_service.send_password_reset_email`) and `reset_password` (validates hash/expiry/unused, then calls `update_password`). The raw token is never returned in the API response — it's only ever available inside `create_reset_token`, which immediately emails it.
- **`apps/auth/email_service.py`** — sends the password-reset email via [Resend](https://resend.com) (`RESEND_API_KEY`/`RESEND_FROM_EMAIL`), linking to `PASSWORD_RESET_URL?token=<raw_token>` (the FE's reset-password page, reading `token` from the query string). Raises a `500` on Resend delivery failure — deliberately not swallowed, since silently claiming success when the email didn't send would leave the user stuck.
- **`apps/auth/rate_limit.py`** — fixed-window rate limiting for the unauthenticated auth endpoints (`register`, `login`, `forgot-password`, `reset-password`), keyed by `rate_limit:<endpoint>:<client IP>` in Redis, capped at `MAX_ATTEMPTS` (4) per `WINDOW_SECONDS` (15 min) - `429` past that. Backed by Redis's atomic `INCR`/`EXPIRE` (not an in-memory counter) so the limit holds across multiple app processes; each counter key expires on its own after the window, so it resets without separate cleanup.

**Chat service only** (`apps/chat/app.py`, `apps/chat/Dockerfile`, `apps/chat/requirements.txt`):
- **`apps/chat/models.py`** — `QueryRequest`.
- **`apps/chat/chat_service.py`** — CRUD for `chat_sessions`/`chat_messages`. A session is created lazily on the first query in a thread (or reused via a client-supplied `session_id`) and scoped to the owning user; `MAX_HISTORY_TURNS` (5) caps how many prior turns are loaded, since tinyllama's context window is small.
- **`apps/chat/session_routes.py`** — `GET /chat/sessions`, `GET /chat/sessions/{id}/messages`, `DELETE /chat/sessions/{id}`.
- **`apps/chat/query_routes.py`** — `POST /query/user` and `POST /query/lawyer`, both behind `Depends(get_current_user)`. Both funnel through `_handle_query`, which differs only by the `role` string passed to prompt building. Loads history for `session_id` (if given) *before* retrieval — `apps/chat/history.py`'s `build_search_query` combines it with the current query so retrieval for follow-ups stays on-topic, not just the generation prompt — then retrieves, generates, and only creates/persists the session+turn after a context match is found (so a 204 "no context" turn doesn't leave an orphan session). Maps retrieval/generation failures to HTTP 404 (unknown `collection_name`), 204 (no context found), 500 (generation failure).
- **`apps/chat/retrieval.py`** — embeds a search string once with `DefaultEmbeddingFunction` (must match what `dataset/dataset.py` ingested with) and runs a single `$vectorSearch` aggregation against `case_law_documents`, optionally filtered by `dataset` when `collection_name` is given. The embedded text is `apps/chat/history.py`'s `build_search_query` output (current query + recent turns when `session_id` is given), not the bare query — a bare follow-up like "what remedy did they order?" shares almost no keywords with its topic and retrieves an unrelated chunk on its own. Only ever returns the single best-matching chunk — the LLM never sees more than one chunk of context, which is why prompts (`apps/chat/prompts.py`) explicitly forbid inventing facts beyond it.
- **`apps/chat/constants.py`** — `DATASETS`, the list of dataset codes (SCC, FCA, FC, TCC, CMAC, CHRT, SST, RPD, RAD, RLLR, ONCA). Each corresponds to a value of the `dataset` field in `case_law_documents` (previously a separate ChromaDB collection per dataset). Adding a new dataset means adding it here *and* to `dataset/dataset.py`'s `DATASETS` (kept as two separate lists, not shared, since retrieval and ingestion are independent entrypoints).
- **`apps/chat/history.py`** — turns the list of recent Mongo chat messages into the `Previous conversation` text block injected into the prompt (`build_history_context`), and into the combined text embedded for retrieval (`build_search_query`, current query first since the embedding model truncates long input from the end).
- **`apps/chat/llm.py`** — wraps the Ollama client, pointed at `OLLAMA_HOST`. Maps `role` ("user"/"lawyer") to a prompt-builder function in `apps/chat/prompts.py`, then calls `OLLAMA_MODEL`.
- **`apps/chat/response_utils.py`** — strips tinyllama's tendency to echo the question or prefix answers with labels like "Answer:" before returning to the client.
- **`apps/chat/prompts.py`** — `get_user_prompt` (plain-language, non-lawyer audience) and `get_lawyer_prompt` (precise legal terminology) share `_GROUNDING_RULES` so grounding behavior never drifts between roles — only tone/vocabulary should differ between the two prompt builders.

**Not part of either service:**
- **`dataset/dataset.py`** (+ its own `dataset/requirements.txt`) — standalone ingestion script (imports `libs.shared.db`). Its own requirements file covers `pymongo`/`chromadb` (for the embedding function, must match what `apps/chat/retrieval.py` embeds queries with) plus `pandas`/`requests`/`pyarrow`/`fastparquet` for the download/parquet work - not tied to either service's requirements file. Downloads each dataset's parquet from a HuggingFace dataset repo, embeds each chunk with the same `DefaultEmbeddingFunction` retrieval uses, and batch-inserts into `case_law_documents` with a deterministic `_id` (`"<dataset>_<original_id>"`) so re-running is idempotent. Concurrent downloads (`ThreadPoolExecutor`), sequential ingestion so it overlaps with in-flight downloads. Calls `ensure_vector_search_index()` once at the end.
- **`scripts/ai_review.py`** — standalone script used by `.github/workflows/pr_review.yml` to send a PR diff to Gemini (`GEMINI_API_KEY` secret) and post the response as a PR comment; has its own `scripts/requirements.txt` (`google-genai`), unrelated to either service's dependencies.
- **`db/`, `user_db/`** — leftover local ChromaDB storage from before the MongoDB migration; no longer read by anything. Not deleted automatically since it's local data, but safe to remove once you've confirmed the MongoDB-backed flow works.

## Additional collections not yet built

Flagged as likely-future needs, not implemented:
- `audit_log` — who queried what, when; likely relevant for compliance in a legal product.
- `api_keys` — for programmatic (non-browser-session) access, e.g. a future lawyer-tier integration.

## Docs

`README.md` and `curl_examples.sh` are kept in sync with the current MongoDB-backed API (auth, chat sessions, query endpoints) — no known drift as of this migration. `API.md` has the full per-endpoint request/response reference.
