# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A FastAPI RAG (Retrieval-Augmented Generation) API for Canadian legal case law. It embeds a query, retrieves the closest-matching chunk from ChromaDB collections, and generates a grounded answer with a local Ollama model (`tinyllama`).

## Commands

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

Ingest datasets into ChromaDB (populates `./db`, run once before querying):
```bash
python dataset/dataset.py
```

Docker:
```bash
docker build -t nextwork-rag-api .
docker run -p 8000:8000 nextwork-rag-api
```

There is no test suite (CI's `pytest` step is commented out in `.github/workflows/ci.yml`, and no test files exist).

## Architecture

Request flow: `app.py` → `services/api.py` → `services/retrieval.py` → `services/history.py` → `services/llm.py` → `services/response_utils.py`.

- **`app.py`** — FastAPI entrypoint, CORS middleware, mounts `services/api.py`'s router.
- **`services/api.py`** — the two endpoints, `POST /query/user` and `POST /query/lawyer`. Both funnel through `_handle_query`, which differs only by the `role` string passed down to prompt building. Maps retrieval/generation failures to HTTP 404 (no matching collection), 204 (no context found), 500 (generation failure).
- **`services/retrieval.py`** — owns the single `chromadb.PersistentClient(path="./db")`. Embeds the query once with `DefaultEmbeddingFunction` (must match the embedding function datasets were ingested with) and either queries one named collection or fans out across all `DATASETS` collections in parallel via `ThreadPoolExecutor`, keeping only the closest match by distance. Only ever returns the single best-matching chunk — the LLM never sees more than one chunk of context, which is why prompts (`prompts/prompts.py`) explicitly forbid inventing facts beyond it.
- **`services/constants.py`** — `DATASETS`, the list of dataset codes (SCC, FCA, FC, TCC, CMAC, CHRT, SST, RPD, RAD, RLLR, ONCA). Each corresponds to a `<NAME>_docs` ChromaDB collection. Adding a new dataset means adding it here *and* to `dataset/dataset.py`'s `DATASETS` (kept as two separate lists, not shared, since retrieval and ingestion are independent entrypoints).
- **`services/history.py`** — turns a client-supplied `history` list into a text block injected into the prompt. Caps to the last `MAX_HISTORY_TURNS` (5) turns since tinyllama's context window is small; the API itself is stateless and holds no session state server-side — the client must resend history each request.
- **`services/llm.py`** — wraps the Ollama client. Maps `role` ("user"/"lawyer") to a prompt-builder function in `prompts/prompts.py`, then calls `tinyllama`.
- **`services/response_utils.py`** — strips tinyllama's tendency to echo the question or prefix answers with labels like "Answer:" before returning to the client.
- **`prompts/prompts.py`** — `get_user_prompt` (plain-language, non-lawyer audience) and `get_lawyer_prompt` (precise legal terminology) share `_GROUNDING_RULES` so grounding behavior never drifts between roles — only tone/vocabulary should differ between the two prompt builders.
- **`dataset/dataset.py`** — standalone ingestion script (not imported by the API). Downloads each dataset's parquet from a HuggingFace dataset repo, then batch-ingests into `<name>_docs` ChromaDB collections at `./db`. Concurrent downloads (`ThreadPoolExecutor`), sequential ingestion so it overlaps with in-flight downloads.
- **`scripts/ai_review.py`** — standalone script used by `.github/workflows/pr_review.yml` to send a PR diff to Gemini (`GEMINI_API_KEY` secret) and post the response as a PR comment. Not part of the running API.
- **`db/`** — ChromaDB's persistent storage for the legal document collections; `user_db/` is present but currently empty (no session-persistence feature is wired up despite the folder existing).

## Known drift

- **`README.md` is stale**: it documents a `services/chat_api.py`, `services/service.py`, and chat session endpoints (`GET /chat/start`, `DELETE /chat/{session_id}`) that do not exist in the current code. The actual service layer is `services/api.py` + the modules above; there are no session-management endpoints today. Don't trust the README's endpoint/file list — verify against `services/` directly.
- **`curl_examples.sh` is stale**: it calls `POST /query` with a `"q"` field. The real endpoints are `POST /query/user` / `POST /query/lawyer` with a `QueryRequest` body (`query`, optional `collection_name`, optional `history`) as defined in `services/models.py`.
