import os
import psycopg2
import numpy as np
from dotenv import load_dotenv
from openai import OpenAI
from pgvector.psycopg2 import register_vector
from core.router import route_query
from core.planner import route_query
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

DEBUG = False


# -----------------------------
# EMBEDDINGS
# -----------------------------
def get_embedding(text: str):
    response = client.embeddings.create(
        model="text-embedding-3-small",
        input=text
    )
    return response.data[0].embedding


# -----------------------------
# DEDUP
# -----------------------------
def deduplicate_docs(rows):
    seen = set()
    unique = []

    for r in rows:
        key = r[0][:150].strip().lower()
        if key not in seen:
            seen.add(key)
            unique.append(r)

    return unique


# -----------------------------
# HYBRID SCORE
# -----------------------------
def hybrid_score(text, query):
    text_l = text.lower()
    query_l = query.lower()

    score = 0.0

    if query_l in text_l:
        score += 10

    weights = {
        "refund": 3,
        "duplicate": 5,
        "charge": 3,
        "escalated": 4,
        "delay": 3,
        "not received": 5,
        "billing": 2
    }

    for term, w in weights.items():
        if term in text_l:
            score += w

    score += len(set(query_l.split()) & set(text_l.split())) * 1.5

    return score


# -----------------------------
# RETRIEVAL
# -----------------------------
def retrieve_candidates(query, top_k=10):
    embedding = get_embedding(query)

    cur.execute(
        """
        SELECT content, source, department, embedding
        FROM documents
        ORDER BY embedding <-> %s::vector
        LIMIT %s;
        """,
        (embedding, top_k * 3)
    )

    rows = cur.fetchall()
    rows = deduplicate_docs(rows)

    return rows, embedding


# -----------------------------
# COSINE SIM
# -----------------------------
def cosine_sim(a, b):
    a = np.array(a)
    b = np.array(b)
    return float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b)))


# -----------------------------
# MMR RERANK
# -----------------------------
def mmr_rerank(query, query_embedding, docs, lambda_=0.7, k=5):
    selected = []
    candidates = docs.copy()

    doc_emb_map = {d[0]: d[3] for d in docs}

    for _ in range(min(k, len(candidates))):

        best_doc = None
        best_score = -1

        for doc in candidates:
            if doc in selected:
                continue

            relevance = hybrid_score(doc[0], query)

            if not selected:
                diversity = 0
            else:
                diversity = max(
                    cosine_sim(query_embedding, doc_emb_map[s[0]])
                    for s in selected
                )

            score = lambda_ * relevance - (1 - lambda_) * diversity

            if score > best_score:
                best_score = score
                best_doc = doc

        if best_doc:
            selected.append(best_doc)

    return selected


# -----------------------------
# CONTEXT BUILDER
# -----------------------------
def build_context(rows):
    if not rows:
        return ""

    return "\n".join([
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
# SQL TOOL (STRUCTURED OUTPUT ONLY)
# -----------------------------
def run_sql(query: str = None):

    q = (query or "").lower()

    # specific metric path
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

    # fallback aggregation
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
# TOOL EXECUTION (SINGLE SOURCE OF TRUTH)
# -----------------------------
def execute_tools(query, route):

    docs, q_emb = retrieve_candidates(query)
    reranked = mmr_rerank(query, q_emb, docs)

    context = {
        "unstructured": build_context(reranked),
        "structured": None
    }

    if route == "sql":
        context["structured"] = run_sql(query)

    elif route == "hybrid":
        context["structured"] = run_sql(query)

    return context


# -----------------------------
# LLM
# -----------------------------
def generate_answer(query, context):

    prompt = f"""
You are an Enterprise AI Analyst.

RULES:
- Structured data is ground truth
- Do NOT infer numbers
- Use only provided context

CONTEXT:
{context}

QUESTION:
{query}

FORMAT:
Main Issue
Evidence
Recommendations
"""

    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": "Precise enterprise analyst. No hallucination."},
            {"role": "user", "content": prompt}
        ]
    )

    return response.choices[0].message.content


# -----------------------------
# MAIN
# -----------------------------
def ask(query: str):

    plan = route_query(query)

    print("\n--- PLAN ---")
    print(plan)

    context_parts = []

    for step in plan["steps"]:

        if step["tool"] == "sql":
            context_parts.append(run_sql(query))

        elif step["tool"] == "retrieval":
            docs, _ = retrieve_candidates(query)
            context_parts.append(build_context(docs))

    context = "\n\n".join(context_parts)

    answer = generate_answer(query, context)

    print("\nAI ANSWER\n")
    print(answer)


# -----------------------------
# CLI
# -----------------------------
if __name__ == "__main__":
    query = input("Ask EAIP: ")
    ask(query)