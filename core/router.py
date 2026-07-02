

def route_query(query: str):
    q = query.lower()

    # -------------------------
    # 1. SQL INTENT
    # -------------------------
    sql_triggers = [
        "how many",
        "count",
        "total",
        "trend",
        "group by",
        "revenue",
        "volume"
    ]

    if any(t in q for t in sql_triggers):
        return {
            "route": "sql",
            "confidence": 0.9
        }

    # -------------------------
    # 2. ANALYTICAL / HYBRID
    # -------------------------
    hybrid_triggers = [
        "why",
        "reason",
        "issue",
        "problem",
        "refund",
        "delay",
        "duplicate",
        "escalation"
    ]

    if any(t in q for t in hybrid_triggers):
        return {
            "route": "hybrid",
            "confidence": 0.85
        }

    # -------------------------
    # 3. DEFAULT → RAG
    # -------------------------
    return {
        "route": "rag",
        "confidence": 0.6
    }