import os
import json
import psycopg2
from dotenv import load_dotenv
from openai import OpenAI
from pgvector.psycopg2 import register_vector

from core.planner import route_query
from core.fusion_agent import fuse_results
from core.verification_agent import verify
from core.report_generator import generate_report

# -----------------------------
# ENV + CLIENT
# -----------------------------
load_dotenv()

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

conn = psycopg2.connect(
    dbname="eaip",
    user="saee2510",
    host="localhost",
    port=5432
)

register_vector(conn)
cur = conn.cursor()


# -----------------------------
# EMBEDDINGS
# -----------------------------
def get_embedding(text: str):
    res = client.embeddings.create(
        model="text-embedding-3-small",
        input=text
    )
    return res.data[0].embedding


# -----------------------------
# RETRIEVAL
# -----------------------------
def retrieve_candidates(query, top_k=10):
    q_emb = get_embedding(query)

    cur.execute("""
        SELECT content, source, department, embedding
        FROM documents
        ORDER BY embedding <-> %s::vector
        LIMIT %s;
    """, (q_emb, top_k * 3))

    return cur.fetchall(), q_emb


def build_context(rows):
    if not rows:
        return ""

    return "\n\n".join([
        f"""
DOCUMENT {i+1}
SOURCE: {r[1]}
DEPARTMENT: {r[2]}

CONTENT:
{r[0]}
"""
        for i, r in enumerate(rows)
    ])


# -----------------------------
# SQL LAYER
# -----------------------------
def run_sql(query: str):
    q = query.lower()

    if "refund" in q and ("how many" in q or "count" in q):
        cur.execute("""
            SELECT COUNT(*)
            FROM support_tickets
            WHERE category ILIKE '%refund%'
        """)
        return {
            "type": "metric",
            "name": "refund_tickets",
            "value": cur.fetchone()[0],
            "unit": "tickets"
        }

    cur.execute("""
        SELECT category, COUNT(*)
        FROM support_tickets
        GROUP BY category
    """)

    return {
        "type": "category_distribution",
        "data": {r[0]: r[1] for r in cur.fetchall()}
    }


# -----------------------------
# LLM ANSWER
# -----------------------------
def generate_answer(query, context):
    prompt = f"""
You are an Enterprise AI Analyst.

Use ONLY provided evidence.

CONTEXT:
{context}

QUESTION:
{query}

FORMAT:
Main Issue
Evidence
Recommendations
"""

    res = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": "Precise enterprise analyst."},
            {"role": "user", "content": prompt}
        ]
    )

    return res.choices[0].message.content


# -----------------------------
# MAIN PIPELINE
# -----------------------------
def ask(query: str):

    # -----------------------------
    # 1. PLAN
    # -----------------------------
    plan = route_query(query)

    print("\n--- PLAN ---")
    print(json.dumps(plan, indent=2))

    sql_result = None
    docs_text = ""

    steps = plan.get("steps", [])
    if not steps:
        steps = [{"tool": "hybrid"}]

    # -----------------------------
    # 2. EXECUTION
    # -----------------------------
    for step in steps:

        tool = step.get("tool")

        if tool == "sql":
            sql_result = run_sql(query)

        elif tool == "retrieval":
            docs, _ = retrieve_candidates(query)
            docs_text = build_context(docs)

        elif tool == "hybrid":
            sql_result = run_sql(query)
            docs, _ = retrieve_candidates(query)
            docs_text = build_context(docs)

    # -----------------------------
    # 3. FUSION
    # -----------------------------
    fused = fuse_results(query, sql_result, docs_text)

    print("\n--- FUSED EVIDENCE GRAPH ---")
    print(json.dumps(fused, indent=2))

    # -----------------------------
    # 4. VERIFICATION
    # -----------------------------
    verified = verify(fused, sql_result, docs_text)

    print("\n--- VERIFIED EVIDENCE GRAPH ---")
    print(json.dumps(verified, indent=2))

    # -----------------------------
    # 5. ANSWER
    # -----------------------------
    answer = generate_answer(
        query,
        json.dumps(verified, indent=2)
    )

    print("\n--- AI ANSWER ---")
    print(answer)

    # -----------------------------
    # 6. REPORT
    # -----------------------------
    report = generate_report(query, fused, verified)

    print("\n--- FINAL REPORT ---")
    print(json.dumps(report, indent=2))

    # -----------------------------
    # 7. RETURN EVERYTHING
    # -----------------------------
    return {
        "answer": answer,
        "report": report,
        "verified": verified,
        "fused": fused,
        "sql": sql_result,
        "docs": docs_text,
        "trace": plan
    }

# -----------------------------
# CLI
# -----------------------------
if __name__ == "__main__":
    q = input("Ask EAIP: ")
    ask(q)