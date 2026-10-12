"""
Seeds Postgres with the causal synthetic dataset and writes the ground-truth
facts used by the evaluation.

Run from the project root:
    python -m ingestion.seed_pipeline
"""
import json
from pathlib import Path

from psycopg2.extras import execute_values

from core.db import get_connection
from ingestion.synthetic_data import generate

GROUND_TRUTH_PATH = Path("evaluation/ground_truth.json")

TABLES = {
    "customers": "(id, name, region, signup_date)",
    "products": "(id, name, category, price)",
    "orders": "(id, customer_id, product_id, quantity, revenue, order_date)",
    "refunds": "(id, order_id, amount, reason, created_at)",
    "support_tickets": "(id, customer_id, severity, category, created_at, resolution_time)",
    "revenue": "(id, region, date, total_revenue)",
}


def seed():
    data = generate()
    conn = get_connection(with_vector=False)
    cur = conn.cursor()

    # wipe old rows so reseeding is repeatable
    cur.execute("TRUNCATE " + ", ".join(TABLES) + " RESTART IDENTITY CASCADE;")

    for table, cols in TABLES.items():
        execute_values(cur, f"INSERT INTO {table} {cols} VALUES %s", data[table])
        # keep SERIAL counters in sync with the explicit ids we inserted
        cur.execute(f"SELECT setval(pg_get_serial_sequence('{table}', 'id'), "
                    f"COALESCE((SELECT MAX(id) FROM {table}), 1));")
        print(f"{table}: {len(data[table])} rows")

    conn.commit()
    cur.close()
    conn.close()

    GROUND_TRUTH_PATH.parent.mkdir(exist_ok=True)
    GROUND_TRUTH_PATH.write_text(json.dumps(data["ground_truth"], indent=2))
    print(f"Ground truth written to {GROUND_TRUTH_PATH}")


if __name__ == "__main__":
    seed()
