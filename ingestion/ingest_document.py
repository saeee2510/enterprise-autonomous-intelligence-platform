"""
Loads every .txt document under ingestion/documents, chunks it, creates
real OpenAI embeddings, and stores the chunks in the pgvector documents table.

Run from the project root:
    python -m ingestion.ingest_document
"""
import uuid
from pathlib import Path

from core.db import get_connection
from core.llm import embed
from ingestion.chunking.text_splitter import split_document
from ingestion.loaders.txt_loader import load_text_file

DOCS_DIR = Path("ingestion/documents")

INDEXES = [
    "CREATE INDEX IF NOT EXISTS documents_embedding_hnsw "
    "ON documents USING hnsw (embedding vector_cosine_ops)",
    "CREATE INDEX IF NOT EXISTS documents_content_fts "
    "ON documents USING gin (to_tsvector('english', content))",
]


def ingest():
    chunks = []
    for path in sorted(DOCS_DIR.rglob("*.txt")):
        chunks.extend(split_document(load_text_file(str(path))))

    if not chunks:
        raise SystemExit(f"No .txt documents found under {DOCS_DIR}")

    embeddings, _ = embed([c["content"] for c in chunks])

    conn = get_connection()
    cur = conn.cursor()
    cur.execute("TRUNCATE documents;")  # re-ingest from scratch each run

    for chunk, emb in zip(chunks, embeddings):
        cur.execute(
            """
            INSERT INTO documents (id, content, embedding, source, department, entity, created_at)
            VALUES (%s, %s, %s, %s, %s, %s, NOW())
            """,
            (str(uuid.uuid4()), chunk["content"], emb,
             chunk["source"], chunk["department"], chunk["entity"]),
        )

    for statement in INDEXES:
        cur.execute(statement)

    conn.commit()
    cur.close()
    conn.close()
    print(f"Ingested {len(chunks)} chunks from {DOCS_DIR}")


if __name__ == "__main__":
    ingest()
