from typing import Dict, Any, List


# -----------------------------
# MAIN FUSION FUNCTION
# -----------------------------
def fuse_results(query: str, sql_result: Dict, docs: str):

    structured = sql_result or {}

    signals = extract_signals(docs)
    insights = generate_insights(structured, signals)

    source_map = {
        "sql": bool(sql_result),
        "docs": bool(docs)
    }

    verified_claims = build_claims(structured, signals)

    confidence = compute_confidence(verified_claims, source_map)

    return {
        "query": query,
        "structured": structured,
        "unstructured_signals": signals,
        "insights": insights,
        "confidence": confidence,
        "source_map": source_map
    }


# -----------------------------
# CLAIM BUILDER (IMPORTANT FIX)
# -----------------------------
def build_claims(structured: Dict, signals: List[str]):

    claims = []

    # SQL claim
    if structured and "value" in structured:
        claims.append({
            "claim": f"{structured.get('name')} = {structured.get('value')}",
            "verified": True,
            "source": "sql"
        })

    # signal claims (docs-derived heuristics)
    for s in signals:
        claims.append({
            "claim": s,
            "verified": False,
            "source": "docs"
        })

    return claims


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
# INSIGHTS GENERATION
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
# CONFIDENCE (FIXED + STABLE)
# -----------------------------
def compute_confidence(verified_claims: List[Dict], source_map: Dict):

    if not verified_claims:
        return 0.0

    verified_count = 0

    for c in verified_claims:
        if isinstance(c, dict) and c.get("verified") is True:
            verified_count += 1

    base = verified_count / len(verified_claims)

    # structured boost
    if source_map.get("sql"):
        base += 0.1

    # docs uncertainty penalty
    if source_map.get("docs"):
        base -= 0.05

    return round(max(0.0, min(base, 0.95)), 2)