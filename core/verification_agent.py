"""
Verification Agent: checks every claim from the Fusion Agent against the
evidence it cites, then checks the summary against the SQL evidence.

Stage 1, deterministic (no LLM):
  1. Citation check: a claim must cite at least one evidence id that exists.
  2. Numeric grounding: every number in a claim must appear in the evidence
     it cites (SQL row values or document text), allowing for rounding and sign,
     OR be the difference or percentage change between two grounded numbers
     stated in the same claim ("fell from 67292 to 45015, a 33.1% drop").
  3. Date grounding: every date in a claim must appear in the evidence it cites.
     Dates are checked as dates, never as loose numbers. When a claim names a
     date, its numbers are checked against THAT date's rows, not the whole table.
  4. Direction check: "rose/fell from X to Y" must agree with whether Y > X.

Stage 2, LLM judge (only for claims stage 1 could not settle):
  3. Entailment: is the claim actually stated or directly implied by the
     specific evidence it cites?
  4. Consistency: does any SQL result contradict the summary's direction or
     magnitude (e.g. summary says revenue fell, SQL shows it rose)?

Claim statuses:
  supported     passed every check
  unsupported   failed a check (missing citation, ungrounded number, or the
                judge found the evidence does not support it)
  needs_review  the judge found it only partially supported
"""
import json
import re

from core import llm

NUMBER_RE = re.compile(r"-?\d[\d,]*\.?\d*")
MONTHS = {m: i for i, m in enumerate(
    ["january", "february", "march", "april", "may", "june", "july", "august",
     "september", "october", "november", "december"], start=1)}
MONTH_DAY_RE = re.compile(
    r"\b(" + "|".join(MONTHS) + r")\s+(\d{1,2})(?!\d)(?:st|nd|rd|th)?(?:,?\s+(\d{4}))?", re.IGNORECASE)
ISO_DATE_RE = re.compile(r"\b(\d{4})-(\d{2})-(\d{2})\b")
MONTH_YEAR_RE = re.compile(r"\b(" + "|".join(MONTHS) + r")\s+(\d{4})\b", re.IGNORECASE)
YEAR_RE = re.compile(r"\b(?:19|20)\d{2}\b")
REL_TOLERANCE = 0.005  # 0.5% to allow rounding of large values
MAX_DERIVATION_VALUES = 400


def strip_dates(text: str) -> str:
    """Removes every date expression so its parts aren't read as metric numbers."""
    for pattern in (ISO_DATE_RE, MONTH_YEAR_RE, MONTH_DAY_RE, YEAR_RE):
        text = pattern.sub(" ", text)
    return text


def extract_numbers(text: str):
    """'Revenue fell 26.0% to $73,939 on April 21, 2025' -> ['26.0', '73939']

    Dates (2025-04-21, April 21 2025, March 2025, 2025) are removed first so
    they are never misread as metric numbers; dates are checked separately.
    """
    nums = [m.replace(",", "").rstrip(".") for m in NUMBER_RE.findall(strip_dates(text))]
    return [n for n in nums if n not in ("", "-")]


def _evidence_numbers(evidence_ids, sql_by_id, docs_by_id):
    values = []
    for eid in evidence_ids:
        if eid in sql_by_id:
            r = sql_by_id[eid]
            for row in r["rows"]:
                for v in row:
                    if isinstance(v, bool):
                        continue
                    if isinstance(v, (int, float)):
                        values.append(float(v))
                    elif v is not None:
                        values.extend(float(n) for n in extract_numbers(str(v)))
        elif eid in docs_by_id:
            values.extend(float(n) for n in extract_numbers(docs_by_id[eid]["content"]))
    return values


def number_is_grounded(token: str, evidence_values) -> bool:
    x = abs(float(token))
    decimals = len(token.split(".")[1]) if "." in token else 0
    for v in evidence_values:
        v = abs(v)
        if round(v, decimals) == x:
            return True
        if v and abs(v - x) / v <= REL_TOLERANCE:
            return True
    return False


