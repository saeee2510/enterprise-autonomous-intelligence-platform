import os
import psycopg2
from dotenv import load_dotenv
from openai import OpenAI

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
# embedding
# -----------------------------
def get_embedding(text: str):
    response = client.embeddings.create(
        model="text-embedding-3-small",
        input=text
    )
    return response.data[0].embedding


# -----------------------------
# search
# -----------------------------
def search_documents(query, top_k=5):
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

    print("\n🔍 TOP RESULTS\n")

    for i, (content, source, department) in enumerate(rows, 1):
        print(f"\nResult {i}")
        print("-" * 40)
        print("Source:", source)
        print("Department:", department)
        print("Content:", content[:250])


# -----------------------------
# run
# -----------------------------
if __name__ == "__main__":
    q = input("Enter query: ")
    search_documents(q)