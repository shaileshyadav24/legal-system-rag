# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A FastAPI RAG (Retrieval-Augmented Generation) API for Canadian legal case law. It embeds a query, retrieves the closest-matching chunk from ChromaDB collections, and generates a grounded answer with a local Ollama model (`tinyllama`).

## Commands

Requires a `.env` (see `.env.example`) with `MONGODB_URI` pointing at a MongoDB Atlas cluster (Atlas Vector Search is Atlas-only - it doesn't work against a plain self-hosted `mongod`), plus `MONGODB_DB_NAME` and `JWT_SECRET`.

Run the API locally:
```bash
uvicorn app:app --port 8000 --host 0.0.0.0
```
Requires Ollama running with the model pulled:
```bash
ollama serve
ollama pull tinyllama
```

Install dependencies:
```bash
pip install -r requirements.txt
```

Ingest datasets into MongoDB (populates the `case_law_documents` collection and creates its Atlas Search vector index, run once before querying):
```bash
python dataset/dataset.py
```

Docker:
```bash
docker build -t nextwork-rag-api .
docker run -p 8000:8000 nextwork-rag-api
```

**Local testing without a real Atlas cluster**: `mongodb/mongodb-atlas-local` is a Docker image that bundles `mongot`, so `$vectorSearch` works against it — a plain `mongo:7` container cannot run `$vectorSearch` at all (`OperationFailure: $vectorSearch stage is only allowed on MongoDB Atlas`). Run it with `docker run -d -p 27017:27017 mongodb/mongodb-atlas-local`, and connect with `MONGODB_URI=mongodb://localhost:27017/?directConnection=true` (its replica set otherwise advertises an internal container hostname the host can't resolve).

There is no test suite (CI's `pytest` step is commented out in `.github/workflows/ci.yml`, and no test files exist).

## Architecture

Persistence is MongoDB (Atlas required — Atlas Vector Search is used for retrieval and doesn't work against a plain `mongod`; see "Local testing" below for a workaround). `services/db.py` owns the single `pymongo.MongoClient` and seven collections: `users`, `chat_sessions`, `chat_messages`, `case_law_documents`, `revoked_tokens`, `password_reset_tokens`, `rate_limit_attempts`.

Request flow for a query: `app.py` → `services/api.py` (auth-gated) → `services/chat_service.py` (load history for `session_id`, if any) → `services/retrieval.py` (Atlas `$vectorSearch`, embedding query + history combined) → `services/llm.py` → `services/response_utils.py` → `services/chat_service.py` (save the turn).

- **`app.py`** — FastAPI entrypoint, CORS middleware, mounts the query/auth/chat routers, and calls `services/db.py`'s `ensure_indexes()` on startup.
- **`services/config.py`** — env-driven settings (`MONGODB_URI`, `MONGODB_DB_NAME`, `JWT_SECRET`, `JWT_ALGORITHM`, `JWT_EXPIRE_MINUTES`), loaded via `python-dotenv`. See `.env.example`.
- **`services/db.py`** — the Mongo client/collections, `ensure_indexes()` (regular indexes: unique `users.email`, etc.), and `ensure_vector_search_index()` (creates the Atlas Search vector index `case_law_vector_index` on `case_law_documents.embedding`, 384 dims/cosine — idempotent, called from `dataset/dataset.py` and safe to re-run).
- **`services/auth.py`** — password hashing/verification (`bcrypt`), JWT issuing/decoding (`pyjwt`, each token carries a `jti`), and two dependencies: `get_token_payload` (Bearer token → decoded payload, 401 if invalid/expired/revoked via `revoked_tokens`) and `get_current_user` (built on top, looks up the `sub` in `users`). `revoke_token`/`is_token_revoked` back logout — a revoked `jti` is stored with a TTL equal to the token's own expiry, so entries self-clean once the token would've expired anyway.
- **`services/user_service.py`** — user CRUD/auth logic (`create_user`, `authenticate_user`, `update_password`, etc.) backing `services/auth_routes.py`'s `POST /auth/register`, `POST /auth/login`, `GET /auth/me`, `POST /auth/logout`.
- **`services/password_reset_service.py`** — forgot-password flow: `create_reset_token` (only stores a SHA-256 hash of the raw token, in `password_reset_tokens`, TTL 30 min) and `reset_password` (validates hash/expiry/unused, then calls `update_password`). Backs `POST /auth/forgot-password` / `POST /auth/reset-password`. No email delivery is wired up, so `forgot-password` currently echoes the raw token back in the response for dev/testing — swap that for actually emailing it before using this in production.
- **`services/rate_limit.py`** — fixed-window rate limiting for the unauthenticated auth endpoints (`register`, `login`, `forgot-password`, `reset-password`), keyed by `(client IP, endpoint)` in `rate_limit_attempts`, capped at `MAX_ATTEMPTS` (4) per `WINDOW_SECONDS` (15 min) - `429` past that. Backed by Mongo (not an in-memory counter) so the limit holds across multiple app processes; each attempt record TTL-expires on its own, so the window resets without separate cleanup. Applied via `dependencies=[Depends(rate_limit("login"))]` etc. in `services/auth_routes.py`.
- **`services/chat_service.py`** — CRUD for `chat_sessions`/`chat_messages`. A session is created lazily on the first query in a thread (or reused via a client-supplied `session_id`) and scoped to the owning user; `MAX_HISTORY_TURNS` (5) caps how many prior turns are loaded, since tinyllama's context window is small. Backs `services/chat_routes.py`'s `GET /chat/sessions`, `GET /chat/sessions/{id}/messages`, `DELETE /chat/sessions/{id}`.
- **`services/api.py`** — the two query endpoints, `POST /query/user` and `POST /query/lawyer`, both behind `Depends(get_current_user)`. Both funnel through `_handle_query`, which differs only by the `role` string passed to prompt building. Loads history for `session_id` (if given) *before* retrieval — `services/history.py`'s `build_search_query` combines it with the current query so retrieval for follow-ups stays on-topic, not just the generation prompt — then retrieves, generates, and only creates/persists the session+turn after a context match is found (so a 204 "no context" turn doesn't leave an orphan session). Maps retrieval/generation failures to HTTP 404 (unknown `collection_name`), 204 (no context found), 500 (generation failure).
- **`services/retrieval.py`** — embeds a search string once with `DefaultEmbeddingFunction` (must match what `dataset/dataset.py` ingested with) and runs a single `$vectorSearch` aggregation against `case_law_documents`, optionally filtered by `dataset` when `collection_name` is given. The embedded text is `services/history.py`'s `build_search_query` output (current query + recent turns when `session_id` is given), not the bare query — a bare follow-up like "what remedy did they order?" shares almost no keywords with its topic and retrieves an unrelated chunk on its own. Only ever returns the single best-matching chunk — the LLM never sees more than one chunk of context, which is why prompts (`prompts/prompts.py`) explicitly forbid inventing facts beyond it.
- **`services/constants.py`** — `DATASETS`, the list of dataset codes (SCC, FCA, FC, TCC, CMAC, CHRT, SST, RPD, RAD, RLLR, ONCA). Each corresponds to a value of the `dataset` field in `case_law_documents` (previously a separate ChromaDB collection per dataset). Adding a new dataset means adding it here *and* to `dataset/dataset.py`'s `DATASETS` (kept as two separate lists, not shared, since retrieval and ingestion are independent entrypoints).
- **`services/history.py`** — turns the list of recent Mongo chat messages into the `Previous conversation` text block injected into the prompt (`build_history_context`), and into the combined text embedded for retrieval (`build_search_query`, current query first since the embedding model truncates long input from the end).
- **`services/llm.py`** — wraps the Ollama client. Maps `role` ("user"/"lawyer") to a prompt-builder function in `prompts/prompts.py`, then calls `tinyllama`.
- **`services/response_utils.py`** — strips tinyllama's tendency to echo the question or prefix answers with labels like "Answer:" before returning to the client.
- **`prompts/prompts.py`** — `get_user_prompt` (plain-language, non-lawyer audience) and `get_lawyer_prompt` (precise legal terminology) share `_GROUNDING_RULES` so grounding behavior never drifts between roles — only tone/vocabulary should differ between the two prompt builders.
- **`dataset/dataset.py`** — standalone ingestion script (not imported by the API, but imports `services.db`). Downloads each dataset's parquet from a HuggingFace dataset repo, embeds each chunk with the same `DefaultEmbeddingFunction` retrieval uses, and batch-inserts into `case_law_documents` with a deterministic `_id` (`"<dataset>_<original_id>"`) so re-running is idempotent. Concurrent downloads (`ThreadPoolExecutor`), sequential ingestion so it overlaps with in-flight downloads. Calls `ensure_vector_search_index()` once at the end.
- **`scripts/ai_review.py`** — standalone script used by `.github/workflows/pr_review.yml` to send a PR diff to Gemini (`GEMINI_API_KEY` secret) and post the response as a PR comment. Not part of the running API.
- **`db/`, `user_db/`** — leftover local ChromaDB storage from before this migration; no longer read by the API. Not deleted automatically since it's local data, but safe to remove once you've confirmed the MongoDB-backed flow works.

## Additional collections not yet built

Flagged as likely-future needs, not implemented:
- `audit_log` — who queried what, when; likely relevant for compliance in a legal product.
- `api_keys` — for programmatic (non-browser-session) access, e.g. a future lawyer-tier integration.

## Docs

`README.md` and `curl_examples.sh` are kept in sync with the current MongoDB-backed API (auth, chat sessions, query endpoints) — no known drift as of this migration. `API.md` has the full per-endpoint request/response reference.