def number_is_derived(token: str, stated_values) -> bool:
    """True if the number is the difference or percentage change between two
    OTHER numbers stated in the same text (which must themselves be grounded).

    Only values the text itself states are used, never all evidence values: with
    hundreds of evidence values, some pair would match almost any number by
    coincidence, which would let hallucinated numbers through.
    """
    x = abs(float(token))
    decimals = len(token.split(".")[1]) if "." in token else 0
    half_unit = 0.5 * 10 ** (-decimals) + 1e-9
    values = [abs(v) for v in stated_values]
    for a in values:
        for b in values:
            if a == b:
                continue
            if abs(abs(a - b) - x) <= max(half_unit, REL_TOLERANCE * x):
                return True
            if b and abs(abs(a - b) / b * 100 - x) <= half_unit:
                return True
    return False


def ungrounded_numbers(text: str, evidence_values):
    """Numbers in text that are neither in the evidence nor derived from two
    grounded numbers stated alongside them."""
    nums = extract_numbers(text)
    grounded = [n for n in nums if number_is_grounded(n, evidence_values)]
    stated = [float(n) for n in grounded]
    return [n for n in nums if n not in grounded and not number_is_derived(n, stated)]


UP_WORDS = r"rose|risen|rise|rising|increased|increase|increasing|grew|grown|growth|climbed|jumped|up|higher|recovered"
DOWN_WORDS = r"fell|fallen|fall|falling|dropped|drop|dropping|decreased|decrease|decreasing|declined|decline|down|lower|lost"
FROM_TO_RE = re.compile(r"from\s+[$€£]?(-?[\d,]+\.?\d*)\D{0,40}?\s+to\s+[$€£]?(-?[\d,]+\.?\d*)", re.IGNORECASE)


def direction_errors(text: str):
    """Finds "rose from X to Y" with Y < X (or "fell" with Y > X).

    Looks at the words just around each "from X to Y" (dates removed first),
    so a sentence like "rose from 6866 to 4622, a 33.1% drop" is caught.
    """
    errors = []
    cleaned = strip_dates(text)
    for m in FROM_TO_RE.finditer(cleaned):
        try:
            x = float(m.group(1).replace(",", ""))
            y = float(m.group(2).replace(",", ""))
        except ValueError:
            continue
        if x == y:
            continue
        window = cleaned[max(0, m.start() - 40): m.end() + 30].lower()
        ups = re.findall(rf"\b({UP_WORDS})\b", window)
        downs = re.findall(rf"\b({DOWN_WORDS})\b", window)
        wrong = ups if y < x else downs
        if wrong:
            actual = "a decrease" if y < x else "an increase"
            errors.append(f"'{wrong[0]}' used for {m.group(1)} -> {m.group(2)}, which is {actual}")
    return errors


def _row_anchored_values(claim_dates, evidence_ids, sql_by_id, docs_by_id):
    """Numbers from only the SQL rows dated on the claim's dates (plus cited docs).
    Returns None when no cited row matches those dates."""
    values, matched = [], False
    for eid in evidence_ids:
        if eid in sql_by_id:
            for row in sql_by_id[eid]["rows"]:
                row_dates = set()
                for v in row:
                    if isinstance(v, str):
                        row_dates |= extract_dates(v)
                if row_dates & claim_dates:
                    matched = True
                    values += _evidence_numbers_from_rows([row])
        elif eid in docs_by_id:
            values += [float(n) for n in extract_numbers(docs_by_id[eid]["content"])]
    return values if matched else None


def _evidence_numbers_from_rows(rows):
    values = []
    for row in rows:
        for v in row:
            if isinstance(v, bool) or v is None:
                continue
            if isinstance(v, (int, float)):
                values.append(float(v))
            else:
                values.extend(float(n) for n in extract_numbers(str(v)))
    return values


