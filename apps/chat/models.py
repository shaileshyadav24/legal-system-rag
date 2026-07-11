"""Request/response models for the chat/query service."""
from typing import Optional

from pydantic import BaseModel


class QueryRequest(BaseModel):
    query: str
    collection_name: Optional[str] = None
    session_id: Optional[str] = None
