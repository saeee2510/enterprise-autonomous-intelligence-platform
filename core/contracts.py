from dataclasses import dataclass
from typing import List, Optional, Dict, Any


# =========================
# 1. USER INPUT CONTRACT
# =========================

@dataclass
class QueryRequest:
    """
    Raw user query entering the system
    """
    question: str


# =========================
# 2. INTENT CLASSIFICATION
# =========================

@dataclass
class Intent:
    """
    Output of Intent Router
    Determines which subsystems to activate
    """
    sql_needed: bool
    retrieval_needed: bool
    priority: str  # low | medium | high


# =========================
# 3. PLANNING STRUCTURE
# =========================

@dataclass
class PlanStep:
    """
    Single step in execution plan
    """
    step_id: int
    action: str
    description: str


@dataclass
class ExecutionPlan:
    """
    Structured multi-step plan
    produced by Planner Agent
    """
    steps: List[PlanStep]


# =========================
# 4. SQL OUTPUT CONTRACT
# =========================

@dataclass
class SQLResult:
    """
    Output of SQL Agent execution
    """
    query: str
    results: List[Dict[str, Any]]
    source_table: str


# =========================
# 5. RETRIEVAL CONTRACT
# =========================

@dataclass
class RetrievedChunk:
    """
    Single document chunk from vector DB
    """
    chunk_id: str
    content: str
    score: float
    source: str


@dataclass
class RetrievalResult:
    """
    Output of Retrieval Agent
    """
    chunks: List[RetrievedChunk]


# =========================
# 6. EVIDENCE LAYER
# =========================

@dataclass
class Evidence:
    """
    Canonical evidence unit for verification + reporting
    """
    source: str
    content: str
    evidence_type: str  # sql | document


# =========================
# 7. FUSION OUTPUT
# =========================

@dataclass
class FusionResult:
    """
    Combined structured + unstructured intelligence
    """
    summary: str
    evidence: List[Evidence]


# =========================
# 8. FINAL REPORT
# =========================

@dataclass
class FinalReport:
    """
    Final output returned to user
    """
    executive_summary: str
    root_cause: str
    timeline: List[str]
    metrics: Dict[str, Any]
    evidence: List[Evidence]
    confidence_score: float