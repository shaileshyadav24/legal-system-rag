# Legal RAG API

## Overview
This project is a Retrieval-Augmented Generation (RAG) API for Canadian legal case-law search and question answering. It uses FastAPI, MongoDB Atlas Vector Search, and Ollama (`tinyllama`) for semantic search and generative responses, with answers tailored to the reader (layperson vs. legal professional).

Full request/response reference for every endpoint (including exact schemas and error codes) lives in **[`API.md`](API.md)** — this README covers setup and the high-level flow.

## Features
- Query across multiple legal datasets (`SCC, FCA, FC, TCC, CMAC, CHRT, SST, RPD, RAD, RLLR, ONCA`), or target a single one
- Role-based prompt templates - plain-language answers for `/query/user`, precise legal analysis for `/query/lawyer` - both grounded to only use the retrieved context
- Email/password auth with JWT access tokens, including logout (server-side token revocation) and forgot/reset password
- Server-side chat history: conversations are persisted per user/session in MongoDB (not resent by the client) and capped to the last 5 turns per prompt
- Extracts source URLs and PDF links from the retrieved context/metadata
- Returns appropriate HTTP responses (200, 204 no relevant context, 401 auth failure, 404 unknown collection, 409 duplicate email, 500 model failure)
- Docker containerization support
- Automated AI code review posted on pull requests via GitHub Actions (`scripts/ai_review.py`, powered by Gemini)

