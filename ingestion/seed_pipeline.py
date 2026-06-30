import psycopg2
from ingestion.fake_data_generator import (
    generate_customers,
    generate_products,
    generate_orders,
    generate_support_tickets
)

conn = psycopg2.connect(
    dbname="eaip",
    user="postgres",
    password="Shm@2510",
    host="127.0.0.1",
    port=5432
)

cur = conn.cursor()


# -----------------------------
# SEED CUSTOMERS
# -----------------------------
def seed_customers():
    customers = generate_customers()

    for c in customers:
        cur.execute(
            "INSERT INTO customers (name, region, signup_date) VALUES (%s, %s, %s)",
            c
        )


# -----------------------------
# SEED PRODUCTS
# -----------------------------
def seed_products():
    products = generate_products()

    for p in products:
        cur.execute(
            "INSERT INTO products (name, category, price) VALUES (%s, %s, %s)",
            p
        )


# -----------------------------
# SEED ORDERS
# -----------------------------
def seed_orders():
    customers = list(range(1, 200))
    products = list(range(1, 4))

    orders = generate_orders(customers, products)

    for o in orders:
        cur.execute(
            "INSERT INTO orders (customer_id, product_id, quantity, revenue, order_date) VALUES (%s,%s,%s,%s,%s)",
            o
        )


# -----------------------------
# SEED SUPPORT TICKETS
# -----------------------------
def seed_tickets():
    tickets = generate_support_tickets()

    for t in tickets:
        cur.execute(
            "INSERT INTO support_tickets (customer_id, severity, category, created_at, resolution_time) VALUES (%s,%s,%s,%s,%s)",
            t
        )


# -----------------------------
# MAIN PIPELINE
# -----------------------------
if __name__ == "__main__":
    seed_customers()
    seed_products()
    seed_orders()
    seed_tickets()

    conn.commit()
    cur.close()
    conn.close()

    print("Enterprise dataset seeded successfully.")