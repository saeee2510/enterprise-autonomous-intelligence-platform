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
# TOOLS (future agent upgrade)
# -----------------------------
TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "run_sql",
            "description": "Run SQL aggregation queries on support tickets",
            "parameters": {
                "type": "object",
                "properties": {
                    "query_type": {"type": "string"}
                }
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "vector_search",
            "description": "Semantic search over enterprise documents",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string"}
                },
                "required": ["query"]
            }
        }
    }
]

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
# VECTOR SEARCH
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
# SQL CONTEXT
# -----------------------------
def get_sql_context():
    cur.execute("""
        SELECT category, COUNT(*)
        FROM support_tickets
        GROUP BY category
    """)

    rows = cur.fetchall()

    text = "Ticket volume by category:\n"
    for r in rows:
        text += f"- {r[0]}: {r[1]}\n"

    return text


# -----------------------------
# ROUTER
# -----------------------------
def route_query(query):
    q = query.lower()

    if "how many" in q or "count" in q:
        return "sql"
    return "hybrid"


# -----------------------------
# GPT ANSWER GENERATION
# -----------------------------
def generate_answer(query, context):

    if not context.strip():
        return "No relevant context found in database."

    prompt = f"""
You are an Enterprise AI Operations Analyst.

Answer ONLY using the provided context.

Do NOT use markdown, bold text, or special characters.

Structure:

Main Issue:
...

Evidence:
- ...
- ...

Recommended Actions:
- ...
- ...

CONTEXT:
{context}

QUESTION:
{query}
"""

    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": "You are a precise enterprise AI analyst."},
            {"role": "user", "content": prompt}
        ]
    )

    return response.choices[0].message.content


# -----------------------------
# MAIN PIPELINE
# -----------------------------
def ask(query: str):

    mode = route_query(query)

    if mode == "sql":
        context = get_sql_context()

    else:
        vector_docs = retrieve(query)
        vector_context = build_context(vector_docs)

        sql_context = get_sql_context()

        context = f"""
[STRUCTURED DATA]
{sql_context}

[UNSTRUCTURED DATA]
{vector_context}
"""

    answer = generate_answer(query, context)

    print("\nAI ANSWER\n")
    print(answer)
    print("MODE:", mode)


# -----------------------------
# CLI ENTRY
# -----------------------------
if __name__ == "__main__":
    query = input("Ask EAIP: ")
    ask(query)