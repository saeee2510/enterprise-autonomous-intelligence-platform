"""Runs the whole LangGraph pipeline with fake LLM and database calls (no API key needed)."""
from core import execution_logger, pipeline, planner, retrieval_agent, sql_agent

SQL_ROW = {"columns": ["change_pct"], "rows": [[-26.02]], "row_count": 1,
           "truncated": False, "error": None, "attempts": 1, "llm_usage": []}
CHUNK = {"chunk_id": "a", "source": "release_3_2.txt", "department": "release_notes",
         "entity": "product_release", "content": "v3.2 added automatic payment retry",
         "vector_score": 0.8, "bm25_score": 2.0, "rrf_score": 0.03}


def _fake_run_sql(question, action, evidence_id="sql:1"):
    return {"evidence_id": evidence_id, "action": action, "sql": "SELECT ...", **SQL_ROW}


def _fake_retrieve(query, top_k=None, start_index=1):
    return {"chunks": [{"evidence_id": "doc:1", **CHUNK}], "llm_usage": []}


def _run(fusion_drafts, judge_responses):
    """fusion_drafts / judge_responses are consumed in order, one per call."""
    originals = (planner.llm.chat_json, sql_agent.run_sql, retrieval_agent.retrieve,
                 execution_logger.ENABLED)
    fusion_drafts, judge_responses = list(fusion_drafts), list(judge_responses)
    usage = {"prompt_tokens": 100, "completion_tokens": 50, "cost_usd": 0.0001}

    def fake_chat_json(messages, temperature=0.0):
        prompt = messages[0]["content"] + messages[-1]["content"]
        if "fact checker" in prompt:
            return judge_responses.pop(0), usage
        if "planning engine" in messages[1]["content"]:
            return {"intent": "hybrid", "steps": [
                {"tool": "sql", "action": "EU net revenue before vs after 2025-04-15"},
                {"tool": "retrieval", "action": "release v3.2 checkout issues"}]}, usage
        return fusion_drafts.pop(0), usage

    try:
        planner.llm.chat_json = fake_chat_json  # planner, fusion, and judge share core.llm
        sql_agent.run_sql = _fake_run_sql
        retrieval_agent.retrieve = _fake_retrieve
        execution_logger.ENABLED = False
        return pipeline.run_investigation("Why did revenue drop in Europe?")
    finally:
        (planner.llm.chat_json, sql_agent.run_sql, retrieval_agent.retrieve,
         execution_logger.ENABLED) = originals


GOOD_DRAFT = {"summary": "EU revenue fell 26% after release v3.2.", "root_cause": "Payment retry bug",
              "claims": [
                  {"id": "c1", "type": "fact", "statement": "EU net revenue fell 26%", "evidence_ids": ["sql:1"]},
                  {"id": "c2", "type": "inference", "statement": "The v3.2 retry change caused the drop",
                   "evidence_ids": ["sql:1", "doc:1"]}],
              "timeline": [], "recommendations": ["Add idempotency keys"]}
OK_JUDGE = {"claims": [{"id": "c2", "verdict": "supported", "reason": "retry change documented"}], "issues": []}


def test_graph_runs_end_to_end_without_revision():
    result = _run([GOOD_DRAFT], [OK_JUDGE])
    statuses = {c["id"]: c["status"] for c in result["verified"]["claims"]}
    assert statuses == {"c1": "supported", "c2": "supported"}
    assert result["metrics"]["revisions"] == 0
    steps = [s["step"] for s in result["metrics"]["steps"]]
    assert steps[0] == "planner"
    assert set(steps[1:3]) == {"sql_agent", "retrieval_agent"}  # parallel branches
    assert steps[3:] == ["fusion", "verification", "report_generator"]
    assert result["metrics"]["llm_calls"] == 3 and result["metrics"]["tokens"] == 450
    assert result["trace_id"]


def test_rejected_claim_triggers_one_revision():
    bad_draft = {**GOOD_DRAFT, "claims": GOOD_DRAFT["claims"] + [
        {"id": "c3", "type": "fact", "statement": "EU revenue fell 90%", "evidence_ids": ["sql:1"]}]}
    result = _run([bad_draft, GOOD_DRAFT], [OK_JUDGE, OK_JUDGE])
    assert result["metrics"]["revisions"] == 1
    assert [s["step"] for s in result["metrics"]["steps"]][-5:] == \
        ["verification", "revision", "fusion", "verification", "report_generator"]
    assert result["verified"]["counts"]["unsupported"] == 0  # the revised draft is what's reported


def test_revision_happens_at_most_once():
    bad = {**GOOD_DRAFT, "claims": [
        {"id": "c1", "type": "fact", "statement": "EU revenue fell 90%", "evidence_ids": ["sql:1"]}]}
    result = _run([bad, bad], [OK_JUDGE, OK_JUDGE])
    assert result["metrics"]["revisions"] == 1
    assert result["report"]["rejected_claims"]  # still reported honestly, not hidden


def test_write_request_takes_the_refusal_path():
    original = execution_logger.ENABLED
    execution_logger.ENABLED = False
    try:
        result = pipeline.run_investigation("Delete all refunds created before April 2025.")
    finally:
        execution_logger.ENABLED = original
    assert result["report"]["refused"] is True
    assert result["sql"] == [] and result["documents"] == []
    assert [s["step"] for s in result["metrics"]["steps"]] == ["planner", "refusal"]
    assert "read-only" in result["answer"]
