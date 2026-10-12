"""
SQL Agent: generates, validates, and executes read-only SQL.

Safety is layered so no single check has to be perfect:
  1. validate_sql()  rejects anything that isn't a single SELECT/WITH statement
                     or that contains write/DDL keywords.
  2. The connection is opened in READ ONLY mode, so Postgres itself rejects
     writes even if validation missed something.
  3. A statement timeout and row cap stop runaway queries.

If a query fails, the error is sent back to the LLM once to self-correct.
"""
import datetime
import decimal
import re
from functools import lru_cache

from core import llm
from core.db import get_connection

BUSINESS_TABLES = ["customers", "products", "orders", "refunds", "support_tickets", "revenue"]

TABLE_DESCRIPTIONS = {
    "customers": "One row per customer. region is where the customer is based.",
    "products": "Product catalog with list price.",
    "orders": "One row per order. revenue is the gross order amount.",
    "refunds": "Refunds issued against orders, with the refund reason.",
    "support_tickets": "Customer support tickets. resolution_time is in hours.",
    "revenue": "Daily NET revenue per region (gross orders minus refunds). "
               "Prefer this table for revenue totals and trends.",
}

MAX_ROWS = 200
STATEMENT_TIMEOUT_MS = 5000
MAX_ATTEMPTS = 2

FORBIDDEN = re.compile(
    r"\b(insert|update|delete|drop|alter|create|truncate|grant|revoke|copy|"
    r"merge|call|vacuum|reindex|comment|set|reset|lock|execute|prepare)\b",
    re.IGNORECASE,
)
INTERNAL_TABLES = re.compile(r"\b(documents|execution_logs|investigations)\b", re.IGNORECASE)


class UnsafeSQLError(Exception):
    pass


# ----------------------------------------------------------------------
# SCHEMA CONTEXT (columns, foreign keys, low-cardinality values, date ranges)
# ----------------------------------------------------------------------
@lru_cache(maxsize=1)
def get_schema_context() -> str:
    conn = get_connection(with_vector=False, readonly=True)
    try:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT table_name, column_name, data_type
            FROM information_schema.columns
            WHERE table_schema = 'public' AND table_name = ANY(%s)
            ORDER BY table_name, ordinal_position
            """,
            (BUSINESS_TABLES,),
        )
        columns = {}
        for table, col, dtype in cur.fetchall():
            columns.setdefault(table, []).append((col, dtype))

        cur.execute(
            """
            SELECT tc.table_name, kcu.column_name, ccu.table_name, ccu.column_name
            FROM information_schema.table_constraints tc
            JOIN information_schema.key_column_usage kcu
              ON tc.constraint_name = kcu.constraint_name
            JOIN information_schema.constraint_column_usage ccu
              ON tc.constraint_name = ccu.constraint_name
            WHERE tc.constraint_type = 'FOREIGN KEY'
            """
        )
        foreign_keys = cur.fetchall()

        lines = []
        for table in BUSINESS_TABLES:
            if table not in columns:
                continue
            lines.append(f"TABLE {table} -- {TABLE_DESCRIPTIONS.get(table, '')}")
            for col, dtype in columns[table]:
                note = ""
                if dtype == "text" and col != "name":
                    cur.execute(f"SELECT DISTINCT {col} FROM {table} LIMIT 11")
                    values = sorted(str(r[0]) for r in cur.fetchall() if r[0] is not None)
                    if len(values) <= 10:
                        note = f"  values: {', '.join(values)}"
                elif dtype.startswith("timestamp"):
                    cur.execute(f"SELECT MIN({col})::date, MAX({col})::date FROM {table}")
                    lo, hi = cur.fetchone()
                    note = f"  range: {lo} to {hi}"
                lines.append(f"  {col} {dtype}{note}")
            lines.append("")

        lines.append("FOREIGN KEYS:")
        for t, c, ft, fc in foreign_keys:
            lines.append(f"  {t}.{c} -> {ft}.{fc}")

        cur.execute("SELECT MIN(date)::date, MAX(date)::date FROM revenue")
        lo, hi = cur.fetchone()
        weeks = complete_week_range(lo, hi)
        if weeks:
            lines.append("")
            lines.append(f"COMPLETE WEEKS (Monday to Sunday, use ONLY for weekly trends): "
                         f"{weeks[0]} to {weeks[1]}")
        return "\n".join(lines)
    finally:
        conn.close()


def complete_week_range(start, end):
    """First Monday on/after start and last Sunday on/before end, as ISO strings.

    Weekly trends that include partial weeks at the edges show artificial dips,
    so weekly queries are restricted to this range.
    """
    if not start or not end:
        return None
    first_monday = start + datetime.timedelta(days=(7 - start.weekday()) % 7)
    last_sunday = end - datetime.timedelta(days=(end.weekday() + 1) % 7)
    if first_monday > last_sunday:
        return None
    return first_monday.isoformat(), last_sunday.isoformat()


# ----------------------------------------------------------------------
# VALIDATION
# ----------------------------------------------------------------------
def clean_sql(text: str) -> str:
    """Strips markdown fences and a trailing semicolon."""
    text = re.sub(r"^```(?:sql)?\s*|\s*```$", "", text.strip(), flags=re.IGNORECASE)
    return text.strip().rstrip(";").strip()


def validate_sql(sql: str) -> str:
    sql = clean_sql(sql)
    if not sql:
        raise UnsafeSQLError("empty query")
    if ";" in sql:
        raise UnsafeSQLError("multiple statements are not allowed")
    if not re.match(r"^(select|with)\b", sql, re.IGNORECASE):
        raise UnsafeSQLError("only SELECT queries are allowed")
    match = FORBIDDEN.search(sql)
    if match:
        raise UnsafeSQLError(f"forbidden keyword: {match.group(0)}")
    if INTERNAL_TABLES.search(sql):
        raise UnsafeSQLError("internal tables are not queryable")
    return sql


# ----------------------------------------------------------------------
# GENERATION
# ----------------------------------------------------------------------
SQL_PROMPT = """Write ONE PostgreSQL SELECT query.