def check_claim(claim, sql_by_id, docs_by_id, allowed_dates=frozenset()) -> dict:
    valid_ids = [e for e in claim["evidence_ids"] if e in sql_by_id or e in docs_by_id]
    invalid_ids = [e for e in claim["evidence_ids"] if e not in valid_ids]
    result = {**claim, "valid_evidence_ids": valid_ids, "invalid_evidence_ids": invalid_ids,
              "ungrounded_numbers": []}

    if not valid_ids:
        result.update(status="unsupported", reason="no valid evidence cited")
        return result

    claim_dates = extract_dates(claim["statement"])
    anchored = _row_anchored_values(claim_dates, valid_ids, sql_by_id, docs_by_id) if claim_dates else None
    evidence_values = anchored if anchored is not None else _evidence_numbers(valid_ids, sql_by_id, docs_by_id)
    ungrounded = ungrounded_numbers(claim["statement"], evidence_values)
    if ungrounded:
        result.update(status="unsupported", ungrounded_numbers=ungrounded,
                      reason=f"numbers not found in cited evidence: {', '.join(ungrounded)}")
        return result

    wrong_direction = direction_errors(claim["statement"])
    if wrong_direction:
        result.update(status="unsupported", reason=f"direction contradicts numbers: {wrong_direction[0]}")
        return result

    evidence_dates = _evidence_dates(valid_ids, sql_by_id, docs_by_id) | set(allowed_dates)
    bad_dates = sorted(claim_dates - evidence_dates)
    if bad_dates:
        result.update(status="unsupported", ungrounded_numbers=bad_dates,
                      reason=f"dates not found in cited evidence: {', '.join(bad_dates)}")
        return result

    cites_docs = any(e in docs_by_id for e in valid_ids)
    if cites_docs or claim["type"] == "inference":
        result.update(status="needs_review", reason="relies on document wording or inference")
    else:
        result.update(status="supported", reason="numbers grounded in SQL results")
    return result


def extract_dates(text: str):
    """ISO dates mentioned in text: '2025-04-15', 'April 15 2025', 'March 10 and March 14 2025'.

    A month-day without a year takes the next year mentioned after it.
    """
    dates = {f"{y}-{m}-{d}" for y, m, d in ISO_DATE_RE.findall(text)}
    matches = list(MONTH_DAY_RE.finditer(text))
    for i, m in enumerate(matches):
        year = m.group(3)
        if not year:
            later = [x.group(3) for x in matches[i + 1:] if x.group(3)]
            year = later[0] if later else None
        if year:
            dates.add(f"{year}-{MONTHS[m.group(1).lower()]:02d}-{int(m.group(2)):02d}")
    return dates


def _evidence_dates(evidence_ids, sql_by_id, docs_by_id):
    dates = set()
    for eid in evidence_ids:
        if eid in docs_by_id:
            dates |= extract_dates(docs_by_id[eid]["content"])
        elif eid in sql_by_id:
            for row in sql_by_id[eid]["rows"]:
                for v in row:
                    dates |= extract_dates(str(v))
    return dates


def verify_timeline(timeline, sql_by_id, docs_by_id):
    """Keeps a timeline event only if its date appears in the evidence it cites."""
    kept, dropped = [], []
    for t in timeline:
        ids = [e for e in t.get("evidence_ids", []) if e in sql_by_id or e in docs_by_id]
        date = str(t.get("date", ""))[:10]
        if ids and date in _evidence_dates(ids, sql_by_id, docs_by_id):
            kept.append({**t, "evidence_ids": ids})
        else:
            dropped.append({**t, "reason": f"date {date} not found in cited evidence"})
    return kept, dropped


def compute_confidence(checked) -> float:
    """supported = 1, needs_review = 0.5, unsupported = 0, averaged over claims."""
    if not checked:
        return 0.0
    weights = {"supported": 1.0, "needs_review": 0.5, "unsupported": 0.0}
    return round(sum(weights[c["status"]] for c in checked) / len(checked), 2)


