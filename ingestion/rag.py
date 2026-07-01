import os
import psycopg2
from dotenv import load_dotenv
from openai import OpenAI
from pgvector.psycopg2 import register_vector

# -----------------------------
# ENV + CLIENT SETUP
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
# RETRIEVE (VECTOR SEARCH)
# -----------------------------
def retrieve(query, top_k=5):
    embedding = get_embedding(query)

    cur.execute(
        """
        SELECT content, source, department
        FROM documents
        ORDER BY embedding <-> %s::vector
        LIMIT %s;
        """,
        (embedding, top_k)
    )

    rows = cur.fetchall()

    # 🔍 DEBUG: show what retrieval is actually returning
    print("\n--- DEBUG: Retrieved Documents ---")
    for i, r in enumerate(rows, 1):
        print(f"\nDoc {i}")
        print("Source:", r[1])
        print("Dept:", r[2])
        print("Content:", r[0][:200])

    return rows


# -----------------------------
# BUILD CONTEXT
# -----------------------------
def build_context(rows):
    if not rows:
        return ""

    context = ""

    for i, (content, source, dept) in enumerate(rows, 1):
        context += f"""
DOCUMENT {i}
SOURCE: {source}
DEPARTMENT: {dept}

CONTENT:
{content}

-------------------------
"""

    return context


# -----------------------------
# GENERATE ANSWER (GPT)
# -----------------------------
def generate_answer(query, context):

    if not context.strip():
        return "No relevant context found in database."

    prompt = f"""
You are an Enterprise AI Operations Analyst.

Answer using ONLY the retrieved documents.

Return your answer in plain text only.

Do NOT use markdown formatting.
Do NOT use asterisks, bold text, or special symbols.

Structure your response exactly like this:

Main Issue:
...

Evidence:
- ...
- ...
- ...

Recommended Actions:
- ...
- ...
- ...

If the documents are insufficient, say so clearly.

DOCUMENTS:
{context}

QUESTION:
{query}
"""

    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": "You are a helpful enterprise AI assistant."},
            {"role": "user", "content": prompt}
        ]
    )

    return response.choices[0].message.content


# -----------------------------
# PIPELINE
# -----------------------------
def ask(query: str):
    docs = retrieve(query)
    context = build_context(docs)

    answer = generate_answer(query, context)

    print("\n AI ANSWER\n")
    print(answer)


# -----------------------------
# CLI
# -----------------------------
if __name__ == "__main__":
    query = input("Ask EAIP: ")
    ask(query)