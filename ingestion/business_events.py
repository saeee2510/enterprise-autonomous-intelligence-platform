import random
from datetime import datetime, timedelta

# -----------------------------
# Business Event Generator
# -----------------------------

class BusinessEvents:

    def __init__(self):
        self.regions = ["NA", "EU", "APAC"]
        self.products = ["AI Suite", "Cloud Engine", "Data Pipeline", "Analytics Pro"]

    # -----------------------------
    # EVENT 1: Product Bug
    # -----------------------------
    def product_bug_event(self):
        return {
            "type": "product_bug",
            "product": random.choice(self.products),
            "severity": random.choice(["low", "medium", "high", "critical"]),
            "timestamp": datetime.now() - timedelta(days=random.randint(1, 30))
        }

    # -----------------------------
    # EVENT 2: Revenue Shock
    # -----------------------------
    def revenue_drop_event(self):
        return {
            "type": "revenue_drop",
            "region": random.choice(self.regions),
            "drop_percent": random.randint(5, 30),
            "timestamp": datetime.now() - timedelta(days=random.randint(1, 30))
        }

    # -----------------------------
    # EVENT 3: Support Spike
    # -----------------------------
    def support_spike_event(self):
        return {
            "type": "support_spike",
            "category": random.choice(["billing", "bug", "performance"]),
            "multiplier": random.randint(2, 5),
            "timestamp": datetime.now() - timedelta(days=random.randint(1, 30))
        }

    # -----------------------------
    # EVENT STREAM GENERATOR
    # -----------------------------
    def generate_events(self, n=50):
        events = []

        for _ in range(n):
            event_type = random.choice([
                "product_bug",
                "revenue_drop",
                "support_spike"
            ])

            if event_type == "product_bug":
                events.append(self.product_bug_event())

            elif event_type == "revenue_drop":
                events.append(self.revenue_drop_event())

            else:
                events.append(self.support_spike_event())

        return events