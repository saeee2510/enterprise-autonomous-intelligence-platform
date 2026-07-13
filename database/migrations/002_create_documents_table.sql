CREATE EXTENSION IF NOT EXISTS vector;


CREATE TABLE IF NOT EXISTS documents (

    id UUID PRIMARY KEY,

    content TEXT NOT NULL,

    embedding VECTOR(1536),

    source TEXT,

    department TEXT,

    entity TEXT,

    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP

);