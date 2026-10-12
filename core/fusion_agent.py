"""
Fusion Agent: combines SQL results and retrieved document chunks into a
draft answer made of discrete claims.

Every piece of evidence gets an id (sql:1, doc:2, ...). The LLM must attach
evidence ids to every claim, which is what lets the Verification Agent
check each claim against the exact rows or chunks it relied on.
"""
import json

from core import llm

MAX_ROWS_IN_PROMPT = 80

FUSION_PROMPT = """You are an evidence-bound enterprise analyst.

Answer the business question using ONLY the evidence below.

Rules:
- Break your answer into short, atomic claims. Each claim states ONE thing.
- Every claim MUST cite one or more evidence ids, e.g. ["sql:1", "doc:2"].
- type "fact": directly stated by the cited evidence (numbers copied exactly
  from SQL rows, or statements found in documents).
- type "inference": a conclusion drawn by combining cited evidence. Cite every
  piece of evidence the inference depends on.
- Never invent numbers, dates, names, or causes not present in the evidence.
- Use SQL evidence for WHAT changed and by how much; use documents for WHY.
- Check the question's premise against the SQL evidence. If the data does not
  show the change the question assumes, or contradicts the documents, say so
  plainly in the summary instead of following the question.
- When you state a change, cite the SQL rows that show both the before and
  after values.
- Copy numbers exactly from SQL rows. The ONLY arithmetic allowed is the
  difference or percentage change between two values that appear in the
  evidence, and you must state both values (e.g. "fell from 67292.0 to
  45015.0, a 33.1% drop"). Never add up or average rows yourself.
- Trust each SQL result for exactly what its "SQL result for:" line says it
  computed, including its filters and date range, even if the columns do not
  repeat them. Do not say the evidence is missing when a SQL result answers it.
- When a document states a cause (e.g. an incident review's "Root Cause"),
  state that cause directly and cite the document. Do not hedge a cause that
  the evidence states. Only call something uncertain when the evidence
  genuinely leaves it open.
- To describe a trend, compare whole periods (e.g. monthly totals, or several
  weeks before vs after an event), not two arbitrary weeks.
- A spike can be short: judge spikes from WEEKLY values, not monthly totals.
- For the effect of a dated event (a release, hotfix, incident, or campaign),
  compare the WEEKLY values just before that date with the weeks after it,
  using the event date stated in the documents. Monthly totals blur this.
- Direction words must match the numbers: "rose/increased" only if the later
  value is larger, "fell/dropped" only if it is smaller. Check every
  "from X to Y" you write.
- Do not claim a "correlation" unless the SQL rows compute one.
- Every timeline date must be stated in the evidence it cites. Do not move
  events between documents.
- If the evidence does not answer the question, say so in the summary and
  return no claims you cannot support.
- root_cause: the single best-supported explanation, or null if the evidence
  does not establish one.

Return JSON only:
{
  "summary": "2-3 sentence answer",
  "root_cause": "string or null",
  "claims": [
    {"id": "c1", "type": "fact | inference", "statement": "...", "evidence_ids": ["sql:1"]}
  ],
  "timeline": [
    {"date": "YYYY-MM-DD", "event": "...", "evidence_ids": ["doc:1"]}
  ],
  "recommendations": ["..."]
}

QUESTION: {question}

EVIDENCE:
{evidence}"""


def format_evidence(sql_results, chunks) -> str:
    blocks = []
    for r in sql_results:
        if r.get("error"):
            blocks.append(f"[{r['evidence_id']}] SQL step '{r['action']}' FAILED: {r['error']}")
            continue
        rows = r["rows"][:MAX_ROWS_IN_PROMPT]
        table = "\n".join(" | ".join(str(v) for v in row) for row in rows)
        more = f"\n... {r['row_count'] - len(rows)} more rows" if r["row_count"] > len(rows) else ""
        blocks.append(
            f"[{r['evidence_id']}] SQL result for: {r['action']}\n"
            f"columns: {' | '.join(r['columns'])}\n{table or '(no rows)'}{more}"
        )
    for c in chunks:
        blocks.append(
            f"[{c['evidence_id']}] DOCUMENT {c['source']} (department: {c['department']})\n"
            f"{c['content'].strip()}"
        )
    return "\n\n".join(blocks) if blocks else "(no evidence was retrieved)"


def normalize(raw: dict) -> dict:
    """Guarantees the shape downstream agents rely on, whatever the LLM returned."""
    claims = []
    for i, c in enumerate(raw.get("claims") or [], start=1):
        if not isinstance(c, dict) or not str(c.get("statement", "")).strip():
            continue
        ids = c.get("evidence_ids") or []
        claims.append({
            "id": str(c.get("id") or f"c{i}"),
            "type": "inference" if c.get("type") == "inference" else "fact",
            "statement": str(c["statement"]).strip(),
            "evidence_ids": [str(x) for x in ids] if isinstance(ids, list) else [str(ids)],
        })
    return {
        "summary": str(raw.get("summary") or "").strip(),
        "root_cause": raw.get("root_cause") or None,
        "claims": claims,
        "timeline": [t for t in (raw.get("timeline") or []) if isinstance(t, dict)],
        "recommendations": [str(r) for r in (raw.get("recommendations") or [])],
    }


def fuse(question: str, sql_results, chunks, feedback=None) -> dict:
    """feedback: verifier issues from a previous draft, used for one revision pass."""
    evidence = format_evidence(sql_results, chunks)
    messages = [
        {"role": "system", "content": "You output strict JSON and cite evidence for every claim."},
        {"role": "user", "content": FUSION_PROMPT
            .replace("{question}", question)
            .replace("{evidence}", evidence)},
    ]
    if feedback:
        problems = "\n".join(f"- {f}" for f in feedback)
        messages.append({"role": "user", "content":
                         "A verifier rejected parts of your previous draft:\n"
                         f"{problems}\n"
                         "Write a corrected answer. Drop or fix every rejected claim and "
                         "make the summary agree with the SQL evidence."})
    try:
        raw, usage = llm.chat_json(messages)
    except json.JSONDecodeError:
        raw, usage = {"summary": "Fusion step returned invalid JSON.", "claims": []}, None

    fused = normalize(raw)
    fused["query"] = question
    fused["available_evidence"] = [r["evidence_id"] for r in sql_results] + \
                                  [c["evidence_id"] for c in chunks]
    fused["llm_usage"] = [usage] if usage else []
    return fused
