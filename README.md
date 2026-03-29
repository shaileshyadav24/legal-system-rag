# Nextwork RAG API

## Overview
This project is a Retrieval-Augmented Generation (RAG) API for legal document search and question answering. It uses FastAPI, ChromaDB, and Ollama for semantic search and generative responses.

## Features
- Query across multiple legal datasets (SCC, FCA, FC, TCC, CMAC, CHRT, SST, RPD, RAD, RLLR, ONCA)
- Extract and clean URLs from context
- Modular service and API structure
- Role-based prompt templates (user, lawyer)
- Session-based conversation history for context
- Chat session management (start, delete)
- Returns appropriate HTTP responses (200, 204, 404, 500)
- Docker containerization support

## Project Structure
- `app.py`: FastAPI app entrypoint with CORS middleware
- `services/api.py`: Query endpoints with role-based logic and prompt templates
- `services/chat_api.py`: Chat session management endpoints
- `services/service.py`: Business logic for querying collections and extracting URLs
- `prompts/prompts.py`: Prompt templates for user and lawyer roles
- `dataset/dataset.py`: Dataset management utilities
- `db/`: ChromaDB persistent storage for document collections
- `user_db/`: ChromaDB persistent storage for user chat sessions
- `scripts/ai_review.py`: AI review utilities
- `Dockerfile`: Docker container configuration
- `curl_examples.sh`: Example API calls using curl

## Prerequisites
- Python 3.11+
- Ollama with `tinyllama` model installed
- ChromaDB for vector storage

## Installation

### Local Development
1. Clone the repository and navigate to the project directory
2. Create a virtual environment:
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
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

#### Chat Session Management
- `GET /chat/start`: Start a new chat session and get a session ID
- `DELETE /chat/{session_id}`: Delete a chat session

#### Query Endpoints
- `POST /query/user`: Query for user-friendly answers
- `POST /query/lawyer`: Query for legal professional answers

### Example Usage

1. Start a chat session:
   ```bash
   curl -X GET "http://localhost:8000/chat/start"
   ```
   Response: `{"session_id": "uuid-here"}`

2. Query with user role:
   ```bash
   curl -X POST "http://localhost:8000/query/user" \
     -H "Content-Type: application/json" \
     -d '{"query": "What is the deadline for filing an appeal?", "session_id": "your-session-id"}'
   ```

3. Query with lawyer role:
   ```bash
   curl -X POST "http://localhost:8000/query/lawyer" \
     -H "Content-Type: application/json" \
     -d '{"query": "What are the legal requirements for contract formation?", "session_id": "your-session-id"}'
   ```

### Request Format
```json
{
  "query": "Your legal question here",
  "session_id": "uuid-of-chat-session"
}
```

### Response Format
```json
{
  "answer": "The AI-generated answer based on retrieved legal documents",
  "urls": ["https://example.com/legal-reference-1", "https://example.com/legal-reference-2"]
}
```

## Development

### Adding New Datasets
1. Add dataset name to the `datasets` list in `services/api.py`
2. Ensure the dataset collection exists in ChromaDB

### Customizing Prompts
- Modify prompt templates in `prompts/prompts.py`
- Add new roles by extending the `build_prompt` function

### Extending Business Logic
- Add new functionality in `services/service.py`
- Update API endpoints in `services/api.py` or `services/chat_api.py`

## License
MIT