# ----------------------------------------------------------------------
# STAGE 2: LLM JUDGE
# ----------------------------------------------------------------------
JUDGE_PROMPT = """You are a strict fact checker for an enterprise analytics system.

PART 1. For each claim, decide using ONLY the evidence listed under that claim:
- "supported": the evidence states it, or it follows directly from the evidence.
- "partial": some of it is supported, some is not.
- "unsupported": the evidence does not state it, or contradicts it.
Judge causal words ("because", "caused", "due to") strictly: the evidence must
state or clearly show the causal link.

PART 2. Compare the SUMMARY with ALL SQL evidence, region by region.
Report an issue ONLY when you can name the exact SQL values that contradict
a summary statement. Classify each issue:
- type "direction": the summary says a metric rose but SQL shows it fell, or
  the reverse.
- type "magnitude": the summary states a size of change (e.g. "halved",
  "26%") that the SQL values clearly do not match.
- type "not_shown": the summary describes a change that no SQL result covers.
- type "wording": causal or statistical wording ("correlation", "due to")
  stronger than the evidence, while the numbers themselves agree.
Severity "high" only for direction or magnitude errors a reader would act on.
Normal week-to-week noise is not an issue. If the SQL values agree with the
summary, return an empty list. Do not report an issue and then say the data
agrees.

Return JSON only:
{
  "claims": [{"id": "c1", "verdict": "supported | partial | unsupported", "reason": "..."}],
  "issues": [
    {"type": "direction | magnitude | not_shown | wording", "severity": "high | low",
     "summary_statement": "...", "sql_values": "...", "explanation": "..."}
  ]
}

SUMMARY:
{summary}

ALL SQL EVIDENCE:
{sql_evidence}

CLAIMS TO CHECK:
{claims}"""


def _evidence_text(eid, sql_by_id, docs_by_id, max_rows=80):
    if eid in sql_by_id:
        r = sql_by_id[eid]
        rows = "\n".join(" | ".join(str(v) for v in row) for row in r["rows"][:max_rows])
        return f"[{eid}] SQL for: {r['action']}\ncolumns: {' | '.join(r['columns'])}\n{rows}"
    d = docs_by_id[eid]
    return f"[{eid}] DOCUMENT {d['source']}\n{d['content'].strip()}"


def judge(summary, claims, sql_by_id, docs_by_id):
    """One LLM call that checks all pending claims and the summary."""
    claim_blocks = []
    for c in claims:
        evidence = "\n\n".join(_evidence_text(e, sql_by_id, docs_by_id)
                                for e in c["valid_evidence_ids"])
        claim_blocks.append(f"CLAIM {c['id']} ({c['type']}): {c['statement']}\n"
                            f"EVIDENCE FOR {c['id']}:\n{evidence}")
    sql_evidence = "\n\n".join(_evidence_text(e, sql_by_id, docs_by_id) for e in sql_by_id) \
        or "(no SQL evidence)"

    prompt = (JUDGE_PROMPT
              .replace("{summary}", summary or "(empty)")
              .replace("{sql_evidence}", sql_evidence)
              .replace("{claims}", "\n\n---\n\n".join(claim_blocks) or "(none)"))
    messages = [{"role": "system", "content": "You are a strict, skeptical fact checker. Output JSON only."},
                {"role": "user", "content": prompt}]
    try:
        raw, usage = llm.chat_json(messages)
    except json.JSONDecodeError:
        return {}, True, [], [{"type": "judge_error", "explanation": "judge returned invalid JSON"}], None

    verdicts = {str(v.get("id")): v for v in raw.get("claims", []) if isinstance(v, dict)}
    issues = [i for i in raw.get("issues", []) or [] if isinstance(i, dict)]
    return verdicts, *classify_issues(issues), usage


