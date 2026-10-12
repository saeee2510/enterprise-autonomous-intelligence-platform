"""
Observability layer: writes one row per pipeline step to execution_logs and
one row per investigation to investigations.

Logging must never break an investigation, so database errors are caught and
reported as warnings. Set ENABLED = False (as the tests do) to skip the database.
"""
import json
import logging
import uuid

from core.db import get_connection

ENABLED = True
log = logging.getLogger("eaip.observability")


def new_trace_id() -> str:
    return str(uuid.uuid4())


def summarize_usage(usages):
    usages = [u for u in usages if u]
    return {
        "llm_calls": len(usages),
        "tokens": sum(u.get("prompt_tokens", 0) + u.get("completion_tokens", 0) for u in usages),
        "cost_usd": round(sum(u.get("cost_usd", 0.0) for u in usages), 6),
    }


def log_step(trace_id, query, step, input_data, output_data, latency_ms,
             tokens=0, cost_usd=0.0, success=True):
    if not ENABLED:
        return
    try:
        conn = get_connection(with_vector=False)
        try:
            conn.cursor().execute(
                """
                INSERT INTO execution_logs
                    (trace_id, query, step, input, output, latency_ms, tokens, cost_usd, success)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (trace_id, query, step, json.dumps(input_data, default=str),
                 json.dumps(output_data, default=str), latency_ms, tokens, cost_usd, success),
            )
            conn.commit()
        finally:
            conn.close()
    except Exception as e:  # never fail the investigation because logging failed
        log.warning("could not write execution log for %s/%s: %s", trace_id, step, e)


def save_investigation(trace_id, question, plan, report):
    if not ENABLED:
        return
    try:
        conn = get_connection(with_vector=False)
        try:
            conn.cursor().execute(
                """
                INSERT INTO investigations (id, question, plan, final_report)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (id) DO UPDATE SET final_report = EXCLUDED.final_report
                """,
                (trace_id, question, json.dumps(plan, default=str), json.dumps(report, default=str)),
            )
            conn.commit()
        finally:
            conn.close()
    except Exception as e:
        log.warning("could not save investigation %s: %s", trace_id, e)


def get_investigation(trace_id):
    conn = get_connection(with_vector=False, readonly=True)
    try:
        cur = conn.cursor()
        cur.execute("SELECT id::text, question, plan, final_report, created_at "
                    "FROM investigations WHERE id = %s", (trace_id,))
        row = cur.fetchone()
        if not row:
            return None
        return {"id": row[0], "question": row[1], "plan": row[2],
                "report": row[3], "created_at": row[4].isoformat()}
    finally:
        conn.close()


def get_logs(trace_id):
    conn = get_connection(with_vector=False, readonly=True)
    try:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT step, latency_ms, tokens, cost_usd, success, input, output, created_at
            FROM execution_logs WHERE trace_id = %s ORDER BY id
            """,
            (trace_id,),
        )
        return [{"step": r[0], "latency_ms": r[1], "tokens": r[2], "cost_usd": r[3],
                 "success": r[4], "input": r[5], "output": r[6],
                 "created_at": r[7].isoformat()} for r in cur.fetchall()]
    finally:
        conn.close()
