"""Auth service entrypoint: registration, login, logout, password management."""
from libs.shared.logging_config import configure_logging

configure_logging()

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from apps.auth.routes import router as auth_router
from libs.shared.config import ALLOWED_ORIGINS
from libs.shared.db import ensure_auth_indexes, ensure_connection
from libs.shared.redis_client import ensure_connection as ensure_redis_connection

app = FastAPI(title="Auth Service")

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
    ensure_auth_indexes()
    ensure_redis_connection()


@app.get("/health")
def health() -> dict:
    # Liveness only (process is up and serving) - deliberately no DB/Redis
    # round trip here, so a transient blip on either doesn't get this
    # container killed by an orchestrator's liveness probe.
    return {"status": "ok"}


app.include_router(auth_router)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)
