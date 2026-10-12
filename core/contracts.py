"""
Input/output contracts for every agent. Each agent is a function that takes
and returns these shapes, which is what makes the pipeline deterministic and
testable stage by stage.
"""
from typing import List, Optional, TypedDict


class PlanStep(TypedDict):
    step: int
    tool: str     # "sql" | "retrieval"
    action: str   # plain-English description, never SQL


class Plan(TypedDict):
    query: str
    intent: str   # "sql" | "retrieval" | "hybrid"
    steps: List[PlanStep]


class SQLEvidence(TypedDict):
    evidence_id: str          # "sql:1"
    action: str
    sql: Optional[str]
    columns: List[str]
    rows: List[list]
    row_count: int
    truncated: bool
    error: Optional[str]
    attempts: int


class DocumentEvidence(TypedDict):
    evidence_id: str          # "doc:1"
    chunk_id: str
    content: str
    source: str
    department: str
    entity: str
    vector_score: float
    bm25_score: float
    rrf_score: float


class Claim(TypedDict):
    id: str
    type: str                 # "fact" | "inference"
    statement: str
    evidence_ids: List[str]


class CheckedClaim(Claim):
    status: str               # "supported" | "needs_review" | "unsupported"
    reason: str
    valid_evidence_ids: List[str]
    invalid_evidence_ids: List[str]
    ungrounded_numbers: List[str]
