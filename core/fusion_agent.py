from typing import Dict, Any, List


def fuse_results(query: str, sql_result: Dict, docs: str):
    """
    Converts raw SQL + retrieval outputs into unified evidence graph
    """

    # -----------------------------
    # PARSE STRUCTURED DATA
    # -----------------------------
    structured = sql_result if sql_result else {}

    # -----------------------------
    # EXTRACT UNSTRUCTURED SIGNALS
    # -----------------------------
    signals = extract_signals(docs)

    # -----------------------------
    # GENERATE INSIGHTS (RULE-BASED FIRST)
    # -----------------------------
    insights = generate_insights(structured, signals)

    # -----------------------------
    # CONFIDENCE SCORING
    # -----------------------------
    confidence = compute_confidence(structured, signals)

    return {
        "query": query,
        "structured": structured,
        "unstructured_signals": signals,
        "insights": insights,
        "confidence": confidence
    }


# -----------------------------
# SIGNAL EXTRACTION
# -----------------------------
def extract_signals(docs: str) -> List[str]:
    if not docs:
        return []

    signals = []

    text = docs.lower()

    if "refund" in text:
        signals.append("refund-related complaints detected")

    if "duplicate charge" in text:
        signals.append("duplicate charge incidents detected")

    if "delay" in text:
        signals.append("delay in processing detected")

    if "engineering" in text:
        signals.append("system improvement activity detected")

    if "escalated" in text:
        signals.append("support escalation detected")

    return signals


# -----------------------------
# INSIGHT GENERATION
# -----------------------------
def generate_insights(structured: Dict, signals: List[str]) -> List[str]:
    insights = []

    refund_volume = structured.get("value")

    if refund_volume and refund_volume > 100:
        insights.append("High refund volume indicates systemic issue")

    if "delay in processing detected" in signals:
        insights.append("Operational latency likely contributing factor")

    if "duplicate charge incidents detected" in signals:
        insights.append("Billing integrity issues present")

    if len(signals) >= 3:
        insights.append("Multi-system failure pattern detected")

    return insights


# -----------------------------
# CONFIDENCE MODEL
# -----------------------------
def compute_confidence(structured: Dict, signals: List[str]) -> float:
    score = 0.5

    if structured:
        score += 0.2

    score += min(len(signals) * 0.1, 0.3)

    return round(min(score, 0.95), 2)