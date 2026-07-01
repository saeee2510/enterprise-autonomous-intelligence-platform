import psycopg2
import uuid
from datetime import datetime
from faker import Faker

from dotenv import load_dotenv
import os

load_dotenv()

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

fake = Faker()

conn = psycopg2.connect(
    dbname="eaip",
    user="saee2510",
    host="localhost",
    port=5432
)

cur = conn.cursor()


# -----------------------------
# STEP 1: Generate fake documents
# -----------------------------
def generate_documents(n=50):
    docs = []

    for _ in range(n):
        doc_type = fake.random_element(
            elements=["email", "support", "release_notes"]
        )

        if doc_type == "email":
            text = f"""
            Customer email: {fake.sentence()}
            Issue: {fake.paragraph()}
            """
            source = "email_system"
            dept = "customer_success"

        elif doc_type == "support":
            text = f"""
            Support ticket:
            {fake.paragraph()}
            Resolution notes:
            {fake.paragraph()}
            """
            source = "support_system"
            dept = "support"

        else:
            text = f"""
            Release Notes:
            {fake.paragraph()}
            Bug fixes and improvements included.
            """
            source = "engineering"
            dept = "product"

        docs.append((str(uuid.uuid4()), text, source, dept))

    return docs


# -----------------------------
# STEP 2: Embed placeholder 
# -----------------------------
def fake_embedding(text):
    """
    TEMPORARY:
    We will replace this with OpenAI embeddings next step.
    """
    import random
    return [random.random() for _ in range(1536)]


# -----------------------------
# STEP 3: Insert into Postgres
# -----------------------------
def insert_documents():
    docs = generate_documents()

    for doc_id, content, source, dept in docs:
        embedding = fake_embedding(content)

        cur.execute(
            """
            INSERT INTO documents (id, content, embedding, source, department, created_at)
            VALUES (%s, %s, %s, %s, %s, %s)
            """,
            (
                doc_id,
                content,
                embedding,
                source,
                dept,
                datetime.utcnow()
            )
        )

    conn.commit()
    print(f"Inserted {len(docs)} documents")


# -----------------------------
# RUN
# -----------------------------
if __name__ == "__main__":
    insert_documents()
    cur.close()
    conn.close()
    print("Document pipeline completed")