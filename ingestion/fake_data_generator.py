import random
from faker import Faker
from datetime import datetime
from ingestion.business_events import BusinessEvents

fake = Faker()
events = BusinessEvents()


# -----------------------------
# CUSTOMERS
# -----------------------------
def generate_customers(n=200):
    return [
        (fake.name(), random.choice(["NA", "EU", "APAC"]), datetime.now())
        for _ in range(n)
    ]


# -----------------------------
# PRODUCTS
# -----------------------------
def generate_products():
    return [
        ("AI Suite", "AI", 299),
        ("Cloud Engine", "Cloud", 199),
        ("Data Pipeline", "Data", 149),
        ("Analytics Pro", "BI", 99)
    ]


# -----------------------------
# ORDERS (with mild correlation logic)
# -----------------------------
def generate_orders(customers, products, n=1000):
    orders = []

    for _ in range(n):
        customer_id = random.randint(1, len(customers))
        product_id = random.randint(1, len(products))

        base_revenue = random.randint(50, 500)

        # simulate slight real-world noise
        noise = random.uniform(0.8, 1.2)

        revenue = base_revenue * noise

        orders.append((
            customer_id,
            product_id,
            random.randint(1, 3),
            revenue,
            datetime.now()
        ))

    return orders


# -----------------------------
# SUPPORT TICKETS (event-driven)
# -----------------------------
def generate_support_tickets(n=300):
    tickets = []

    for _ in range(n):
        event = random.choice(["bug", "billing", "performance"])

        tickets.append((
            random.randint(1, 200),
            random.choice(["low", "medium", "high", "critical"]),
            event,
            datetime.now(),
            random.randint(1, 72)
        ))

    return tickets