import os
import psycopg2
from dotenv import load_dotenv
from openai import OpenAI

DEBUG = False

load_dotenv()

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

conn = psycopg2.connect(
    dbname="eaip",
    user="saee2510",
    host="localhost",
    port=5432
)

cur = conn.cursor()


# =============================
# EMBEDDINGS
# =============================
def get_embedding(text: str):
    response = client.embeddings.create(
        model="text-embedding-3-small",
        input=text
    )
    return response.data[0].embedding


# =============================
# INTENT CLASSIFICATION
# =============================
def classify_doc(text):
    t = text.lower()

    if "duplicate charge" in t:
        return "billing_error"

    if "refund not received" in t or "refund" in t:
        return "refund_issue"

    if "release notes" in t or "improved" in t:
        return "engineering"

    if "email" in t:
        return "customer_email"

    return "other"


def query_intent(query):
    q = query.lower()

    if "duplicate" in q and "charge" in q:
        return "billing_error"

    if "refund" in q:
        return "refund_issue"

    if "escalation" in q:
        return "support_priority"

    return "general"


# =============================
# HYBRID SCORING
# =============================
def hybrid_score(text, query):
    text_l = text.lower()

    q_intent = query_intent(query)
    d_intent = classify_doc(text)

    score = 0

    # INTENT MATCH (most important)
    if q_intent == d_intent:
        score += 10

    # exact phrase match
    if query.lower() in text_l:
        score += 8

    # keyword overlap
    for w in query.lower().split():
        if w in text_l:
            score += 1

    return score


# =============================
# VECTOR SEARCH
# =============================
def search_documents(query, top_k=5):
    embedding = get_embedding(query)

    cur.execute(
        """
        SELECT content, source, department
        FROM documents
        ORDER BY embedding <-> %s::vector
        LIMIT 20;
        """,
        (embedding,)
    )

    rows = cur.fetchall()

    # -----------------------------
    # DEBUG 
    # -----------------------------
    if DEBUG:
        print("\n🔍 TOP RESULTS (RAW VECTOR)\n")

    if DEBUG:
        for i, (content, source, department) in enumerate(rows, 1):
            print(f"\nRaw {i}")
            print("-" * 40)
            print("Source:", source)
            print("Dept:", department)
            print("Content:", content[:200])

    # -----------------------------
    # RERANKING
    # -----------------------------
    scored = []
    for r in rows:
        score = hybrid_score(r[0], query)
        scored.append((score, r))

    scored.sort(reverse=True, key=lambda x: x[0])

    ranked_rows = [r for _, r in scored]

    # -----------------------------
    # FINAL OUTPUT
    # -----------------------------
    if DEBUG:
        print("\nTOP RESULTS (DIRECT VECTOR)\n")
    

    for i, (content, source, department) in enumerate(ranked_rows[:top_k], 1):
        print(f"\nResult {i}")
        print("-" * 40)
        print("Source:", source)
        print("Department:", department)
        print("Content:", content[:250])


# =============================
# OPTIONAL TEST
# =============================
def test_query_search():
    query = "refund not received"

    embedding = get_embedding(query)

    cur.execute("""
        SELECT content
        FROM documents
        ORDER BY embedding <-> %s::vector
        LIMIT 3;
    """, (embedding,))

    rows = cur.fetchall()

    print("\nTOP RESULTS (DIRECT VECTOR)\n")
    for i, r in enumerate(rows, 1):
        print(f"{i}. {r[0][:200]}\n")


# =============================
# RUN
# =============================
if __name__ == "__main__":
    q = input("Enter query: ")
    search_documents(q)

    # optional debug run
    test_query_search()