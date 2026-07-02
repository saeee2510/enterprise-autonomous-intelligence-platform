import os
import psycopg2
import numpy as np
from dotenv import load_dotenv
from openai import OpenAI
from pgvector.psycopg2 import register_vector

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
# DEDUPLICATION
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
# EMBEDDINGS
# -----------------------------
def get_embedding(text: str):
    response = client.embeddings.create(
        model="text-embedding-3-small",
        input=text
    )
    return response.data[0].embedding


# -----------------------------
# HYBRID SCORE
# -----------------------------
def hybrid_score(text, query):
    text_l = text.lower()
    query_l = query.lower()

    score = 0.0

    if query_l in text_l:
        score += 10

    strong_terms = {
        "refund": 3,
        "duplicate": 5,
        "charge": 3,
        "escalated": 4,
        "delay": 3,
        "not received": 5,
        "billing": 2
    }

    for term, weight in strong_terms.items():
        if term in text_l:
            score += weight

    overlap = len(set(query_l.split()) & set(text_l.split()))
    score += overlap * 1.5

    return score


# -----------------------------
# VECTOR RETRIEVAL (FIXED)
# -----------------------------
def retrieve_candidates(query, top_k=10):
    query_embedding = get_embedding(query)

    cur.execute(
        """
        SELECT content, source, department, embedding
        FROM documents
        ORDER BY embedding <-> %s::vector
        LIMIT %s;
        """,
        (query_embedding, top_k * 3)
    )

    rows = cur.fetchall()

    if DEBUG:
        print("\n--- RAW RESULTS ---")
        for r in rows:
            print(r[1], r[2], r[0][:80])

    rows = deduplicate_docs(rows)

    return rows, query_embedding


# -----------------------------
# MMR RERANKING (FIXED)
# -----------------------------
def cosine_sim(a, b):
    a = np.array(a)
    b = np.array(b)
    return float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b)))


def mmr_rerank(query, query_embedding, docs, lambda_=0.7, k=5):
    selected = []
    candidates = docs.copy()

    doc_embeddings = {
        d[0]: d[3] for d in docs  # content -> embedding
    }

    for _ in range(min(k, len(candidates))):
        best_doc = None
        best_score = -1

        for doc in candidates:
            if doc in selected:
                continue

            content = doc[0]

            relevance = hybrid_score(content, query)

            if not selected:
                diversity = 0
            else:
                diversity = max(
                    cosine_sim(query_embedding, doc_embeddings[s[0]])
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
def run_sql():
    cur.execute("""
        SELECT category, COUNT(*)
        FROM support_tickets
        GROUP BY category
    """)

    rows = cur.fetchall()
    return "\n".join([f"{r[0]}: {r[1]}" for r in rows])


# -----------------------------
# PIPELINE
# -----------------------------
def execute_tools(query):
    docs, query_embedding = retrieve_candidates(query)

    reranked = mmr_rerank(query, query_embedding, docs)

    context = []
    context.append("[UNSTRUCTURED]")
    context.append(build_context(reranked))

    if any(x in query.lower() for x in ["how many", "count", "trend", "volume"]):
        context.append("\n[STRUCTURED]")
        context.append(run_sql())

    return "\n".join(context)


# -----------------------------
# GPT GENERATION
# -----------------------------
def generate_answer(query, context):

    prompt = f"""
You are an Enterprise AI Analyst.

Use ONLY the provided context.

Main Issue:
...

Evidence:
...

Recommended Actions:
...

CONTEXT:
{context}

QUESTION:
{query}
"""

    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": "You are a precise enterprise analyst."},
            {"role": "user", "content": prompt}
        ]
    )

    return response.choices[0].message.content


# -----------------------------
# MAIN
# -----------------------------
def ask(query: str):
    context = execute_tools(query)
    answer = generate_answer(query, context)

    print("\nAI ANSWER\n")
    print(answer)


# -----------------------------
# CLI
# -----------------------------
if __name__ == "__main__":
    query = input("Ask EAIP: ")
    ask(query)