# Legal RAG API

## Overview
This project is a Retrieval-Augmented Generation (RAG) API for Canadian legal case-law search and question answering. It uses FastAPI, MongoDB Atlas Vector Search, and Ollama (`tinyllama`) for semantic search and generative responses, with answers tailored to the reader (layperson vs. legal professional).

It's split into **two independently deployable services** that share one MongoDB database and one Redis instance:
- **Auth service** (`apps/auth/app.py`, port 8001) — registration, login, logout, forgot/reset password.
- **Chat service** (`apps/chat/app.py`, port 8000) — the RAG query endpoints and chat session history.

A JWT issued by the auth service works directly against the chat service — the chat service verifies it independently (shared secret + database), no service-to-service call needed for every request.

Full request/response reference for every endpoint (including exact schemas and error codes) lives in **[`API.md`](API.md)** — this README covers setup and the high-level flow.

## Features
- Query across multiple legal datasets (`SCC, FCA, FC, TCC, CMAC, CHRT, SST, RPD, RAD, RLLR, ONCA`), or target a single one
- Role-based prompt templates - plain-language answers for `/query/user`, precise legal analysis for `/query/lawyer` - both grounded to only use the retrieved context
- Email/password auth with JWT access tokens, including logout (server-side token revocation via Redis) and forgot/reset password
- Server-side chat history: conversations are persisted per user/session in MongoDB (not resent by the client) and capped to the last 5 turns per prompt
- Extracts source URLs and PDF links from the retrieved context/metadata
- Returns appropriate HTTP responses (200, 204 no relevant context, 401 auth failure, 404 unknown collection, 409 duplicate email, 500 model failure)
- Docker containerization support
- Automated AI code review posted on pull requests via GitHub Actions (`scripts/ai_review.py`, powered by Gemini)

## Project Structure

**Entrypoints:**
- `apps/auth/app.py`: auth service FastAPI app (port 8001), CORS middleware, mounts `apps/auth/routes.py`'s router, validates the MongoDB and Redis connections and creates auth-owned Mongo indexes on startup
- `apps/chat/app.py`: chat service FastAPI app (port 8000), CORS middleware, mounts `apps/chat/query_routes.py` + `apps/chat/session_routes.py`'s routers, validates the MongoDB and Redis connections, creates chat-owned Mongo indexes, and builds the Atlas Search vector index on startup

**Shared** (imported by both services):
- `libs/shared/config.py`: required environment variables (fails fast if any are missing)
- `libs/shared/db.py`: the MongoDB client/collections, split index setup (`ensure_auth_indexes`/`ensure_chat_indexes`), and connection validation
- `libs/shared/redis_client.py`: the Redis client and connection validation, used for revoked-token lookups and auth rate limiting
- `libs/shared/jwt_auth.py`: JWT issuing/decoding and the auth dependencies (including revoked-token checks against Redis) — the chat service only ever verifies tokens with this, never issues them

**Auth service only** (`apps/auth/requirements.txt`, `apps/auth/Dockerfile`):
- `apps/auth/password_auth.py`: password hashing/verification
- `apps/auth/models.py`: request/response Pydantic models for auth endpoints
- `apps/auth/routes.py`: `/auth/register`, `/auth/login`, `/auth/me`, `/auth/logout`, `/auth/forgot-password`, `/auth/reset-password`
- `apps/auth/user_service.py`: user CRUD/authentication logic backing the auth routes
- `apps/auth/password_reset_service.py`: forgot/reset-password token generation and redemption
- `apps/auth/email_service.py`: sends the password-reset email via Resend
- `apps/auth/rate_limit.py`: Redis-backed rate limiting for the unauthenticated auth endpoints

