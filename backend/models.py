from pydantic import BaseModel
from typing import Optional, Dict, Any


class QueryRequest(BaseModel):
    query: str


class QueryResponse(BaseModel):
    query: str
    plan: Optional[Dict[str, Any]] = None
    fused: Optional[Dict[str, Any]] = None
    verified: Optional[Dict[str, Any]] = None
    report: Optional[Dict[str, Any]] = None
    answer: Optional[str] = None