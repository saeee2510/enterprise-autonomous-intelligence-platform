from typing import Dict, List, Any
import uuid


def build_claim_graph(fused: Dict, sql_result: Dict, signals: List[str]):

    claims = []

    # -----------------------
    # FACT CLAIM (SQL)
    # -----------------------
    if sql_result and "value" in sql_result:
        claims.append({
            "id": str(uuid.uuid4()),
            "type": "fact",
            "statement": f"{sql_result['name']} = {sql_result['value']}",
            "source": "sql",
            "confidence": 1.0
        })

    # -----------------------
    # SIGNAL CLAIMS (DOCS)
    # -----------------------
    for s in signals:
        claims.append({
            "id": str(uuid.uuid4()),
            "type": "signal",
            "statement": s,
            "source": "docs",
            "confidence": 0.6
        })

    # -----------------------
    # INFERENCE CLAIMS (INSIGHTS)
    # -----------------------
    for insight in fused.get("insights", []):
        claims.append({
            "id": str(uuid.uuid4()),
            "type": "inference",
            "statement": insight,
            "depends_on": [claims[0]["id"]] if claims else [],
            "source": "reasoning",
            "confidence": 0.7
        })

    return claims