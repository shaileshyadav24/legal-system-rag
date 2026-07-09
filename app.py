from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from services.api import router
from services.auth_routes import router as auth_router
from services.chat_routes import router as chat_router
from services.db import ensure_connection, ensure_indexes, ensure_vector_search_index

app = FastAPI()

# Add CORS middleware to handle OPTIONS requests
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allows all origins
    allow_credentials=True,
    allow_methods=["*"],  # Allows all methods
    allow_headers=["*"],  # Allows all headers
)


@app.on_event("startup")
def on_startup() -> None:
    ensure_connection()
    ensure_indexes()
    ensure_vector_search_index()


app.include_router(router)
app.include_router(auth_router)
app.include_router(chat_router)
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)