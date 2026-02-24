# legal-system-rag

## Overview
This project is a Retrieval-Augmented Generation (RAG) API for legal document search and question answering. It uses FastAPI, ChromaDB, and Ollama for semantic search and generative responses.

## Features
- Query across multiple legal datasets
- Extract and clean URLs from context
- Modular service and API structure
- Role-based prompt templates (user, lawyer)
- Supports conversation history for context
- Returns appropriate HTTP responses (200, 204, 404, 500)

## Project Structure
- `app.py`: FastAPI app entrypoint, mounts API router
- `api.py`: API endpoints, role-based logic, imports prompt templates
- `service.py`: Business logic for querying collections and extracting URLs
- `prompts.py`: Prompt templates for user and lawyer roles
- `dataset.py`: Dataset management (if used)
- `db/`: ChromaDB persistent storage

## Usage
1. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
2. Start the API server:
   ```bash
   uvicorn app:app --port 8000 --host 0.0.0.0
   ```
3. Query the API:
   - POST `/query/user` for user-friendly answers
   - POST `/query/lawyer` for legal professional answers

## Example Request
```json
{
  "query": "What is the deadline for filing an appeal?",
  "collection_name": "SCC",
  "history": [
    {"q": "What is an appeal?", "answer": "An appeal is a request to review a court decision."}
  ]
}
```

## Response
```json
{
  "answer": "The deadline for filing an appeal is typically 30 days from the date of the decision. Please check the specific rules for your jurisdiction.",
  "urls": ["https://decisions.scc-csc.ca/scc-csc/scc-csc/en/item/14153/index.do"]
}
```

## Customization
- Add new roles or prompts in `prompts.py`
- Extend business logic in `service.py`
- Add new datasets in `dataset.py`

## License
MIT
