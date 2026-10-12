"""
Runs the benchmark through the real pipeline and measures:

  Answer quality   answer accuracy (LLM grader vs. reference), SQL execution
                   accuracy, root-cause accuracy, distractor resistance,
                   false-premise handling
  Retrieval        recall@k and MRR against the documents each question needs
  Hallucination    unsupported-claim rate, ungrounded numbers in the final summary
  Verifier         stress test: inject wrong numbers and flipped trends into
                   real answers and measure how often verification catches them,
                   plus how often the judge raises false alarms on correct answers
  Safety           write requests must never change the database
  Cost             latency p50/p95, LLM calls, tokens, and cost per question

Usage (from the project root, with the backend NOT required):
    python -m evaluation.run_eval                 # full benchmark
    python -m evaluation.run_eval --limit 5       # quick check
    python -m evaluation.run_eval --ids why_01 fp_01
    python -m evaluation.run_eval --no-stress     # skip the verifier stress test
"""
import argparse
import json
import os
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path

from core import llm, sql_agent, verification_agent
from core.db import get_connection
from core.pipeline import run_investigation
from evaluation import metrics as M

BENCHMARK = Path("evaluation/benchmark.jsonl")
RESULTS_DIR = Path("evaluation/results")
# a stronger, different model grades the answers (avoids self-preference bias)
GRADER_MODEL = os.getenv("GRADER_MODEL", "gpt-4o")
REPORT = Path("evaluation/report.md")

GRADER_PROMPT = """You grade answers from an enterprise analytics assistant.

QUESTION: {question}

REFERENCE ANSWER (ground truth): {reference}

SYSTEM ANSWER:
{answer}

Grade the SYSTEM ANSWER against the REFERENCE on its key point(s) only.
Ignore extra detail, wording, and formatting.
- "correct": states the key point(s) of the reference and nothing that contradicts it.
- "partial": gets part of it right, or is right but hedged or incomplete.
- "incorrect": misses the key point, contradicts the reference, or accepts a
  false premise that the reference rejects.

Rules:
- Numbers: the answer is correct if it states the same value; ignore
  formatting, units, currency symbols, and rounding differences. Extra
  figures beyond the reference are fine.
- False premises: if the reference says the premise is false, the answer is
  correct when it states the actual facts that contradict the premise (for
  example "tickets increased" when asked why they decreased), even if it never
  uses the words "the premise is false".

Return JSON only: {"verdict": "correct | partial | incorrect", "reason": "..."}"""


# ----------------------------------------------------------------------
# HELPERS
# ----------------------------------------------------------------------
def load_benchmark(ids=None, limit=None):
    items = [json.loads(line) for line in BENCHMARK.read_text().splitlines() if line.strip()]
    if ids:
        items = [i for i in items if i["id"] in set(ids)]
    return items[:limit] if limit else items


def run_gold_sql(sql):
    columns, rows, _ = sql_agent.execute_readonly(sql_agent.validate_sql(sql))
    return columns, rows


def count_refunds():
    conn = get_connection(with_vector=False, readonly=True)
    try:
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM refunds")
        return cur.fetchone()[0]
    finally:
        conn.close()


def format_reference(columns, rows):
    """Turns gold SQL output into a plain-English reference for the grader."""
    if len(rows) == 1 and len(rows[0]) == 1:
        return f"The correct answer is {rows[0][0]}."
    parts = ["; ".join(f"{c} = {v}" for c, v in zip(columns, r)) for r in rows]
    return "The correct answer is: " + " | ".join(parts) + "."


def answer_text(result):
    report = result["report"]
    findings = "\n".join(f"- {f['statement']}" for f in report.get("findings", []))
    return (f"Summary: {report.get('executive_summary', '')}\n"
            f"Root cause: {report.get('root_cause', '')}\nFindings:\n{findings}")


def grade(question, reference, answer):
    prompt = (GRADER_PROMPT.replace("{question}", question)
              .replace("{reference}", reference).replace("{answer}", answer))
    try:
        raw, usage = llm.chat_json([
            {"role": "system", "content": "You are a fair, strict grader. Output JSON only."},
            {"role": "user", "content": prompt}], model=GRADER_MODEL)
        verdict = raw.get("verdict") if raw.get("verdict") in M.GRADE_POINTS else "incorrect"
        return {"verdict": verdict, "reason": raw.get("reason", "")}, usage
    except Exception as e:
        return {"verdict": "error", "reason": str(e)}, None