Rules:
- Use only the tables and columns below.
- Return only the SQL, no explanation, no markdown.
- Give every computed column a clear alias.
- Round money and percentages to 2 decimals, always casting to numeric first:
  ROUND(x::numeric, 2). Postgres has no ROUND(double precision, integer), so
  ROUND(SUM(total_revenue), 2) fails; write ROUND(SUM(total_revenue)::numeric, 2).
- Region is on customers.region; join through foreign keys to filter by region.
- AVOID DOUBLE COUNTING: aggregate each fact table (orders, refunds,
  support_tickets, revenue) on its own, e.g. in its own CTE, before combining.
  Never join the revenue table to orders, refunds, or support_tickets: it is
  already a daily rollup, and joining it duplicates rows.
- For weekly trends ONLY, group with date_trunc('week', <date column>)::date AS week,
  filter to the COMPLETE WEEKS range in the schema so partial weeks don't show
  fake dips, and ORDER BY week. Never apply the COMPLETE WEEKS range to totals,
  monthly figures, or counts: those use all data unless the step names a period.
- When grouping by region and week, put region first in ORDER BY so each
  region's trend reads top to bottom.
- Do not filter by date unless the step asks for a period.
- Date ranges on timestamp columns must be half-open: col >= 'start' AND
  col < 'the day after end'. Never use <= with a date on a timestamp column:
  it silently drops everything after midnight on the last day.
- If the step asks for a total, compute the total in SQL (one row), not a
  breakdown the reader has to add up.
- Use absolute dates. Never select more than 200 rows; aggregate when possible.

SCHEMA:
{schema}

BUSINESS QUESTION: {question}
THIS STEP SHOULD COMPUTE: {action}"""


def generate_sql(question: str, action: str, previous_error=None):
    prompt = (SQL_PROMPT
              .replace("{schema}", get_schema_context())
              .replace("{question}", question)
              .replace("{action}", action))
    messages = [
        {"role": "system", "content": "You are a precise PostgreSQL analyst."},
        {"role": "user", "content": prompt},
    ]
    if previous_error:
        messages.append({"role": "user", "content":
                         f"Your previous query failed:\n{previous_error['sql']}\n"
                         f"Error: {previous_error['error']}\nReturn a corrected query."})
    text, usage = llm.chat(messages)
    return clean_sql(text), usage


# ----------------------------------------------------------------------
# EXECUTION
# ----------------------------------------------------------------------
def _to_json_value(v):
    if isinstance(v, decimal.Decimal):
        return float(v)
    if isinstance(v, (datetime.date, datetime.datetime)):
        return v.isoformat()
    return v


def execute_readonly(sql: str):
    conn = get_connection(with_vector=False, readonly=True)
    try:
        cur = conn.cursor()
        cur.execute(f"SET statement_timeout = {STATEMENT_TIMEOUT_MS}")
        cur.execute(sql)
        columns = [d.name for d in cur.description]
        rows = cur.fetchmany(MAX_ROWS + 1)
        truncated = len(rows) > MAX_ROWS
        rows = [[_to_json_value(v) for v in r] for r in rows[:MAX_ROWS]]
        return columns, rows, truncated
    finally:
        conn.rollback()
        conn.close()


def run_sql(question: str, action: str, evidence_id: str = "sql:1") -> dict:
    result = {"evidence_id": evidence_id, "action": action, "sql": None,
              "columns": [], "rows": [], "row_count": 0, "truncated": False,
              "error": None, "attempts": 0, "failed_attempts": [], "llm_usage": []}
    previous_error = None

    for attempt in range(1, MAX_ATTEMPTS + 1):
        result["attempts"] = attempt
        sql, usage = generate_sql(question, action, previous_error)
        result["llm_usage"].append(usage)
        result["sql"] = sql
        try:
            safe_sql = validate_sql(sql)
        except UnsafeSQLError as e:
            # unsafe output is never retried into execution
            result["error"] = f"blocked: {e}"
            return result
        try:
            columns, rows, truncated = execute_readonly(safe_sql)
            result.update(columns=columns, rows=rows, row_count=len(rows),
                          truncated=truncated, error=None)
            return result
        except Exception as e:  # database error -> let the LLM self-correct once
            result["error"] = str(e).strip()
            previous_error = {"sql": safe_sql, "error": result["error"]}
            result["failed_attempts"].append(previous_error)

    return result
