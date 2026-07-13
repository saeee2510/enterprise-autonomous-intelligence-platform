from typing import Dict


def generate_report(query: str, fused: Dict, verified: Dict):

    structured = fused.get("structured", {})
    insights = fused.get("insights", [])
    verified_claims = verified.get("verified_claims", [])

    executive_summary = ""

    if structured.get("type") == "metric":
        executive_summary = (
            f"The system found {structured.get('value')} "
            f"{structured.get('unit')} for {structured.get('name')}."
        )

    key_metrics = []

    if structured.get("type") == "metric":
        key_metrics.append({
            "metric": structured.get("name"),
            "value": structured.get("value"),
            "unit": structured.get("unit")
        })

    recommendations = []

    if structured.get("value", 0) > 100:
        recommendations.append(
            "Investigate the root cause of the elevated refund volume."
        )

    if not recommendations:
        recommendations.append(
            "No immediate action recommended."
        )

    return {
        "question": query,
        "executive_summary": executive_summary,
        "verified_evidence": verified_claims,
        "insights": insights,
        "key_metrics": key_metrics,
        "timeline": [],
        "risk_level": "medium",
        "recommendations": recommendations,
        "confidence": verified.get("confidence", 0)
    }