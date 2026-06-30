-- =========================
-- ENABLE VECTOR EXTENSION
-- =========================
CREATE EXTENSION IF NOT EXISTS vector;

-- =========================
-- STRUCTURED BUSINESS DATA
-- =========================

CREATE TABLE customers (
    id SERIAL PRIMARY KEY,
    name TEXT,
    region TEXT,
    signup_date TIMESTAMP
);

CREATE TABLE products (
    id SERIAL PRIMARY KEY,
    name TEXT,
    category TEXT,
    price FLOAT
);

CREATE TABLE orders (
    id SERIAL PRIMARY KEY,
    customer_id INT,
    product_id INT,
    quantity INT,
    revenue FLOAT,
    order_date TIMESTAMP
);

CREATE TABLE support_tickets (
    id SERIAL PRIMARY KEY,
    customer_id INT,
    severity TEXT,
    category TEXT,
    created_at TIMESTAMP,
    resolution_time INT
);

CREATE TABLE revenue (
    id SERIAL PRIMARY KEY,
    region TEXT,
    date TIMESTAMP,
    total_revenue FLOAT
);

-- =========================
-- UNSTRUCTURED DATA (VECTOR DB)
-- =========================

CREATE TABLE documents (
    id UUID PRIMARY KEY,
    content TEXT,
    embedding VECTOR(1536),
    source TEXT,
    department TEXT,
    timestamp TIMESTAMP
);

-- =========================
-- OBSERVABILITY LAYER
-- =========================

CREATE TABLE execution_logs (
    query_id UUID,
    step TEXT,
    input TEXT,
    output TEXT,
    latency FLOAT,
    success BOOLEAN,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE investigations (
    id UUID PRIMARY KEY,
    question TEXT,
    plan TEXT,
    final_report TEXT,
    created_at TIMESTAMP DEFAULT NOW()
);