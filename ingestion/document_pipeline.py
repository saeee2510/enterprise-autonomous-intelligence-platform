import os
import uuid
from datetime import datetime

import psycopg2
from dotenv import load_dotenv
from faker import Faker
from openai import OpenAI

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
def generate_documents():
    docs = []

    refund_docs = [
        (
            """
Customer complaint:
Refund not received after order cancellation.

Details:
Customer has waited 14 days for the refund.
Order status shows refunded, but the bank account has not been credited.

Resolution:
Escalated to billing operations.
""",
            "support_system",
            "support"
        ),
        (
            """
Customer complaint:
Duplicate charge detected.

Details:
Customer was charged twice for the same purchase.
Refund request submitted immediately.

Resolution:
Finance team investigating duplicate transaction.
""",
            "support_system",
            "support"
        ),
        (
            """
Customer email:

I cancelled my order last week but still haven't received my refund.
Please help resolve this issue.

Resolution:
Pending review.
""",
            "email_system",
            "customer_success"
        ),
        (
            """
Release Notes

Refund processing latency reduced by 40%.

Improved billing reconciliation and duplicate payment detection.
""",
            "engineering",
            "product"
        ),
    ]

    # Create 50 docs by repeating templates
    for i in range(50):
        content, source, dept = refund_docs[i % len(refund_docs)]

        docs.append((
            str(uuid.uuid4()),
            content,
            source,
            dept
        ))

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