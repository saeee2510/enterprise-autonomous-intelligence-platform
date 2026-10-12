"""
Deterministic synthetic enterprise dataset with a known causal story.

The story the agents should be able to discover:

  1. Release v3.2 ships on 2025-04-15 with a new automatic payment-retry
     mechanism in the Checkout Service.
  2. Retry handling is buggy for European payment providers, so EU
     customers get duplicate charges and some checkouts fail.
  3. EU support tickets spike (billing / checkout_bug categories).
  4. Duplicate charges are refunded, and failed checkouts reduce orders.
  5. EU net revenue drops.
  6. Hotfix v3.2.1 ships on 2025-05-02 and EU recovers gradually.

Two distractors exist so the system can be tested on NOT mis-attributing:

  - APAC has a performance-ticket spike on 2025-03-10..14 with no revenue impact.
  - NA runs a spring promotion 2025-04-10..30 that lifts NA revenue.

Everything is seeded, so the same seed always produces the same data, and
GROUND TRUTH facts are computed from the generated rows themselves.
"""
import random
from collections import defaultdict
from datetime import date, datetime, timedelta

SEED = 42

START = date(2025, 3, 1)
END = date(2025, 5, 31)
RELEASE_DATE = date(2025, 4, 15)
HOTFIX_DATE = date(2025, 5, 2)
FULL_RECOVERY_DATE = date(2025, 5, 16)

APAC_INCIDENT = (date(2025, 3, 10), date(2025, 3, 14))
NA_PROMO = (date(2025, 4, 10), date(2025, 4, 30))

REGIONS = ["NA", "EU", "APAC"]
BASE_ORDERS_PER_DAY = {"NA": 40, "EU": 35, "APAC": 25}
BASE_TICKETS_PER_DAY = {"NA": 3, "EU": 3, "APAC": 2}

PRODUCTS = [
    ("AI Suite", "AI", 299.0),
    ("Cloud Engine", "Cloud", 199.0),
    ("Data Pipeline", "Data", 149.0),
    ("Analytics Pro", "BI", 99.0),
]

BASE_TICKET_CATEGORIES = {
    "account": 0.35,
    "billing": 0.25,
    "performance": 0.20,
    "refund_request": 0.20,
}

_COMPANY_PREFIX = ["Nordic", "Atlas", "Blue", "Summit", "Vertex", "Harbor",
                   "Pioneer", "Silver", "Orbit", "Lumen", "Crest", "Delta"]
_COMPANY_SUFFIX = ["Retail", "Labs", "Systems", "Foods", "Logistics", "Media",
                   "Health", "Finance", "Energy", "Motors", "Studios", "Group"]
_REGION_TAG = {"NA": "Inc", "EU": "GmbH", "APAC": "Pte Ltd"}


def daterange(start: date, end: date):
    d = start
    while d <= end:
        yield d
        d += timedelta(days=1)


def _ts(rng: random.Random, d: date) -> datetime:
    return datetime(d.year, d.month, d.day, rng.randint(0, 23), rng.randint(0, 59))


def _eu_bug_severity(d: date) -> float:
    """0 = no bug impact, 1 = full impact. Ramps down after the hotfix."""
    if d < RELEASE_DATE:
        return 0.0
    if d < HOTFIX_DATE:
        return 1.0
    if d >= FULL_RECOVERY_DATE:
        return 0.0
    days_left = (FULL_RECOVERY_DATE - d).days
    return days_left / (FULL_RECOVERY_DATE - HOTFIX_DATE).days * 0.5


def _weighted_choice(rng: random.Random, weights: dict) -> str:
    return rng.choices(list(weights), weights=list(weights.values()), k=1)[0]


