"""
LangGraph orchestration of the investigation pipeline.

                       ┌──── sql_agent ──────┐
    START → planner ───┤                     ├──→ fusion → verification ──→ report_generator → END
                       └── retrieval_agent ──┘       ▲            │
                                                     └─ revision ─┘  (at most once)

- planner decides which branches run. When both are needed, sql_agent and
  retrieval_agent run in parallel and fusion waits for both. Inside sql_agent,
  the independent SQL steps also run concurrently.
- Node names differ from state keys (plan, report, ...) because LangGraph
  does not allow a node and a state key to share a name.
- verification can send the draft back to fusion ONCE with the verifier's objections
  (rejected claims or contradictions with the SQL data). This bounded loop is
  the only cycle in the graph, so the run always terminates.
- Every node is wrapped by `logged`, which records latency, LLM tokens, and
  cost to execution_logs and to the in-memory step log returned to the caller.
"""
import operator
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Annotated, List, Optional, TypedDict

from langgraph.graph import END, START, StateGraph

from core import (execution_logger, fusion_agent, planner, report_generator,
                  retrieval_agent, sql_agent, verification_agent)

MAX_CHUNKS = 8
MAX_REVISIONS = 1
MAX_PARALLEL_SQL = 4


class InvestigationState(TypedDict, total=False):
    trace_id: str
    question: str
    plan: dict
    sql_results: list
    chunks: list
    fused: dict
    verified: dict
    report: dict
    revisions: int
    feedback: Optional[List[str]]
    step_log: Annotated[list, operator.add]  # parallel nodes append safely


# ----------------------------------------------------------------------
# LOGGING WRAPPER
# ----------------------------------------------------------------------
def logged(step_name, summarize_input, summarize_output):
    def decorator(fn):
        def node(state: InvestigationState):
            start = time.perf_counter()
            success, update, error = True, {}, None
            try:
                update = fn(state)
            except Exception as e:
                success, error = False, str(e)
                raise
            finally:
                latency = round((time.perf_counter() - start) * 1000, 1)
                usage = execution_logger.summarize_usage(update.pop("_usage", []) if update else [])
                output = summarize_output(update) if success else {"error": error}
                execution_logger.log_step(
                    state["trace_id"], state["question"], step_name,
                    summarize_input(state), output, latency,
                    usage["tokens"], usage["cost_usd"], success)
            update["step_log"] = [{"step": step_name, "latency_ms": latency, **usage,
                                   "success": success}]
            return update
        return node
    return decorator


def _usage_of(*parts):
    usages = []
    for p in parts:
        usages.extend(p.get("llm_usage", []) if isinstance(p, dict) else [])
    return usages


# ----------------------------------------------------------------------
# NODES
# ----------------------------------------------------------------------
@logged("planner",
        lambda s: {"question": s["question"]},
        lambda u: {"intent": u["plan"]["intent"], "steps": u["plan"]["steps"]})
def plan_node(state):
    plan = planner.plan(state["question"])
    return {"plan": plan, "_usage": _usage_of(plan)}


@logged("sql_agent",
        lambda s: {"actions": [st["action"] for st in s["plan"]["steps"] if st["tool"] == "sql"]},
        lambda u: [{"evidence_id": r["evidence_id"], "sql": r["sql"], "row_count": r["row_count"],
                    "attempts": r["attempts"], "error": r["error"]} for r in u["sql_results"]])
def sql_node(state):
    # independent SQL steps run concurrently; evidence ids keep plan order
    actions = [step["action"] for step in state["plan"]["steps"] if step["tool"] == "sql"]
    with ThreadPoolExecutor(max_workers=MAX_PARALLEL_SQL) as pool:
        results = list(pool.map(
            lambda pair: sql_agent.run_sql(state["question"], pair[1], f"sql:{pair[0]}"),
            enumerate(actions, start=1)))
    return {"sql_results": results, "_usage": _usage_of(*results)}


@logged("retrieval_agent",
        lambda s: {"actions": [st["action"] for st in s["plan"]["steps"] if st["tool"] == "retrieval"]},
        lambda u: [{"evidence_id": c["evidence_id"], "source": c["source"],
                    "vector_score": c["vector_score"], "bm25_score": c["bm25_score"]}
                   for c in u["chunks"]])
def retrieve_node(state):
    chunks, seen, usages = [], set(), []
    for step in state["plan"]["steps"]:
        if step["tool"] != "retrieval" or len(chunks) >= MAX_CHUNKS:
            continue
        found = retrieval_agent.retrieve(f"{state['question']} {step['action']}")
        usages.extend(found.get("llm_usage", []))
        for c in found["chunks"]:
            if c["chunk_id"] not in seen and len(chunks) < MAX_CHUNKS:
                seen.add(c["chunk_id"])
                chunks.append({**c, "evidence_id": f"doc:{len(chunks) + 1}"})
    return {"chunks": chunks, "_usage": usages}


