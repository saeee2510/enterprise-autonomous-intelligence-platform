import uuid
import psycopg2

from ingestion.document_loader import load_documents
from ingestion.chunker import chunk_documents
from ingestion.embedder import create_embedding

conn = psycopg2.connect(
    dbname="eaip",
    user="postgres",
    password="YOUR_PASSWORD",
    host="127.0.0.1",
)

cur = conn.cursor()

docs = load_documents("documents")

chunks = chunk_documents(docs)

for chunk in chunks:
    embedding = create_embedding(chunk["content"])

    cur.execute(
        """
        INSERT INTO documents
        (id, content, embedding, source, department, timestamp)
        VALUES (%s,%s,%s,%s,%s,NOW())
        """,
        (
            str(uuid.uuid4()),
            chunk["content"],
            embedding,
            chunk["source"],
            "engineering",
        ),
    )

conn.commit()