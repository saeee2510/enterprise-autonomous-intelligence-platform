from ingestion.search import retrieve_candidates, mmr_rerank, build_context
from ingestion.search import get_embedding, run_sql
from openai import OpenAI
import os
from dotenv import load_dotenv

# -----------------------------
# ENV + CLIENT
# -----------------------------
load_dotenv()

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))


# -----------------------------
# GENERATE ANSWER
# -----------------------------
def generate_answer(query, context):

    if not context.strip():
        return "No relevant context found in database."

    prompt = f"""
You are an Enterprise AI Operations Analyst.

Answer ONLY using the provided context.

Structure your response:

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
# MAIN RAG PIPELINE
# -----------------------------
def ask(query: str):

    # 1. Retrieve candidates
    docs, query_embedding = retrieve_candidates(query)

    # 2. Rerank using MMR
    reranked_docs = mmr_rerank(query, query_embedding, docs)

    # 3. Build context
    vector_context = build_context(reranked_docs)

    # 4. Optional SQL context
    sql_context = ""

    if any(x in query.lower() for x in ["how many", "count", "trend", "volume"]):
        sql_context = run_sql()

    # 5. Merge context
    context = f"""
[UNSTRUCTURED DATA]
{vector_context}

[STRUCTURED DATA]
{sql_context}
"""

    # 6. Generate answer
    answer = generate_answer(query, context)

    print("\nAI ANSWER\n")
    print(answer)


# -----------------------------
# CLI
# -----------------------------
if __name__ == "__main__":
    query = input("Ask EAIP: ")
    ask(query)