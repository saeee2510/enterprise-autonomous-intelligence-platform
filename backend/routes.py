from fastapi import APIRouter
from backend.models import QueryRequest
from backend.services import process_query

router = APIRouter()


# -------------------------
# HEALTH CHECK
# -------------------------
@router.get("/health")
def health():
    return {
        "status": "healthy"
    }


# -------------------------
# MAIN QUERY ENDPOINT
# -------------------------
@router.post("/query")
def query(request: QueryRequest):

    result = process_query(request.query)

    return result


# -------------------------
# PLACEHOLDER STORAGE (PHASE 14 later)
# -------------------------
@router.get("/investigation/{id}")
def get_investigation(id: str):

    return {
        "id": id,
        "status": "not_implemented_yet"
    }


@router.get("/logs/{id}")
def get_logs(id: str):

    return {
        "id": id,
        "logs": []
    }