def generate(seed: int = SEED) -> dict:
    rng = random.Random(seed)

    # ---------------- customers ----------------
    customers = []  # (id, name, region, signup_date)
    cid = 1
    for region in REGIONS:
        for _ in range(100):
            name = (f"{rng.choice(_COMPANY_PREFIX)} {rng.choice(_COMPANY_SUFFIX)} "
                    f"{_REGION_TAG[region]}")
            signup = START - timedelta(days=rng.randint(30, 700))
            customers.append((cid, name, region, datetime.combine(signup, datetime.min.time())))
            cid += 1
    by_region = defaultdict(list)
    for c in customers:
        by_region[c[2]].append(c[0])

    # ---------------- products ----------------
    products = [(i + 1, n, cat, p) for i, (n, cat, p) in enumerate(PRODUCTS)]

    # ---------------- orders + refunds ----------------
    orders = []   # (id, customer_id, product_id, quantity, revenue, order_date)
    refunds = []  # (id, order_id, amount, reason, created_at)
    oid, rid = 1, 1

    for d in daterange(START, END):
        for region in REGIONS:
            base = BASE_ORDERS_PER_DAY[region]
            multiplier = 1.0

            sev = _eu_bug_severity(d) if region == "EU" else 0.0
            if region == "EU":
                multiplier *= 1.0 - 0.15 * sev  # failed checkouts
            if region == "NA" and NA_PROMO[0] <= d <= NA_PROMO[1]:
                multiplier *= 1.35  # strong enough that April net revenue clearly beats March

            n_orders = max(0, round(rng.gauss(base * multiplier, base * 0.08)))

            for _ in range(n_orders):
                prod = rng.choice(products)
                qty = rng.choices([1, 2, 3], weights=[0.7, 0.2, 0.1])[0]
                price = prod[3]
                if region == "NA" and NA_PROMO[0] <= d <= NA_PROMO[1]:
                    price *= 0.9  # promo discount
                revenue = round(price * qty, 2)
                created = _ts(rng, d)
                orders.append((oid, rng.choice(by_region[region]), prod[0], qty, revenue, created))

                if region == "EU" and rng.random() < 0.08 * sev:
                    refunds.append((rid, oid, revenue, "duplicate_charge",
                                    created + timedelta(days=rng.randint(1, 4))))
                    rid += 1
                elif rng.random() < 0.02:
                    refunds.append((rid, oid, revenue, "customer_request",
                                    created + timedelta(days=rng.randint(1, 10))))
                    rid += 1
                oid += 1

    # ---------------- support tickets ----------------
    tickets = []  # (id, customer_id, severity, category, created_at, resolution_time_hours)
    tid = 1
    for d in daterange(START, END):
        for region in REGIONS:
            n_base = max(0, round(rng.gauss(BASE_TICKETS_PER_DAY[region], 1)))
            batch = [(_weighted_choice(rng, BASE_TICKET_CATEGORIES),
                      rng.choices(["low", "medium", "high"], weights=[0.5, 0.35, 0.15])[0])
                     for _ in range(n_base)]

            if region == "EU":
                sev = _eu_bug_severity(d)
                for _ in range(round(5 * sev)):
                    batch.append(("billing", rng.choice(["high", "critical"])))
                for _ in range(round(2 * sev)):
                    batch.append(("checkout_bug", rng.choice(["high", "critical"])))

            if region == "APAC" and APAC_INCIDENT[0] <= d <= APAC_INCIDENT[1]:
                for _ in range(8):
                    batch.append(("performance", "medium"))

            for category, severity in batch:
                resolution = rng.randint(4, 24) if severity in ("low", "medium") else rng.randint(12, 96)
                tickets.append((tid, rng.choice(by_region[region]), severity, category,
                                _ts(rng, d), resolution))
                tid += 1

    # ---------------- daily revenue rollup ----------------
    cust_region = {c[0]: c[2] for c in customers}
    order_region = {o[0]: cust_region[o[1]] for o in orders}
    gross = defaultdict(float)
    for o in orders:
        gross[(cust_region[o[1]], o[5].date())] += o[4]
    refunded = defaultdict(float)
    for r in refunds:
        refunded[(order_region[r[1]], r[4].date())] += r[2]

    revenue = []  # (id, region, date, total_revenue)
    rev_id = 1
    for d in daterange(START, END):
        for region in REGIONS:
            net = gross[(region, d)] - refunded[(region, d)]
            revenue.append((rev_id, region, datetime.combine(d, datetime.min.time()), round(net, 2)))
            rev_id += 1

    data = {
        "customers": customers,
        "products": products,
        "orders": orders,
        "refunds": refunds,
        "support_tickets": tickets,
        "revenue": revenue,
    }
    data["ground_truth"] = compute_ground_truth(data)
    return data