**Chat service only** (`apps/chat/requirements.txt`, `apps/chat/Dockerfile`):
- `apps/chat/models.py`: request/response Pydantic models for query/chat endpoints
- `apps/chat/query_routes.py`: `/query/user` and `/query/lawyer` endpoints (auth-gated)
- `apps/chat/chat_service.py` / `apps/chat/session_routes.py`: chat session + message persistence and the `/chat/sessions` endpoints
- `apps/chat/retrieval.py`: runs a MongoDB Atlas `$vectorSearch` query and extracts URLs/PDF links from the best-matching chunk
- `apps/chat/history.py`: builds the conversation-history block injected into prompts, and the combined text embedded for retrieval, from persisted chat messages
- `apps/chat/llm.py`: builds the role-specific prompt and calls the Ollama model
- `apps/chat/response_utils.py`: cleans up raw model output before returning it
- `apps/chat/constants.py`: dataset codes used to validate `collection_name` and tag ingested documents
- `apps/chat/prompts.py`: prompt templates for the `user` and `lawyer` roles

**Not part of either service:**
- `dataset/dataset.py` (+ its own `dataset/requirements.txt`): downloads the source datasets, embeds each chunk, and ingests them into the `case_law_documents` MongoDB collection (replacing that dataset's existing documents only once its download succeeds) — its embedding function/model must match `apps/chat/retrieval.py`'s
- `db/`, `user_db/`: leftover local ChromaDB storage from before the MongoDB migration; no longer read by anything (gitignored)
- `scripts/ai_review.py` (+ its own `scripts/requirements.txt`): Gemini-powered script used by the CI PR-review workflow
- `.github/workflows/`: CI (`ci.yml`) and automated PR review (`pr_review.yml`)
- `API.md`: full API reference for every endpoint
- `.env.example`: required environment variables (shared by both services)

## Prerequisites
- Python 3.11+
- Ollama with the `tinyllama` model installed
- A MongoDB **Atlas** cluster with Atlas Search enabled — `$vectorSearch` doesn't work against a plain self-hosted `mongod`. For local development/testing without a real Atlas cluster, the `mongodb/mongodb-atlas-local` Docker image supports `$vectorSearch` too (see `CLAUDE.md` for the exact command).
- A reachable Redis instance — plain upstream Redis is fine, no managed-only feature is used.

## Getting Started

This walks through everything from scratch: standing up a MongoDB cluster, standing up Redis, ingesting the dataset, and running the API.

### 1. Get a MongoDB cluster with Atlas Search

`$vectorSearch` (used by `apps/chat/retrieval.py`) only works against MongoDB **Atlas** — a plain self-hosted `mongod` can't run it, so this step isn't optional. Pick one:

**Option A — real Atlas cluster (use this if you want the data to persist / for anything beyond local testing):**
1. Sign up / log in at [MongoDB Atlas](https://www.mongodb.com/cloud/atlas/register) and create a Project.
2. **Build a Database** → choose a tier (the free **M0** tier is enough to develop against) → pick a cloud provider/region → create the cluster (provisioning takes a few minutes).
3. **Database Access** → *Add New Database User* → set a username/password. These become `<user>`/`<password>` in the connection string.
4. **Network Access** → *Add IP Address* → add your current IP (or `0.0.0.0/0` to allow access from anywhere, only while developing).
5. Once the cluster is up, click **Connect** → **Drivers**, and copy the connection string. It looks like:
   ```
   mongodb+srv://<user>:<password>@<cluster>.mongodb.net/?retryWrites=true&w=majority
   ```
   You don't need to create the vector search index yourself — `ensure_vector_search_index()` (`libs/shared/db.py`) creates it programmatically the first time `dataset/dataset.py` or the app runs.

**Option B — local Docker container (fast, disposable, good for a quick trial run):**
```bash
docker run -d -p 27017:27017 mongodb/mongodb-atlas-local
```
This image bundles `mongot`, so `$vectorSearch` works against it too, unlike a plain `mongo` image. Its connection string is:
```
mongodb://localhost:27017/?directConnection=true
```
(`directConnection=true` is required — otherwise the driver tries to resolve the replica set's internal container hostname, which your host can't do.)

### 2. Get a Redis instance
Used for revoked-token (logout) lookups and auth-endpoint rate limiting. Any reachable Redis works — fastest for local dev:
```bash
docker run -d -p 6379:6379 redis:7
```
Connection string: `redis://localhost:6379/0`.

### 3. Configure environment variables
Copy `.env.example` to `.env` and fill in:
- `MONGODB_URI` — the connection string from step 1
- `MONGODB_DB_NAME` — any database name, e.g. `legal_rag` (created automatically on first write)
- `JWT_SECRET` — any long random string (e.g. `python -c "import secrets; print(secrets.token_hex(32))"`)
- `JWT_EXPIRE_MINUTES` — how long access tokens stay valid, e.g. `1440` (24h)
- `REDIS_URL` — the connection string from step 2, e.g. `redis://localhost:6379/0`
- `ALLOWED_ORIGINS` — comma-separated list of browser origins allowed to call either service (CORS), e.g. `http://localhost:3000` for a local frontend dev server, or `https://app.example.com,https://staging.example.com` in production. No wildcard support — both services send `Access-Control-Allow-Credentials: true`, and browsers reject a wildcard origin on credentialed requests.
- `RESEND_API_KEY` — API key from [Resend](https://resend.com), used to send forgot-password emails
- `RESEND_FROM_EMAIL` — sender address; must be on a domain verified in Resend, or use their sandbox sender `onboarding@resend.dev` for local testing (only delivers to your own Resend account email)
- `PASSWORD_RESET_URL` — base URL of the FE's reset-password page; the emailed link appends `?token=...` to it
- `OLLAMA_HOST` — base URL of the Ollama server, e.g. `http://localhost:11434` for local dev (see step 5)
- `OLLAMA_MODEL` — name of the Ollama model to generate answers with, e.g. `tinyllama` (must be pulled on the `OLLAMA_HOST` server, see step 5)

All eleven are required — the app fails fast at startup if any are missing (`libs/shared/config.py`).

### 4. Install dependencies
Each service has its own requirements file (they don't share every dependency — only auth needs `bcrypt`/`resend`, only chat needs `ollama`/`chromadb`). To run both locally in one venv:
```bash
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
pip install -r apps/auth/requirements.txt -r apps/chat/requirements.txt
```

### 5. Start Ollama
```bash
ollama serve
ollama pull tinyllama
```

### 6. Ingest the dataset
```bash
python dataset/dataset.py
```
This downloads each case-law dataset, embeds every chunk, and writes it into MongoDB's `case_law_documents` collection, then builds the Atlas Search vector index. It checks the MongoDB connection first and fails immediately with a clear error if step 1/3 isn't set up correctly, rather than after downloading anything. This step downloads a non-trivial amount of data and can take a while — it only needs to be re-run when you want to refresh the dataset (re-running is safe: each dataset's old documents are only replaced once its download succeeds).

### 7. Run both services
```bash
uvicorn apps.auth.app:app --port 8001 --host 0.0.0.0
uvicorn apps.chat.app:app --port 8000 --host 0.0.0.0
```
(Separate terminals/processes.) On startup each re-validates the MongoDB and Redis connections and creates its own Mongo indexes; the chat service also builds the Atlas Search vector index.

### 8. Verify it works
```bash
curl -X POST "http://localhost:8001/auth/register" \
  -H "Content-Type: application/json" \
  -d '{"email": "jane@example.com", "password": "hunter2", "full_name": "Jane Doe"}'
```
Take the `access_token` from the response and use it against the **chat service** (port 8000) in the `Querying` example under [Usage](#usage) below. A `200` with an `answer` means the whole chain (auth service → shared MongoDB/Redis → chat service → Atlas Search → Ollama) is working end to end.

### Docker
Once `.env` is set up (steps 1–3 above), each service builds/runs as its own image:
```bash
docker build -f apps/auth/Dockerfile -t nextwork-auth-service .
docker build -f apps/chat/Dockerfile -t nextwork-chat-service .
docker run -p 127.0.0.1:8001:8001 --env-file .env nextwork-auth-service
docker run -p 127.0.0.1:8000:8000 --env-file .env nextwork-chat-service
```
Both images run as a non-root user and expose `GET /health` (liveness - process is up, no DB/Redis check) with a Docker `HEALTHCHECK` already wired to it. Each container runs uvicorn with multiple worker processes (`UVICORN_WORKERS`, defaults to 4 - set it in `.env` to tune to the container's CPU allocation, or leave at the default and scale horizontally with more container replicas instead). Ports are bound to `127.0.0.1` only - see "Exposing it publicly" below for why.

**Or run the whole stack with Compose** (Redis, Ollama, and both services - MongoDB still has to be a real Atlas cluster, see above):
```bash
docker compose up -d --build
```
This also pulls `OLLAMA_MODEL` into Ollama automatically (a one-shot `ollama-init` service) and wires `REDIS_URL`/`OLLAMA_HOST` to the containers' in-network hostnames for you - no `.env` edits needed beyond the usual `MONGODB_URI`/`JWT_SECRET`/etc. from steps 1–3. It also binds both services to `127.0.0.1` only, same as the plain `docker run` commands above.

**Exposing it publicly**: neither `docker run` above nor `docker-compose.yml` expose the services beyond `127.0.0.1`, on purpose - `deploy/nginx/legalrag.conf` is a ready-to-use Nginx reverse-proxy config (with Let's Encrypt setup instructions in its header comment) that terminates TLS and proxies `auth.yourdomain.com`/`api.yourdomain.com` to them from there.

## Usage

Assumes both services are already running and you have an `access_token` (see [Getting Started](#getting-started) above — steps 7–8 cover starting them and registering). Every call below needs `Authorization: Bearer <access_token>`. Subsequent logins use `POST /auth/login` (port 8001) with `{"email", "password"}`; `POST /auth/logout` revokes the current token server-side; `POST /auth/forgot-password` / `POST /auth/reset-password` cover password recovery. Full request/response shapes for all six auth endpoints are in `API.md`.

### Querying

```bash
curl -X POST "http://localhost:8000/query/user" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <access_token>" \
  -d '{"query": "What is the deadline for filing an appeal?"}'
```

Response:
```json
{
  "answer": "The AI-generated answer based on retrieved legal documents",
  "urls": ["https://example.com/legal-reference-1"],
  "session_id": "6a4ad75d123aeb6c54a06e41"
}
```

- `collection_name` (optional): restrict the search to one dataset (e.g. `SCC`); omit to search across all datasets.
- `session_id` (optional): pass back the `session_id` from a previous response to continue that conversation — the server loads recent turns itself, so the client no longer resends history. Omit on the first message of a new conversation.

`POST /query/lawyer` takes the same request/response shape, with more precise legal terminology in the answer.

Browse past conversations via `GET /chat/sessions`, `GET /chat/sessions/{id}/messages`, and delete one with `DELETE /chat/sessions/{id}` (all scoped to the authenticated user).

See `curl_examples.sh` for more examples and `API.md` for the complete reference.

## Development

### Adding New Datasets
1. Add the dataset code to `DATASETS` in `apps/chat/constants.py` (and `dataset/dataset.py`'s own `DATASETS` list)
2. Run `python dataset/dataset.py` to download, embed, and ingest it into the `case_law_documents` collection

### Customizing Prompts
- Modify the prompt templates in `apps/chat/prompts.py`
- Add a new role by writing a new prompt-builder function and registering it in `_PROMPT_BUILDERS` in `apps/chat/llm.py`, then adding a matching route in `apps/chat/query_routes.py`

### Extending Business Logic
- Add retrieval logic in `apps/chat/retrieval.py`
- Add new chat/query endpoints in `apps/chat/query_routes.py` or `apps/chat/session_routes.py` (chat service) — remember to add any new dependency to `apps/chat/requirements.txt` and `apps/chat/Dockerfile`'s file list
- Add new auth endpoints in `apps/auth/routes.py` (auth service) — same for `apps/auth/requirements.txt`/`apps/auth/Dockerfile`

## License
MIT
