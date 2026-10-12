"""
Entry point for running an investigation. The orchestration itself lives in
core/graph.py (LangGraph); this module creates the trace, runs the graph, saves
the investigation, and shapes the API response.
"""
from core import execution_logger
from core.graph import get_graph


def run_investigation(question: str) -> dict:
    trace_id = execution_logger.new_trace_id()
    final = get_graph().invoke({
        "trace_id": trace_id,
        "question": question,
        "revisions": 0,
        "step_log": [],
    })

    report = final["report"]
    execution_logger.save_investigation(trace_id, question, final["plan"], report)

    steps = final.get("step_log", [])
    metrics = {
        "total_latency_ms": round(sum(s["latency_ms"] for s in steps), 1),
        "llm_calls": sum(s["llm_calls"] for s in steps),
        "tokens": sum(s["tokens"] for s in steps),
        "cost_usd": round(sum(s["cost_usd"] for s in steps), 6),
        "revisions": final.get("revisions", 0),
        "steps": steps,
    }

    return {
        "trace_id": trace_id,
        "answer": report["executive_summary"],
        "report": report,
        "verified": final["verified"],
        "fused": final["fused"],
        "sql": final.get("sql_results", []),
        "documents": final.get("chunks", []),
        "trace": final["plan"],
        "metrics": metrics,
    }


if __name__ == "__main__":
    import json
    q = input("Ask EAIP: ")
    result = run_investigation(q)
    print(json.dumps({"report": result["report"], "metrics": result["metrics"]}, indent=2, default=str))