## Project Structure
- `app.py`: FastAPI app entrypoint, CORS middleware, mounts the query/auth/chat routers, validates the MongoDB connection and creates indexes on startup
- `services/api.py`: `/query/user` and `/query/lawyer` endpoints (auth-gated)
- `services/auth.py`: password hashing, JWT issuing/decoding, and the auth dependencies (including revoked-token checks)
- `services/auth_routes.py`: `/auth/register`, `/auth/login`, `/auth/me`, `/auth/logout`, `/auth/forgot-password`, `/auth/reset-password`
- `services/user_service.py`: user CRUD/authentication logic backing the auth routes
- `services/password_reset_service.py`: forgot/reset-password token generation and redemption
- `services/chat_service.py` / `services/chat_routes.py`: chat session + message persistence and the `/chat/sessions` endpoints
- `services/retrieval.py`: runs a MongoDB Atlas `$vectorSearch` query and extracts URLs/PDF links from the best-matching chunk
- `services/history.py`: builds the conversation-history block injected into prompts, from persisted chat messages
- `services/llm.py`: builds the role-specific prompt and calls the Ollama model
- `services/response_utils.py`: cleans up raw model output before returning it
- `services/models.py`: request/response Pydantic models
- `services/constants.py`: dataset codes used to validate `collection_name` and tag ingested documents
- `services/config.py`: required environment variables (fails fast if any are missing)
- `services/db.py`: the MongoDB client/collections, index setup, and connection validation
- `prompts/prompts.py`: prompt templates for the `user` and `lawyer` roles
- `dataset/dataset.py`: downloads the source datasets, embeds each chunk, and ingests them into the `case_law_documents` MongoDB collection (replacing that dataset's existing documents only once its download succeeds)
- `db/`, `user_db/`: leftover local ChromaDB storage from before the MongoDB migration; no longer read by the API (gitignored)
- `scripts/ai_review.py`: Gemini-powered script used by the CI PR-review workflow
- `.github/workflows/`: CI (`ci.yml`) and automated PR review (`pr_review.yml`)
- `Dockerfile`: Docker container configuration
- `API.md`: full API reference for every endpoint
- `.env.example`: required environment variables

## Prerequisites
- Python 3.11+
- Ollama with the `tinyllama` model installed
- A MongoDB **Atlas** cluster with Atlas Search enabled — `$vectorSearch` doesn't work against a plain self-hosted `mongod`. For local development/testing without a real Atlas cluster, the `mongodb/mongodb-atlas-local` Docker image supports `$vectorSearch` too (see `CLAUDE.md` for the exact command).

## Getting Started

This walks through everything from scratch: standing up a MongoDB cluster, ingesting the dataset, and running the API.

### 1. Get a MongoDB cluster with Atlas Search

`$vectorSearch` (used by `services/retrieval.py`) only works against MongoDB **Atlas** — a plain self-hosted `mongod` can't run it, so this step isn't optional. Pick one:

**Option A — real Atlas cluster (use this if you want the data to persist / for anything beyond local testing):**
1. Sign up / log in at [MongoDB Atlas](https://www.mongodb.com/cloud/atlas/register) and create a Project.
2. **Build a Database** → choose a tier (the free **M0** tier is enough to develop against) → pick a cloud provider/region → create the cluster (provisioning takes a few minutes).
3. **Database Access** → *Add New Database User* → set a username/password. These become `<user>`/`<password>` in the connection string.
4. **Network Access** → *Add IP Address* → add your current IP (or `0.0.0.0/0` to allow access from anywhere, only while developing).
5. Once the cluster is up, click **Connect** → **Drivers**, and copy the connection string. It looks like:
   ```
   mongodb+srv://<user>:<password>@<cluster>.mongodb.net/?retryWrites=true&w=majority
   ```
   You don't need to create the vector search index yourself — `ensure_vector_search_index()` (`services/db.py`) creates it programmatically the first time `dataset/dataset.py` or the app runs.

**Option B — local Docker container (fast, disposable, good for a quick trial run):**
```bash
docker run -d -p 27017:27017 mongodb/mongodb-atlas-local
```
This image bundles `mongot`, so `$vectorSearch` works against it too, unlike a plain `mongo` image. Its connection string is:
```
mongodb://localhost:27017/?directConnection=true
```
(`directConnection=true` is required — otherwise the driver tries to resolve the replica set's internal container hostname, which your host can't do.)

### 2. Configure environment variables
Copy `.env.example` to `.env` and fill in:
- `MONGODB_URI` — the connection string from step 1
- `MONGODB_DB_NAME` — any database name, e.g. `legal_rag` (created automatically on first write)
- `JWT_SECRET` — any long random string (e.g. `python -c "import secrets; print(secrets.token_hex(32))"`)
- `JWT_EXPIRE_MINUTES` — how long access tokens stay valid, e.g. `1440` (24h)
- `RESEND_API_KEY` — API key from [Resend](https://resend.com), used to send forgot-password emails
- `RESEND_FROM_EMAIL` — sender address; must be on a domain verified in Resend, or use their sandbox sender `onboarding@resend.dev` for local testing (only delivers to your own Resend account email)
- `PASSWORD_RESET_URL` — base URL of the FE's reset-password page; the emailed link appends `?token=...` to it

All seven are required — the app fails fast at startup if any are missing (`services/config.py`).

### 3. Install dependencies
```bash
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### 4. Start Ollama
```bash
ollama serve
ollama pull tinyllama
```

### 5. Ingest the dataset
```bash
python dataset/dataset.py
```
This downloads each case-law dataset, embeds every chunk, and writes it into MongoDB's `case_law_documents` collection, then builds the Atlas Search vector index. It checks the MongoDB connection first and fails immediately with a clear error if step 1/2 isn't set up correctly, rather than after downloading anything. This step downloads a non-trivial amount of data and can take a while — it only needs to be re-run when you want to refresh the dataset (re-running is safe: each dataset's old documents are only replaced once its download succeeds).

### 6. Run the API
```bash
uvicorn app:app --port 8000 --host 0.0.0.0
```
On startup the app re-validates the MongoDB connection and creates its regular indexes (`services/db.py`'s `ensure_connection()` / `ensure_indexes()`).

### 7. Verify it works
```bash
curl -X POST "http://localhost:8000/auth/register" \
  -H "Content-Type: application/json" \
  -d '{"email": "jane@example.com", "password": "hunter2", "full_name": "Jane Doe"}'
```
Take the `access_token` from the response and use it in the `Querying` example under [Usage](#usage) below. A `200` with an `answer` means the whole chain (MongoDB → Atlas Search → Ollama) is working end to end.

### Docker
Once `.env` is set up (steps 1–2 above):
```bash
docker build -t nextwork-rag-api .
docker run -p 8000:8000 --env-file .env nextwork-rag-api
```

## Usage

Assumes the API is already running and you have an `access_token` (see [Getting Started](#getting-started) above — steps 6–7 cover starting the server and registering). Every call below needs `Authorization: Bearer <access_token>`. Subsequent logins use `POST /auth/login` with `{"email", "password"}`; `POST /auth/logout` revokes the current token server-side; `POST /auth/forgot-password` / `POST /auth/reset-password` cover password recovery. Full request/response shapes for all six auth endpoints are in `API.md`.

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
1. Add the dataset code to `DATASETS` in `services/constants.py` (and `dataset/dataset.py`'s own `DATASETS` list)
2. Run `python dataset/dataset.py` to download, embed, and ingest it into the `case_law_documents` collection

### Customizing Prompts
- Modify the prompt templates in `prompts/prompts.py`
- Add a new role by writing a new prompt-builder function and registering it in `_PROMPT_BUILDERS` in `services/llm.py`, then adding a matching route in `services/api.py`

### Extending Business Logic
- Add retrieval logic in `services/retrieval.py`
- Add new API endpoints in `services/api.py`, `services/auth_routes.py`, or `services/chat_routes.py`

## License
MIT
