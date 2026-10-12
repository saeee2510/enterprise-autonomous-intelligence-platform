"""
Evaluation metrics. Everything here is a pure function so it can be unit
tested without an API key or database.
"""
import re
import statistics

from core.verification_agent import extract_numbers, ungrounded_numbers

REL_TOL = 0.001  # 0.1%: allows rounding (54.27 vs 54.3) but not wrong counts (897 vs 900)


# ----------------------------------------------------------------------
# SQL EXECUTION ACCURACY
# ----------------------------------------------------------------------
def flatten_values(rows):
    nums, texts = [], []
    for row in rows:
        for v in row:
            if isinstance(v, bool) or v is None:
                continue
            if isinstance(v, (int, float)):
                nums.append(float(v))
            else:
                texts.append(str(v).strip().lower())
    return nums, texts


def numbers_match(gold: float, candidates) -> bool:
    return any(abs(c - gold) <= max(REL_TOL * abs(gold), 0.01) for c in candidates)


def sql_execution_correct(gold_rows, system_sql_results, summary: str = "") -> bool:
    """Execution accuracy: every gold value (number or text) appears in the
    system's SQL results. Compares results, not query text, because many
    different queries are correct."""
    gold_nums, gold_texts = flatten_values(gold_rows)
    if not gold_nums and not gold_texts:
        return False
    sys_nums, sys_texts = [], []
    for r in system_sql_results:
        if r.get("error"):
            continue
        n, t = flatten_values(r.get("rows", []))
        sys_nums += n
        sys_texts += t
    text_pool = " ".join(sys_texts) + " " + summary.lower()
    # word-boundary match so a short value like "na" doesn't match "analysis"
    return (all(numbers_match(g, sys_nums) for g in gold_nums)
            and all(re.search(rf"\b{re.escape(g)}\b", text_pool) for g in gold_texts))


def gold_in_text(gold_rows, text: str) -> bool:
    """True if every gold value (number or text) is stated in the text."""
    gold_nums, gold_texts = flatten_values(gold_rows)
    if not gold_nums and not gold_texts:
        return False
    stated = [float(n) for n in extract_numbers(text)]
    t = text.lower()
    return (all(numbers_match(g, stated) for g in gold_nums)
            and all(re.search(rf"\b{re.escape(g)}\b", t) for g in gold_texts))


# ----------------------------------------------------------------------
# RETRIEVAL
# ----------------------------------------------------------------------
def retrieval_scores(gold_sources, retrieved_sources):
    """recall@k = share of gold documents retrieved; MRR = 1 / rank of the first gold doc."""
    if not gold_sources:
        return None
    gold = set(gold_sources)
    recall = len(gold & set(retrieved_sources)) / len(gold)
    mrr = 0.0
    for rank, src in enumerate(retrieved_sources, start=1):
        if src in gold:
            mrr = 1.0 / rank
            break
    return {"recall": round(recall, 3), "mrr": round(mrr, 3)}


# ----------------------------------------------------------------------
# ROOT CAUSE + DISTRACTORS
# ----------------------------------------------------------------------
def keyword_check(text: str, required_groups, forbidden):
    """required_groups: list of any-of groups, all groups must match.
    forbidden: words that must not appear (distractor causes)."""
    t = text.lower()
    required_ok = all(any(k.lower() in t for k in group) for group in (required_groups or []))
    hits = [k for k in (forbidden or []) if re.search(rf"\b{re.escape(k.lower())}\b", t)]
    return {"root_cause_hit": required_ok, "distractor_hits": hits}


# ----------------------------------------------------------------------
# HALLUCINATION
# ----------------------------------------------------------------------
def evidence_values(sql_results, chunks):
    values = []
    for r in sql_results:
        if r.get("error"):
            continue
        n, t = flatten_values(r.get("rows", []))
        values += n
        for text in t:
            values += [float(x) for x in extract_numbers(text)]
    for c in chunks:
        values += [float(x) for x in extract_numbers(c.get("content", ""))]
    return values


def ungrounded_summary_numbers(summary: str, sql_results, chunks):
    """Numbers in the final executive summary that appear in no evidence at all."""
    return ungrounded_numbers(summary, evidence_values(sql_results, chunks))


# ----------------------------------------------------------------------
# VERIFIER STRESS TEST HELPERS
# ----------------------------------------------------------------------
_NUM = re.compile(r"\d[\d,]*\.?\d*")


def perturb_first_number(statement: str, factor: float = 1.5):
    """'fell 26%' -> 'fell 39%'. Returns None if the statement has no number."""
    m = _NUM.search(statement)
    if not m:
        return None
    raw = m.group(0).replace(",", "").rstrip(".")
    value = float(raw) * factor
    new = f"{value:.2f}" if "." in raw else str(round(value))
    return statement[:m.start()] + new + statement[m.end():]


_FLIPS = [("dropped", "rose"), ("decreased", "increased"), ("declined", "grew"),
          ("fell", "rose"), ("drop", "rise"), ("decline", "growth"), ("decrease", "increase")]
_FLIPS = _FLIPS + [(up, down) for down, up in _FLIPS]


def flip_direction(summary: str):
    """Reverses the first trend word (fell <-> rose, ...). None if nothing to flip."""
    earliest = None
    for a, b in _FLIPS:
        m = re.search(rf"\b{a}\b", summary, re.IGNORECASE)
        if m and (earliest is None or m.start() < earliest[0].start()):
            earliest = (m, b)
    if not earliest:
        return None
    m, replacement = earliest
    return summary[:m.start()] + replacement + summary[m.end():]


# ----------------------------------------------------------------------
# AGGREGATION
# ----------------------------------------------------------------------
def percentile(values, p):
    if not values:
        return None
    values = sorted(values)
    k = (len(values) - 1) * p / 100
    lo, hi = int(k), min(int(k) + 1, len(values) - 1)
    return round(values[lo] + (values[hi] - values[lo]) * (k - lo), 1)


def rate(flags):
    flags = [f for f in flags if f is not None]
    return round(sum(1 for f in flags if f) / len(flags), 3) if flags else None


def mean(values):
    values = [v for v in values if v is not None]
    return round(statistics.mean(values), 3) if values else None


GRADE_POINTS = {"correct": 1.0, "partial": 0.5, "incorrect": 0.0}