# ----------------------------------------------------------------------
# GROUND TRUTH (computed from the rows, used later by the evaluation)
# ----------------------------------------------------------------------
PRE_WINDOW = (date(2025, 4, 1), date(2025, 4, 14))    # 14 days before release
BUG_WINDOW = (date(2025, 4, 15), date(2025, 4, 28))   # 14 days after release


def _in(d: date, window) -> bool:
    return window[0] <= d <= window[1]


def compute_ground_truth(data: dict) -> dict:
    cust_region = {c[0]: c[2] for c in data["customers"]}

    def revenue_in(region, window):
        return sum(r[3] for r in data["revenue"] if r[1] == region and _in(r[2].date(), window))

    def tickets_in(region, window, category=None):
        return sum(1 for t in data["support_tickets"]
                   if cust_region[t[1]] == region and _in(t[4].date(), window)
                   and (category is None or t[3] == category))

    facts = {"windows": {"pre_release": [str(PRE_WINDOW[0]), str(PRE_WINDOW[1])],
                         "post_release": [str(BUG_WINDOW[0]), str(BUG_WINDOW[1])]},
             "release_date": str(RELEASE_DATE),
             "hotfix_date": str(HOTFIX_DATE),
             "root_cause": "Release v3.2 payment-retry bug caused duplicate charges and "
                           "checkout failures for EU customers",
             "regions": {}}

    for region in REGIONS:
        pre_rev, post_rev = revenue_in(region, PRE_WINDOW), revenue_in(region, BUG_WINDOW)
        pre_t, post_t = tickets_in(region, PRE_WINDOW), tickets_in(region, BUG_WINDOW)
        post_cats = defaultdict(int)
        for t in data["support_tickets"]:
            if cust_region[t[1]] == region and _in(t[4].date(), BUG_WINDOW):
                post_cats[t[3]] += 1
        facts["regions"][region] = {
            "net_revenue_pre": round(pre_rev, 2),
            "net_revenue_post": round(post_rev, 2),
            "net_revenue_change_pct": round((post_rev - pre_rev) / pre_rev * 100, 1),
            "tickets_pre": pre_t,
            "tickets_post": post_t,
            "tickets_change_pct": round((post_t - pre_t) / max(pre_t, 1) * 100, 1),
            "top_ticket_category_post": max(post_cats, key=post_cats.get) if post_cats else None,
        }

    facts["duplicate_charge_refunds_total"] = sum(1 for r in data["refunds"] if r[3] == "duplicate_charge")
    facts["duplicate_charge_refund_amount_total"] = round(
        sum(r[2] for r in data["refunds"] if r[3] == "duplicate_charge"), 2)
    facts["total_tickets"] = len(data["support_tickets"])
    facts["total_orders"] = len(data["orders"])
    facts["apac_performance_tickets_incident_window"] = sum(
        1 for t in data["support_tickets"]
        if cust_region[t[1]] == "APAC" and t[3] == "performance" and _in(t[4].date(), APAC_INCIDENT))
    return facts


if __name__ == "__main__":
    import json
    d = generate()
    for k, v in d.items():
        if k != "ground_truth":
            print(f"{k}: {len(v)} rows")
    print(json.dumps(d["ground_truth"], indent=2))
