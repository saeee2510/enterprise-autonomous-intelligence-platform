"""
Planner Agent: turns a business question into an explicit execution plan.

It never answers the question. It only decides which tools to run (sql,
retrieval) and what each step should fetch. The plan is validated, so a
malformed LLM output can never reach the executors.
"""
import json
import re

from core import llm

ALLOWED_TOOLS = {"sql", "retrieval"}
ALLOWED_INTENTS = {"sql", "retrieval", "hybrid"}
MAX_STEPS = 5

PLANNER_PROMPT = """You are the planning engine of an enterprise investigation system.
Your job is ONLY to produce an execution plan. Do not answer the question.

Tools:
- sql: structured metrics from the business database (revenue, orders, refunds,
  support tickets, customers by region, trends over time).
- retrieval: unstructured documents (release notes, incident reviews, support
  logs, customer emails, marketing summaries) that explain WHY something happened.

DATA COVERAGE: {coverage}

Rules:
- Use sql for "how many / how much / trend / compare" questions.
- Use retrieval for "explain / what happened / what is" questions.
- Use both (intent "hybrid") for "why" questions: metrics show WHAT changed,
  documents explain WHY.
- Each sql step's "action" must describe ONE specific metric to compute, in
  plain English (never write SQL). Use separate sql steps for separate metrics.
- Only restrict dates when the question names a period. For totals or counts
  with no period named, use all data and do not mention dates in the action.
- When the question does name a period, use absolute dates inside the data
  coverage. Never use relative periods like "last quarter" or "this month".
- Each retrieval step's "action" is a short search phrase.
- At most 5 steps.

Playbook for questions about a CHANGE in a metric (drop, rise, spike, decline,
recovery):
  1. sql: monthly totals of that metric by region, with the month-over-month
     change and percentage change computed in SQL.
  2. sql: weekly trend of that metric by region across the full data coverage,
     so the change point is visible.
  3. sql: weekly support tickets by category for the affected region.
  4. sql: weekly refund count and amount by reason for the affected region.
  5. retrieval: a short search phrase naming the affected metric and region
     (e.g. "Europe checkout payment problems"). Avoid generic words like
     "incidents" or "campaigns" that match unrelated documents.
If no region is named, use all regions in steps 3 and 4.

Return JSON only:
{
  "intent": "sql | retrieval | hybrid",
  "steps": [
    {"step": 1, "tool": "sql | retrieval", "action": "..."}
  ]
}

Question: {question}"""


def fallback_plan(question: str, reason: str) -> dict:
    return {
        "query": question,
        "intent": "hybrid",
        "steps": [
            {"step": 1, "tool": "sql", "action": question},
            {"step": 2, "tool": "retrieval", "action": question},
        ],
        "fallback_reason": reason,
    }


def validate_plan(question: str, raw) -> dict:
    """Keeps only well-formed steps. Raises ValueError if nothing usable remains."""
    if not isinstance(raw, dict):
        raise ValueError("plan is not a JSON object")

    steps = []
    for s in raw.get("steps", [])[:MAX_STEPS]:
        if not isinstance(s, dict):
            continue
        tool = str(s.get("tool", "")).strip().lower()
        action = str(s.get("action", "")).strip()
        if tool in ALLOWED_TOOLS and action:
            steps.append({"step": len(steps) + 1, "tool": tool, "action": action})

    if not steps:
        raise ValueError("plan has no valid steps")

    tools = {s["tool"] for s in steps}
    intent = "hybrid" if tools == ALLOWED_TOOLS else tools.pop()
    return {"query": question, "intent": intent, "steps": steps}


def data_coverage() -> str:
    """Date range of the business data, so plans use real absolute dates."""
    try:
        from core.db import get_connection
        conn = get_connection(with_vector=False, readonly=True)
        try:
            cur = conn.cursor()
            cur.execute("SELECT MIN(date)::date, MAX(date)::date FROM revenue")
            lo, hi = cur.fetchone()
            return f"{lo} to {hi}" if lo else "unknown"
        finally:
            conn.close()
    except Exception:
        return "unknown"


WRITE_REQUEST = re.compile(
    r"^\s*(please\s+)?(delete|remove|drop|truncate|update|insert|modify|change|alter|"
    r"overwrite|erase|wipe|reset)\b", re.IGNORECASE)


def refusal_plan(question: str) -> dict:
    return {"query": question, "intent": "refuse", "steps": [],
            "refusal_reason": "This system is read-only and cannot modify data."}


def plan(question: str) -> dict:
    # deterministic guard: write requests never reach an LLM or a database
    if WRITE_REQUEST.search(question):
        result = refusal_plan(question)
        result["llm_usage"] = []
        return result

    prompt = (PLANNER_PROMPT
              .replace("{coverage}", data_coverage())
              .replace("{question}", question))
    messages = [
        {"role": "system", "content": "You output strict JSON execution plans."},
        {"role": "user", "content": prompt},
    ]
    usage = None
    try:
        raw, usage = llm.chat_json(messages)
        result = validate_plan(question, raw)
    except (ValueError, json.JSONDecodeError) as e:
        result = fallback_plan(question, str(e))
    result["llm_usage"] = [usage] if usage else []
    return result


if __name__ == "__main__":
    q = input("Enter question: ")
    print(json.dumps(plan(q), indent=2))
