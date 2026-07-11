"""Chat service entrypoint: RAG query endpoints and chat session history.

Verifies JWTs issued by the auth service independently (shared MongoDB +
JWT_SECRET, no HTTP call between services) - see libs/shared/jwt_auth.py.
Revocation checks against Redis (also shared with the auth service, no HTTP
call for that either) - see libs/shared/redis_client.py.
"""
from libs.shared.logging_config import configure_logging

configure_logging()

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from apps.chat.query_routes import router as query_router
from apps.chat.session_routes import router as chat_router
from libs.shared.config import ALLOWED_ORIGINS
from libs.shared.db import ensure_chat_indexes, ensure_connection, ensure_vector_search_index
from libs.shared.redis_client import ensure_connection as ensure_redis_connection

app = FastAPI(title="Chat Service")

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],  # Allows all methods
    allow_headers=["*"],  # Allows all headers
)


@app.on_event("startup")
def on_startup() -> None:
    ensure_connection()
    ensure_chat_indexes()
    ensure_vector_search_index()
    ensure_redis_connection()


@app.get("/health")
def health() -> dict:
    # Liveness only (process is up and serving) - deliberately no DB/Redis
    # round trip here, so a transient blip on either doesn't get this
    # container killed by an orchestrator's liveness probe.
    return {"status": "ok"}


app.include_router(query_router)
app.include_router(chat_router)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
