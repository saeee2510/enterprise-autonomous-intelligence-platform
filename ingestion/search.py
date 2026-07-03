import os
import json
import psycopg2
import numpy as np
from dotenv import load_dotenv
from openai import OpenAI
from pgvector.psycopg2 import register_vector

from core.planner import route_query
from core.fusion_agent import fuse_results

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

    rows = cur.fetchall()
    return rows, q_emb


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
# SQL TOOL
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
# LLM
# -----------------------------
def generate_answer(query, fused_context):

    prompt = f"""
You are an Enterprise AI Analyst.

Use ONLY the provided evidence.

CONTEXT:
{fused_context}

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

    plan = route_query(query)

    print("\n--- PLAN ---")
    print(plan)

    sql_result = None
    docs_text = ""

    for step in plan["steps"]:

        if step["tool"] == "sql":
            sql_result = run_sql(query)

        elif step["tool"] == "retrieval":
            docs, q_emb = retrieve_candidates(query)
            docs_text = build_context(docs)

    fused = fuse_results(query, sql_result, docs_text)

    print("\n--- FUSED EVIDENCE GRAPH ---\n")
    print(json.dumps(fused, indent=2))

    answer = generate_answer(query, json.dumps(fused, indent=2))

    print("\nAI ANSWER\n")
    print(answer)


# -----------------------------
# CLI
# -----------------------------
if __name__ == "__main__":
    q = input("Ask EAIP: ")
    ask(q)