"""Request/response models for the query endpoints."""
from typing import List, Optional

from pydantic import BaseModel


class HistoryTurn(BaseModel):
    """One prior question/answer pair from the same chat session."""
    q: str
    answer: str


class QueryRequest(BaseModel):
    query: str
    collection_name: Optional[str] = None
    history: Optional[List[HistoryTurn]] = None
