from typing import Dict, List
from core.claim_builder import build_claim_graph


# -----------------------------
# MAIN FUSION FUNCTION
# -----------------------------
def fuse_results(query: str, sql_result: Dict, docs: str):

    structured = sql_result or {}

    # Extract signals from retrieved documents
    signals = extract_signals(docs)

    # Generate higher-level insights
    insights = generate_insights(structured, signals)

    # Track available evidence sources
    source_map = {
        "sql": bool(sql_result),
        "docs": bool(docs)
    }

    # Build claim graph
    claims = build_claim_graph(
        fused={
            "insights": insights
        },
        sql_result=structured,
        signals=signals
    )

    # Overall evidence confidence
    confidence = compute_claim_confidence(claims)

    return {
        "query": query,
        "structured": structured,
        "unstructured_signals": signals,
        "insights": insights,
        "claims": claims,
        "confidence": confidence,
        "source_map": source_map
    }


# -----------------------------
# SIGNAL EXTRACTION
# -----------------------------
def extract_signals(docs: str) -> List[str]:

    if not docs:
        return []

    text = docs.lower()
    signals = []

    if "refund" in text:
        signals.append("refund-related complaints detected")

    if "duplicate charge" in text:
        signals.append("duplicate charge incidents detected")

    if "delay" in text:
        signals.append("delay in processing detected")

    if "escalated" in text:
        signals.append("support escalation detected")

    if "engineering" in text:
        signals.append("system improvement activity detected")

    return signals


# -----------------------------
# INSIGHT GENERATION
# -----------------------------
def generate_insights(structured: Dict, signals: List[str]) -> List[str]:

    insights = []

    value = structured.get("value", 0)

    if isinstance(value, (int, float)) and value > 100:
        insights.append("High refund volume indicates systemic issue")

    if "duplicate charge incidents detected" in signals:
        insights.append("Billing integrity issues present")

    if "delay in processing detected" in signals:
        insights.append("Operational latency likely contributing factor")

    if len(signals) >= 3:
        insights.append("Multi-system failure pattern detected")

    return insights


# -----------------------------
# CONFIDENCE
# -----------------------------
def compute_claim_confidence(claims):

    if not claims:
        return 0.0

    total = len(claims)
    score = sum(1 for c in claims if c.get("verified"))

    base = score / total

    # boost factual claims
    fact_bonus = 0.1 * sum(
        1 for c in claims
        if c.get("type") == "fact"
    )

    return round(min(base + fact_bonus, 0.95), 2)