BLOCKING_TYPES = {"direction", "magnitude"}


def classify_issues(issues):
    """Only high-severity direction/magnitude contradictions that quote SQL values
    mark the summary inconsistent. Everything else is kept as a note."""
    blocking, notes = [], []
    for i in issues:
        is_blocking = (i.get("type") in BLOCKING_TYPES and i.get("severity") == "high"
                       and str(i.get("sql_values", "")).strip())
        (blocking if is_blocking else notes).append(i)
    return not blocking, blocking, notes


VERDICT_STATUS = {"supported": "supported", "partial": "needs_review", "unsupported": "unsupported"}


def verify(fused: dict, sql_results, chunks, use_judge: bool = True) -> dict:
    sql_by_id = {r["evidence_id"]: r for r in sql_results if not r.get("error")}
    docs_by_id = {c["evidence_id"]: c for c in chunks}

    question_dates = frozenset(extract_dates(fused.get("query", "")))
    checked = [check_claim(c, sql_by_id, docs_by_id, question_dates) for c in fused.get("claims", [])]

    summary_consistent, consistency_issues, consistency_notes, usage = True, [], [], None
    pending = [c for c in checked if c["status"] == "needs_review"]
    if use_judge and (pending or sql_by_id):
        verdicts, summary_consistent, consistency_issues, consistency_notes, usage = judge(
            fused.get("summary", ""), pending, sql_by_id, docs_by_id)
        for c in pending:
            v = verdicts.get(c["id"])
            if not v:
                c["reason"] = "judge returned no verdict"
                continue
            c["status"] = VERDICT_STATUS.get(v.get("verdict"), "needs_review")
            c["reason"] = f"judge: {v.get('reason', '')}".strip()

    timeline, dropped_timeline = verify_timeline(fused.get("timeline", []), sql_by_id, docs_by_id)

    # numbers in the summary must exist somewhere in the evidence (catches LLM arithmetic)
    all_values = _evidence_numbers(list(sql_by_id) + list(docs_by_id), sql_by_id, docs_by_id)
    all_values += [float(n) for n in extract_numbers(fused.get("query", ""))]  # numbers the user gave
    summary = fused.get("summary", "")
    for err in direction_errors(summary):
        summary_consistent = False
        consistency_issues = consistency_issues + [{
            "type": "direction", "severity": "high", "summary_statement": summary,
            "sql_values": "stated in the summary itself",
            "explanation": f"trend word contradicts the numbers: {err}",
        }]
    bad_numbers = ungrounded_numbers(summary, all_values)
    all_dates = _evidence_dates(list(sql_by_id) + list(docs_by_id), sql_by_id, docs_by_id)
    bad_numbers += sorted(extract_dates(summary) - all_dates - question_dates)
    if bad_numbers:
        summary_consistent = False
        consistency_issues = consistency_issues + [{
            "type": "ungrounded_number", "severity": "high",
            "summary_statement": fused.get("summary", ""),
            "sql_values": "none match",
            "explanation": f"summary numbers or dates not found in any evidence: {', '.join(bad_numbers)}",
        }]

    counts = {s: sum(1 for c in checked if c["status"] == s)
              for s in ("supported", "needs_review", "unsupported")}

    return {
        "claims": checked,
        "verified_claims": [c for c in checked if c["status"] != "unsupported"],
        "rejected_claims": [c for c in checked if c["status"] == "unsupported"],
        "counts": counts,
        "unsupported_rate": round(counts["unsupported"] / len(checked), 3) if checked else 0.0,
        "timeline": timeline,
        "rejected_timeline": dropped_timeline,
        "summary_consistent": summary_consistent,
        "consistency_issues": consistency_issues,
        "consistency_notes": consistency_notes,
        # an answer that contradicts its own data should never look confident
        "confidence": round(compute_confidence(checked) * (1.0 if summary_consistent else 0.5), 2),
        "llm_usage": [usage] if usage else [],
    }
