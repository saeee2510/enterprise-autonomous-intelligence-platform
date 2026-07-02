import psycopg2
from openai import OpenAI
import os
from dotenv import load_dotenv

load_dotenv()

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

conn = psycopg2.connect(
    dbname="eaip",
    user="saee2510",
    host="localhost",
    port=5432
)

cur = conn.cursor()


# -----------------------------
# SCHEMA INTROSPECTION
# -----------------------------
def get_schema():
    cur.execute("""
        SELECT table_name, column_name
        FROM information_schema.columns
        WHERE table_schema = 'public'
        ORDER BY table_name;
    """)
    rows = cur.fetchall()

    schema = {}
    for table, col in rows:
        schema.setdefault(table, []).append(col)

    return schema


# -----------------------------
# SAFETY CHECK
# -----------------------------
def validate_sql(sql: str):
    banned = ["delete", "drop", "update", "insert", "alter"]

    sql_lower = sql.lower()

    for b in banned:
        if b in sql_lower:
            raise Exception(f"Unsafe SQL detected: {b}")

    if not sql_lower.strip().startswith("select"):
        raise Exception("Only SELECT queries allowed")

    return True


# -----------------------------
# SQL GENERATION
# -----------------------------
def generate_sql(question: str, action: str):

    schema = get_schema()

    prompt = f"""
You are an expert SQL generator for Postgres.

Rules:
- ONLY generate SELECT queries
- Use only provided schema
- No explanations
- No markdown

Schema:
{schema}

User Question:
{question}

Task:
{action}

Return ONLY SQL.
"""

    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": "You are a precise SQL engine."},
            {"role": "user", "content": prompt}
        ],
        temperature=0
    )

    return response.choices[0].message.content.strip()


# -----------------------------
# EXECUTION
# -----------------------------
def run_sql(query: str, action: str):

    sql = generate_sql(query, action)

    validate_sql(sql)

    cur.execute(sql)
    result = cur.fetchall()

    return {
        "sql": sql,
        "result": result
    }


# -----------------------------
# ENTRY POINT FOR PLANNER
# -----------------------------
def execute_sql_plan(plan: dict):

    results = []

    for step in plan["steps"]:
        if step["tool"] == "sql":
            out = run_sql(plan["query"], step["action"])
            results.append(out)

    return results