# Nextwork RAG API

## Overview
This project is a Retrieval-Augmented Generation (RAG) API for Canadian legal case-law search and question answering. It uses FastAPI, ChromaDB, and Ollama (`tinyllama`) for semantic search and generative responses, with answers tailored to the reader (layperson vs. legal professional).

## Features
- Query across multiple legal datasets (`SCC, FCA, FC, TCC, CMAC, CHRT, SST, RPD, RAD, RLLR, ONCA`), or target a single collection
- Role-based prompt templates - plain-language answers for `/query/user`, precise legal analysis for `/query/lawyer` - both grounded to only use the retrieved context
- Optional conversation history so follow-up questions stay in context (last 5 turns)
- Extracts source URLs and PDF links from the retrieved context/metadata
- Returns appropriate HTTP responses (200, 204 no relevant context, 404 unknown collection, 500 model failure)
- Docker containerization support
- Automated AI code review posted on pull requests via GitHub Actions (`scripts/ai_review.py`, powered by Gemini)

## Project Structure
- `app.py`: FastAPI app entrypoint with CORS middleware
- `services/api.py`: `/query/user` and `/query/lawyer` endpoints
- `services/retrieval.py`: Queries ChromaDB collections and extracts URLs/PDF links from the best-matching chunk
- `services/history.py`: Builds the conversation-history block injected into prompts
- `services/llm.py`: Builds the role-specific prompt and calls the Ollama model
- `services/response_utils.py`: Cleans up raw model output before returning it
- `services/models.py`: Request/response Pydantic models
- `services/constants.py`: Dataset collection names
- `prompts/prompts.py`: Prompt templates for the `user` and `lawyer` roles
- `dataset/dataset.py`: Downloads the source datasets and populates the ChromaDB collections in `db/`
- `db/`: ChromaDB persistent storage for document collections (gitignored)
- `user_db/`: Reserved for user/session data (gitignored)
- `scripts/ai_review.py`: Gemini-powered script used by the CI PR-review workflow
- `.github/workflows/`: CI (`ci.yml`) and automated PR review (`pr_review.yml`)
- `Dockerfile`: Docker container configuration
- `curl_examples.sh`: Example API calls using curl

## Prerequisites
- Python 3.11+
- Ollama with the `tinyllama` model installed
- ChromaDB (installed via `requirements.txt`) with `db/` populated by `dataset/dataset.py`

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
4. Ensure Ollama is running with the tinyllama model:
   ```bash
   ollama serve
   ollama pull tinyllama
   ```
5. Populate the vector store (one-time, downloads case-law datasets into `db/`):
   ```bash
   python dataset/dataset.py
   ```

### Docker
1. Build the Docker image:
   ```bash
   docker build -t nextwork-rag-api .
   ```
2. Run the container:
   ```bash
   docker run -p 8000:8000 nextwork-rag-api
   ```

## Usage

### Start the API Server
```bash
uvicorn app:app --port 8000 --host 0.0.0.0
```

### API Endpoints
- `POST /query/user`: Query for plain-language, layperson-friendly answers
- `POST /query/lawyer`: Query for precise legal analysis aimed at legal professionals

### Request Format
```json
{
  "query": "What is the deadline for filing an appeal?",
  "collection_name": "SCC",
  "history": [
    {"q": "Previous question", "answer": "Previous answer"}
  ]
}
```
- `query` (required): the question to answer
- `collection_name` (optional): restrict the search to one dataset (e.g. `SCC`); omit to search across all datasets
- `history` (optional): prior turns in the conversation, used to keep follow-up questions in context

### Response Format
```json
{
  "answer": "The AI-generated answer based on retrieved legal documents",
  "urls": ["https://example.com/legal-reference-1"]
}
```

### Example Usage

Query with the user role:
```bash
curl -X POST "http://localhost:8000/query/user" \
  -H "Content-Type: application/json" \
  -d '{"query": "What is the deadline for filing an appeal?"}'
```

Query with the lawyer role, restricted to one collection:
```bash
curl -X POST "http://localhost:8000/query/lawyer" \
  -H "Content-Type: application/json" \
  -d '{"query": "What are the legal requirements for contract formation?", "collection_name": "SCC"}'
```

See `curl_examples.sh` for more examples.

## Development

### Adding New Datasets
1. Add the dataset name to `DATASETS` in `services/constants.py` (and `dataset/dataset.py` if it needs to be downloaded/ingested)
2. Ensure the corresponding `<name>_docs` collection exists in ChromaDB (run `dataset/dataset.py` to ingest it)

### Customizing Prompts
- Modify the prompt templates in `prompts/prompts.py`
- Add a new role by writing a new prompt-builder function and registering it in `_PROMPT_BUILDERS` in `services/llm.py`, then adding a matching route in `services/api.py`

### Extending Business Logic
- Add retrieval logic in `services/retrieval.py`
- Add new API endpoints in `services/api.py`

## License
MIT
