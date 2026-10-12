-- =========================
-- ENABLE VECTOR EXTENSION
-- =========================
CREATE EXTENSION IF NOT EXISTS vector;

-- =========================
-- STRUCTURED BUSINESS DATA
-- =========================

CREATE TABLE IF NOT EXISTS customers (
    id SERIAL PRIMARY KEY,
    name TEXT,
    region TEXT,
    signup_date TIMESTAMP
);

CREATE TABLE IF NOT EXISTS products (
    id SERIAL PRIMARY KEY,
    name TEXT,
    category TEXT,
    price FLOAT
);

CREATE TABLE IF NOT EXISTS orders (
    id SERIAL PRIMARY KEY,
    customer_id INT REFERENCES customers(id),
    product_id INT REFERENCES products(id),
    quantity INT,
    revenue FLOAT,
    order_date TIMESTAMP
);

CREATE TABLE IF NOT EXISTS refunds (
    id SERIAL PRIMARY KEY,
    order_id INT REFERENCES orders(id),
    amount FLOAT,
    reason TEXT,
    created_at TIMESTAMP
);

CREATE TABLE IF NOT EXISTS support_tickets (
    id SERIAL PRIMARY KEY,
    customer_id INT REFERENCES customers(id),
    severity TEXT,
    category TEXT,
    created_at TIMESTAMP,
    resolution_time INT -- hours
);

CREATE TABLE IF NOT EXISTS revenue (
    id SERIAL PRIMARY KEY,
    region TEXT,
    date TIMESTAMP,
    total_revenue FLOAT
);

-- =========================
-- UNSTRUCTURED DATA (VECTOR DB)
-- =========================

CREATE TABLE IF NOT EXISTS documents (
    id UUID PRIMARY KEY,
    content TEXT NOT NULL,
    embedding VECTOR(1536),
    source TEXT,
    department TEXT,
    entity TEXT,
    created_at TIMESTAMP DEFAULT NOW()
);

-- semantic search (cosine) and keyword search indexes
CREATE INDEX IF NOT EXISTS documents_embedding_hnsw
    ON documents USING hnsw (embedding vector_cosine_ops);
CREATE INDEX IF NOT EXISTS documents_content_fts
    ON documents USING gin (to_tsvector('english', content));

-- =========================
-- OBSERVABILITY LAYER
-- (columns match core/execution_logger.py)
-- =========================

CREATE TABLE IF NOT EXISTS execution_logs (
    id SERIAL PRIMARY KEY,
    trace_id UUID,
    query TEXT,
    step TEXT,
    input JSONB,
    output JSONB,
    latency_ms FLOAT,
    tokens INT DEFAULT 0,
    cost_usd FLOAT DEFAULT 0,
    success BOOLEAN,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS investigations (
    id UUID PRIMARY KEY,
    question TEXT,
    plan JSONB,
    final_report JSONB,
    created_at TIMESTAMP DEFAULT NOW()
);
