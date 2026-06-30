import psycopg2
from faker import Faker
import random

fake = Faker()

conn = psycopg2.connect(
    dbname="eaip",
    user="postgres",
    password="postgres",
    host="localhost",
    port=5432
)

cur = conn.cursor()

def seed_customers():
    for _ in range(100):
        cur.execute(
            "INSERT INTO customers (name, region, signup_date) VALUES (%s, %s, NOW())",
            (fake.name(), random.choice(["NA", "EU", "APAC"]))
        )

def seed_products():
    for _ in range(20):
        cur.execute(
            "INSERT INTO products (name, category, price) VALUES (%s, %s, %s)",
            (fake.word(), random.choice(["AI", "Cloud", "Infra"]), random.randint(10, 500))
        )

def commit():
    conn.commit()
    cur.close()
    conn.close()

if __name__ == "__main__":
    seed_customers()
    seed_products()
    commit()
    print("Database seeded successfully")