@logged("fusion",
        lambda s: {"sql_evidence": len(s.get("sql_results", [])), "documents": len(s.get("chunks", [])),
                   "revision": s.get("revisions", 0), "feedback": s.get("feedback")},
        lambda u: {"summary": u["fused"]["summary"], "claims": len(u["fused"]["claims"])})
def fuse_node(state):
    fused = fusion_agent.fuse(state["question"], state.get("sql_results", []),
                              state.get("chunks", []), feedback=state.get("feedback"))
    return {"fused": fused, "_usage": _usage_of(fused)}


@logged("verification",
        lambda s: {"claims": len(s["fused"]["claims"])},
        lambda u: {"counts": u["verified"]["counts"],
                   "summary_consistent": u["verified"]["summary_consistent"],
                   "confidence": u["verified"]["confidence"]})
def verify_node(state):
    verified = verification_agent.verify(state["fused"], state.get("sql_results", []),
                                         state.get("chunks", []))
    feedback = [f"Rejected claim: \"{c['statement']}\" ({c['reason']})"
                for c in verified["rejected_claims"]]
    feedback += [f"Summary problem ({i.get('type')}): {i.get('explanation', '')} "
                 f"Summary statement: \"{i.get('summary_statement', '')}\". SQL: {i.get('sql_values', '')}"
                 for i in verified["consistency_issues"]]
    return {"verified": verified, "feedback": feedback or None, "_usage": _usage_of(verified)}


@logged("revision",
        lambda s: {"feedback": s.get("feedback")},
        lambda u: {"revisions": u["revisions"]})
def revise_node(state):
    return {"revisions": state.get("revisions", 0) + 1}


@logged("refusal",
        lambda s: {"question": s["question"]},
        lambda u: {"refused": True})
def refusal_node(state):
    reason = state["plan"].get("refusal_reason", "Request refused.")
    fused = {"query": state["question"], "summary": f"I can't do that. {reason} "
             "I can answer questions about the data instead.",
             "root_cause": None, "claims": [], "timeline": [], "recommendations": [],
             "available_evidence": [], "llm_usage": []}
    verified = {"claims": [], "verified_claims": [], "rejected_claims": [],
                "counts": {"supported": 0, "needs_review": 0, "unsupported": 0},
                "unsupported_rate": 0.0, "timeline": [], "rejected_timeline": [],
                "summary_consistent": True, "consistency_issues": [], "consistency_notes": [],
                "confidence": 0.0, "llm_usage": []}
    report = report_generator.generate_report(state["question"], fused, verified, [], [])
    report["refused"] = True
    return {"fused": fused, "verified": verified, "report": report}


@logged("report_generator",
        lambda s: {"confidence": s["verified"]["confidence"]},
        lambda u: {"findings": len(u["report"]["findings"]),
                   "rejected": len(u["report"]["rejected_claims"])})
def report_node(state):
    report = report_generator.generate_report(
        state["question"], state["fused"], state["verified"],
        state.get("sql_results", []), state.get("chunks", []))
    report["revisions"] = state.get("revisions", 0)
    return {"report": report}


# ----------------------------------------------------------------------
# ROUTING
# ----------------------------------------------------------------------
def route_after_plan(state):
    if state["plan"].get("intent") == "refuse":
        return ["refusal"]
    tools = {s["tool"] for s in state["plan"]["steps"]}
    branches = [name for tool, name in (("sql", "sql_agent"), ("retrieval", "retrieval_agent"))
                if tool in tools]
    return branches or ["fusion"]


def route_after_verify(state):
    if state.get("feedback") and state.get("revisions", 0) < MAX_REVISIONS:
        return "revision"
    return "report_generator"


# ----------------------------------------------------------------------
# GRAPH
# ----------------------------------------------------------------------
def build_graph():
    g = StateGraph(InvestigationState)
    g.add_node("planner", plan_node)
    g.add_node("sql_agent", sql_node)
    g.add_node("retrieval_agent", retrieve_node)
    g.add_node("fusion", fuse_node)
    g.add_node("verification", verify_node)
    g.add_node("revision", revise_node)
    g.add_node("report_generator", report_node)
    g.add_node("refusal", refusal_node)

    g.add_edge(START, "planner")
    g.add_conditional_edges("planner", route_after_plan,
                            ["sql_agent", "retrieval_agent", "fusion", "refusal"])
    g.add_edge("sql_agent", "fusion")
    g.add_edge("retrieval_agent", "fusion")
    g.add_edge("fusion", "verification")
    g.add_conditional_edges("verification", route_after_verify, ["revision", "report_generator"])
    g.add_edge("revision", "fusion")
    g.add_edge("report_generator", END)
    g.add_edge("refusal", END)
    return g.compile()


GRAPH = None


def get_graph():
    global GRAPH
    if GRAPH is None:
        GRAPH = build_graph()
    return GRAPH
