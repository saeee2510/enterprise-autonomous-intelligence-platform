import os
import psycopg2
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
# HYBRID RERANKING 
# -----------------------------
def hybrid_score(text, query):
    text_l = text.lower()
    query_l = query.lower()

    score = 0

    # -------------------------
    # 1. EXACT PHRASE MATCH BOOST
    # -------------------------
    if query_l in text_l:
        score += 10

    # -------------------------
    # 2. STRONG DOMAIN INTENT BOOST
    # -------------------------
    strong_terms = {
        "duplicate charge": 8,
        "refund": 4,
        "escalation": 3,
        "not received": 5,
        "billing": 3,
        "escalated": 3
    }

    for term, weight in strong_terms.items():
        if term in text_l and term in query_l:
            score += weight

    # -------------------------
    # 3. TOKEN OVERLAP
    # -------------------------
    query_words = query_l.split()

    for w in query_words:
        if w in text_l:
            score += 1

    return score


# -----------------------------
# VECTOR RETRIEVAL
# -----------------------------
def retrieve(query, top_k=8):
    embedding = get_embedding(query)

    cur.execute(
        """
        SELECT content, source, department
        FROM documents
        ORDER BY embedding <-> %s::vector
        LIMIT %s;
        """,
        (embedding, top_k * 2)
    )

    rows = cur.fetchall()

    print("\n--- DEBUG: Retrieved Documents ---")
    for i, r in enumerate(rows, 1):
        print(f"\nDoc {i}")
        print("Source:", r[1])
        print("Dept:", r[2])
        print("Content:", r[0][:200])

    # -----------------------------
    # RERANK STEP (NEW)
    # -----------------------------
    ranked = sorted(
        rows,
        key=lambda r: hybrid_score(r[0], query),
        reverse=True
    )

    return ranked[:top_k]


# -----------------------------
# CONTEXT BUILDER
# -----------------------------
def build_context(rows):
    if not rows:
        return ""

    return "\n\n".join([
        f"""DOCUMENT {i+1}
SOURCE: {r[1]}
DEPARTMENT: {r[2]}
CONTENT:
{r[0]}"""
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
# TOOL EXECUTOR (HYBRID ROUTING)
# -----------------------------
def execute_tools(query):
    context_parts = []

    # ALWAYS vector search
    vector_docs = retrieve(query)
    context_parts.append("[UNSTRUCTURED]")
    context_parts.append(build_context(vector_docs))

    # CONDITIONAL SQL
    if any(x in query.lower() for x in ["how many", "count", "trend", "volume"]):
        context_parts.append("\n[STRUCTURED]")
        context_parts.append(run_sql())

    return "\n".join(context_parts)


# -----------------------------
# LLM ANSWER GENERATION
# -----------------------------
def generate_answer(query, context):

    if not context.strip():
        return "No relevant context found."

    prompt = f"""
You are an Enterprise AI Analyst.

Use ONLY the provided context.

Structure:

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
# MAIN PIPELINE
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