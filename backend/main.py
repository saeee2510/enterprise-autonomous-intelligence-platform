from fastapi import FastAPI, HTTPException

from backend.models import QueryRequest
from core import execution_logger
from core.pipeline import run_investigation

app = FastAPI(title="Enterprise Autonomous Intelligence Platform")


@app.get("/health")
def health():
    return {"status": "healthy"}


@app.post("/query")
def query_endpoint(request: QueryRequest):
    return run_investigation(request.query)


@app.get("/investigation/{trace_id}")
def get_investigation(trace_id: str):
    investigation = execution_logger.get_investigation(trace_id)
    if not investigation:
        raise HTTPException(status_code=404, detail="investigation not found")
    return investigation


@app.get("/logs/{trace_id}")
def get_logs(trace_id: str):
    return {"trace_id": trace_id, "steps": execution_logger.get_logs(trace_id)}
