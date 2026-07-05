# Nextwork RAG API

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

## Installation

### Local Development
1. Clone the repository and navigate to the project directory
2. Create a virtual environment:
   ```bash
   python -m venv .venv
   source .venv/bin/activate  # On Windows: .venv\Scripts\activate
   ```
3. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
4. Copy `.env.example` to `.env` and fill in `MONGODB_URI`, `MONGODB_DB_NAME`, `JWT_SECRET`, and `JWT_EXPIRE_MINUTES` — the app won't start without all four set.
5. Ensure Ollama is running with the tinyllama model:
   ```bash
   ollama serve
   ollama pull tinyllama
   ```
6. Populate the vector store (one-time per dataset refresh; downloads case-law datasets and ingests them into MongoDB):
   ```bash
   python dataset/dataset.py
   ```

### Docker
1. Build the Docker image:
   ```bash
   docker build -t nextwork-rag-api .
   ```
2. Run the container (pass your `.env` through):
   ```bash
   docker run -p 8000:8000 --env-file .env nextwork-rag-api
   ```

## Usage

### Start the API Server
```bash
uvicorn app:app --port 8000 --host 0.0.0.0
```

### Auth flow

Register (or log in) to get a JWT, then send it as `Authorization: Bearer <token>` on every query/chat-history call.

```bash
curl -X POST "http://localhost:8000/auth/register" \
  -H "Content-Type: application/json" \
  -d '{"email": "jane@example.com", "password": "hunter2", "full_name": "Jane Doe"}'
```

This returns `{"access_token": "...", "token_type": "bearer", "user": {...}}`. Subsequent logins use `POST /auth/login` with `{"email", "password"}`. `POST /auth/logout` revokes the current token server-side; `POST /auth/forgot-password` / `POST /auth/reset-password` cover password recovery. Full request/response shapes for all six auth endpoints are in `API.md`.

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