# ----------------------------------------------------------------------
# ONE QUESTION
# ----------------------------------------------------------------------
def evaluate_item(item):
    row = {"id": item["id"], "category": item["category"], "question": item["question"]}

    gold_rows, reference = None, item.get("reference_answer")
    if item.get("gold_sql"):
        cols, gold_rows = run_gold_sql(item["gold_sql"])
        row["gold_value"] = gold_rows
        if not reference:
            reference = format_reference(cols, gold_rows)

    refunds_before = count_refunds() if item.get("safety_check") else None

    started = time.perf_counter()
    try:
        result = run_investigation(item["question"])
    except Exception as e:
        row.update(error=str(e), latency_ms=round((time.perf_counter() - started) * 1000, 1))
        if refunds_before is not None:
            row["data_unchanged"] = count_refunds() == refunds_before
        return row, None

    report, verified, m = result["report"], result["verified"], result["metrics"]
    sql_results, chunks = result["sql"], result["documents"]
    summary = report.get("executive_summary", "")

    row.update(
        latency_ms=m["total_latency_ms"], llm_calls=m["llm_calls"], tokens=m["tokens"],
        cost_usd=m["cost_usd"], revisions=m["revisions"],
        planned_tools=sorted({s["tool"] for s in result["trace"]["steps"]}),
        summary=summary, root_cause=report.get("root_cause"),
        claims=sum(verified["counts"].values()),
        unsupported_claims=verified["counts"]["unsupported"],
        summary_consistent=verified["summary_consistent"],
        sql_errors=sum(1 for r in sql_results if r.get("error")),
        sql_self_corrected=sum(1 for r in sql_results if r.get("attempts", 1) > 1 and not r.get("error")),
        ungrounded_summary_numbers=M.ungrounded_summary_numbers(summary, sql_results, chunks),
        system_sql=[{"action": r["action"], "sql": r["sql"], "rows": r["rows"][:5],
                     "error": r["error"], "failed_attempts": r.get("failed_attempts", [])}
                    for r in sql_results],
        retrieved_sources=[c["source"] for c in chunks],
    )

    expected = set(item.get("expected_tools", []))
    row["routing_correct"] = expected.issubset(set(row["planned_tools"])) if expected else None

    if gold_rows is not None:
        row["sql_correct"] = M.sql_execution_correct(gold_rows, sql_results, summary)

    retrieval = M.retrieval_scores(item.get("gold_sources"), [c["source"] for c in chunks])
    if retrieval and "retrieval" in row["planned_tools"]:
        row.update(retrieval_recall=retrieval["recall"], retrieval_mrr=retrieval["mrr"])

    if item.get("required_keywords") or item.get("forbidden_keywords"):
        kc = M.keyword_check(f"{report.get('root_cause', '')} {summary}",
                             item.get("required_keywords"), item.get("forbidden_keywords"))
        row.update(root_cause_hit=kc["root_cause_hit"], distractor_hits=kc["distractor_hits"])

    if refunds_before is not None:
        row["data_unchanged"] = count_refunds() == refunds_before

    # questions with an exact answer are graded deterministically, not by an LLM
    if gold_rows is not None and row.get("sql_correct") and M.gold_in_text(gold_rows, summary):
        row.update(grade="correct", grade_reason="deterministic: gold value in SQL result and summary",
                   graded_by="deterministic")
        return row, result

    g, _ = grade(item["question"], reference or "", answer_text(result))
    row.update(grade=g["verdict"], grade_reason=g["reason"], graded_by=GRADER_MODEL)
    return row, result


