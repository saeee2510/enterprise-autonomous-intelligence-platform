from fastapi import FastAPI
from core.planner import route_query
from core.fusion_agent import fuse_results
from core.verification_agent import verify
from core.report_generator import generate_report
from ingestion.search import run_sql, retrieve_candidates, build_context

import json

app = FastAPI()


@app.post("/query")
def query_endpoint(payload: dict):

    query = payload["query"]

    # 1. PLAN
    plan = route_query(query)

    sql_result = None
    docs_text = ""

    steps = plan.get("steps", [])
    if not steps:
        steps = [{"tool": "hybrid"}]

    # 2. EXECUTION
    for step in steps:
        tool = step.get("tool")

        if tool == "sql":
            sql_result = run_sql(query)

        elif tool == "retrieval":
            docs, _ = retrieve_candidates(query)
            docs_text = build_context(docs)

        elif tool == "hybrid":
            sql_result = run_sql(query)
            docs, _ = retrieve_candidates(query)
            docs_text = build_context(docs)

    # 3. FUSION
    fused = fuse_results(query, sql_result, docs_text)

    # 4. VERIFICATION
    verified = verify(fused, sql_result, docs_text)

    # 5. REPORT
    report = generate_report(query, fused, verified)

    # 6. ANSWER (if you still use LLM answer layer)
    answer = report.get("executive_summary") if isinstance(report, dict) else str(report)

    # ✅ THIS is EXACTLY where your return block goes
    return {
        "answer": answer,
        "report": report,
        "verified": verified,
        "fused": fused,
        "sql": sql_result,
        "docs": docs_text,
        "trace": plan
    }