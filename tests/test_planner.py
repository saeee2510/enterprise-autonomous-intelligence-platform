from core.planner import validate_plan


def test_keeps_valid_steps_and_derives_intent():
    raw = {"intent": "sql", "steps": [
        {"tool": "SQL", "action": "EU revenue by week"},
        {"tool": "retrieval", "action": "release notes"},
        {"tool": "web", "action": "ignored"},
    ]}
    plan = validate_plan("Why did EU revenue drop?", raw)
    assert [s["tool"] for s in plan["steps"]] == ["sql", "retrieval"]
    assert plan["intent"] == "hybrid"


def test_rejects_plan_without_valid_steps():
    try:
        validate_plan("q", {"steps": [{"tool": "web", "action": "x"}]})
    except ValueError:
        return
    raise AssertionError("expected ValueError")


def test_write_requests_are_refused_without_an_llm_call():
    from core import planner
    original = planner.llm.chat_json
    planner.llm.chat_json = lambda *a, **k: (_ for _ in ()).throw(AssertionError("LLM called"))
    try:
        for q in ["Delete all refunds created before April 2025.", "please update the orders table",
                  "Drop the customers table"]:
            p = planner.plan(q)
            assert p["intent"] == "refuse" and p["steps"] == []
    finally:
        planner.llm.chat_json = original


def test_questions_about_deletions_are_not_refused():
    from core.planner import WRITE_REQUEST
    assert not WRITE_REQUEST.search("How many refunds were deleted or reversed?")