# ----------------------------------------------------------------------
# VERIFIER STRESS TEST
# ----------------------------------------------------------------------
def stress_test(pairs):
    """Injects known errors into real, finished answers and re-runs verification."""
    numeric_trials, numeric_caught = 0, 0
    flip_trials, flip_caught = 0, 0
    clean_trials, false_alarms = 0, 0

    for row, result in pairs:
        if not result:
            continue
        fused, sql_results, chunks = result["fused"], result["sql"], result["documents"]

        # 1. wrong number in a SQL-backed fact claim -> deterministic check should reject it
        for c in fused["claims"]:
            if c["type"] == "fact" and any(e.startswith("sql:") for e in c["evidence_ids"]):
                bad = M.perturb_first_number(c["statement"])
                if bad:
                    tampered = {**fused, "claims": [{**c, "statement": bad}]}
                    v = verification_agent.verify(tampered, sql_results, chunks, use_judge=False)
                    numeric_trials += 1
                    numeric_caught += v["counts"]["unsupported"] == 1
                    break

        # 2. flipped trend in the summary -> judge should flag a contradiction
        has_sql = any(not r.get("error") for r in sql_results)
        if has_sql and row.get("grade") == "correct":
            flipped = M.flip_direction(fused.get("summary", ""))
            if flipped:
                v = verification_agent.verify({**fused, "summary": flipped, "claims": []},
                                              sql_results, chunks)
                flip_trials += 1
                flip_caught += not v["summary_consistent"]
            # 3. false alarms: correct answers the judge called inconsistent
            clean_trials += 1
            false_alarms += not row.get("summary_consistent", True)

    return {
        "numeric_error_catch_rate": round(numeric_caught / numeric_trials, 3) if numeric_trials else None,
        "numeric_trials": numeric_trials,
        "flipped_trend_catch_rate": round(flip_caught / flip_trials, 3) if flip_trials else None,
        "flip_trials": flip_trials,
        "judge_false_alarm_rate": round(false_alarms / clean_trials, 3) if clean_trials else None,
        "clean_trials": clean_trials,
    }


# ----------------------------------------------------------------------
# SUMMARY + REPORT
# ----------------------------------------------------------------------
def summarize(rows, stress):
    ok = [r for r in rows if "error" not in r]
    by_cat = lambda c: [r for r in ok if r["category"] == c]
    graded = [r for r in ok if r.get("grade") in M.GRADE_POINTS]

    summary = {
        "questions": len(rows),
        "pipeline_errors": len(rows) - len(ok),
        "answer_accuracy": M.mean([M.GRADE_POINTS[r["grade"]] for r in graded]),
        "answer_accuracy_by_category": {
            c: M.mean([M.GRADE_POINTS[r["grade"]] for r in graded if r["category"] == c])
            for c in sorted({r["category"] for r in graded})},
        "sql_execution_accuracy": M.rate([r.get("sql_correct") for r in ok if "sql_correct" in r]),
        "routing_accuracy": M.rate([r.get("routing_correct") for r in ok]),
        "retrieval_recall_at_k": M.mean([r.get("retrieval_recall") for r in ok]),
        "retrieval_mrr": M.mean([r.get("retrieval_mrr") for r in ok]),
        "root_cause_accuracy": M.rate([r.get("root_cause_hit") for r in ok if "root_cause_hit" in r]),
        "distractor_resistance": M.rate([not r["distractor_hits"] for r in ok if "distractor_hits" in r]),
        "false_premise_rejection": M.mean([M.GRADE_POINTS[r["grade"]] for r in by_cat("false_premise")
                                           if r.get("grade") in M.GRADE_POINTS]),
        "unsupported_claim_rate": round(sum(r["unsupported_claims"] for r in ok) /
                                        max(sum(r["claims"] for r in ok), 1), 3),
        "summaries_with_ungrounded_numbers": M.rate([bool(r["ungrounded_summary_numbers"]) for r in ok]),
        "revision_rate": M.rate([r["revisions"] > 0 for r in ok]),
        "sql_self_correction_count": sum(r["sql_self_corrected"] for r in ok),
        "sql_error_count": sum(r["sql_errors"] for r in ok),
        "safety_pass_rate": M.rate([r.get("data_unchanged") for r in rows if "data_unchanged" in r]),
        "latency_p50_s": (M.percentile([r["latency_ms"] for r in ok], 50) or 0) / 1000,
        "latency_p95_s": (M.percentile([r["latency_ms"] for r in ok], 95) or 0) / 1000,
        "avg_llm_calls": M.mean([r["llm_calls"] for r in ok]),
        "avg_tokens": M.mean([r["tokens"] for r in ok]),
        "avg_cost_usd": round(sum(r["cost_usd"] for r in ok) / len(ok), 6) if ok else None,
        "total_cost_usd": round(sum(r["cost_usd"] for r in ok), 4),
    }
    if stress:
        summary["verifier_stress_test"] = stress
    return summary


def pct(v):
    return "n/a" if v is None else f"{v * 100:.1f}%"


def write_report(summary, rows, path):
    s = summary
    lines = [
        "# Evaluation Report",
        "",
        f"Run: {datetime.now():%Y-%m-%d %H:%M} · {s['questions']} questions · "
        f"{s['pipeline_errors']} pipeline errors · total cost ${s['total_cost_usd']}",
        "",
        "## Headline metrics",
        "",
        "| Metric | Value |",
        "| --- | --- |",
        f"| Answer accuracy (LLM-graded vs. reference) | {pct(s['answer_accuracy'])} |",
        f"| SQL execution accuracy | {pct(s['sql_execution_accuracy'])} |",
        f"| Routing accuracy | {pct(s['routing_accuracy'])} |",
        f"| Retrieval recall@k | {pct(s['retrieval_recall_at_k'])} |",
        f"| Retrieval MRR | {s['retrieval_mrr']} |",
        f"| Root-cause accuracy | {pct(s['root_cause_accuracy'])} |",
        f"| Distractor resistance | {pct(s['distractor_resistance'])} |",
        f"| False-premise rejection | {pct(s['false_premise_rejection'])} |",
        f"| Unsupported-claim rate (final answers) | {pct(s['unsupported_claim_rate'])} |",
        f"| Summaries with ungrounded numbers | {pct(s['summaries_with_ungrounded_numbers'])} |",
        f"| Revision rate | {pct(s['revision_rate'])} |",
        f"| Safety (write requests left data unchanged) | {pct(s['safety_pass_rate'])} |",
        f"| Latency p50 / p95 | {s['latency_p50_s']:.1f}s / {s['latency_p95_s']:.1f}s |",
        f"| Avg LLM calls / tokens / cost per question | {s['avg_llm_calls']} / "
        f"{s['avg_tokens']:.0f} / ${s['avg_cost_usd']:.4f} |",
        "",
        "## Answer accuracy by category",
        "",
        "| Category | Accuracy |",
        "| --- | --- |",
    ] + [f"| {c} | {pct(v)} |" for c, v in s["answer_accuracy_by_category"].items()]

    st = s.get("verifier_stress_test")
    if st:
        lines += [
            "",
            "## Verifier stress test",
            "",
            "Known errors injected into real answers, then re-verified.",
            "",
            "| Check | Rate | Trials |",
            "| --- | --- | --- |",
            f"| Wrong numbers caught (deterministic check) | {pct(st['numeric_error_catch_rate'])} | {st['numeric_trials']} |",
            f"| Flipped trends caught (LLM judge) | {pct(st['flipped_trend_catch_rate'])} | {st['flip_trials']} |",
            f"| Judge false alarms on correct answers | {pct(st['judge_false_alarm_rate'])} | {st['clean_trials']} |",
        ]

    lines += ["", "## Per-question results", "",
              "| ID | Category | Grade | SQL | Recall | Root cause | Unsupported | Latency |",
              "| --- | --- | --- | --- | --- | --- | --- | --- |"]
    for r in rows:
        if "error" in r:
            lines.append(f"| {r['id']} | {r['category']} | ERROR: {r['error'][:60]} | | | | | |")
            continue
        sql = {True: "✅", False: "❌"}.get(r.get("sql_correct"), "")
        rc = {True: "✅", False: "❌"}.get(r.get("root_cause_hit"), "")
        lines.append(f"| {r['id']} | {r['category']} | {r.get('grade', '')} | {sql} | "
                     f"{r.get('retrieval_recall', '')} | {rc} | {r['unsupported_claims']} | "
                     f"{r['latency_ms'] / 1000:.1f}s |")
    path.write_text("\n".join(lines) + "\n")


# ----------------------------------------------------------------------
# MAIN
# ----------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--ids", nargs="*")
    parser.add_argument("--limit", type=int)
    parser.add_argument("--workers", type=int, default=2)
    parser.add_argument("--no-stress", action="store_true")
    args = parser.parse_args()

    items = load_benchmark(args.ids, args.limit)
    print(f"Running {len(items)} questions with {args.workers} worker(s)...")

    pairs = []
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        for row, result in pool.map(evaluate_item, items):
            status = row.get("grade") or f"ERROR {row.get('error', '')[:60]}"
            print(f"  {row['id']:<8} {status:<10} {row.get('latency_ms', 0) / 1000:5.1f}s")
            pairs.append((row, result))

    rows = [r for r, _ in pairs]
    stress = None if args.no_stress else stress_test(pairs)
    summary = summarize(rows, stress)

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    out = RESULTS_DIR / f"eval_{datetime.now():%Y%m%d_%H%M%S}.json"
    out.write_text(json.dumps({"summary": summary, "rows": rows}, indent=2, default=str))
    write_report(summary, rows, REPORT)

    print("\n" + json.dumps(summary, indent=2, default=str))
    print(f"\nSaved {out} and {REPORT}")


if __name__ == "__main__":
    main()
