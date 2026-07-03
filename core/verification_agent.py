import json

# -----------------------------
# CLAIM EXTRACTION (MVP)
# -----------------------------
def extract_claims(text: str):
    lines = [l.strip("- ").strip() for l in text.split("\n") if l.strip()]
    return [l for l in lines if len(l) > 5]


# -----------------------------
# SQL VERIFICATION
# -----------------------------
def verify_sql_claims(claims, sql_result):
    verified = []

    for c in claims:
        if sql_result and str(sql_result.get("value")) in c:
            verified.append({
                "claim": c,
                "verified": True,
                "source": "sql"
            })
        else:
            verified.append({
                "claim": c,
                "verified": False,
                "source": "sql"
            })

    return verified


# -----------------------------
# DOC VERIFICATION
# -----------------------------
def verify_doc_claims(claims, docs_text):
    verified = []

    for c in claims:
        if docs_text and c.lower()[:20] in docs_text.lower():
            verified.append({
                "claim": c,
                "verified": True,
                "source": "docs"
            })
        else:
            verified.append({
                "claim": c,
                "verified": False,
                "source": "docs"
            })

    return verified


# -----------------------------
# CONFIDENCE ENGINE (FINAL)
# -----------------------------
def compute_confidence(verified_claims):

    sql_count = 0
    doc_count = 0

    earned = 0
    total = 0

    for c in verified_claims:

        if c["source"] == "sql":
            sql_count += 1
            total += 1.0
            if c["verified"]:
                earned += 1.0

        elif c["source"] == "docs":
            doc_count += 1
            total += 0.5
            if c["verified"]:
                earned += 0.5

    if total == 0:
        return 0.0

    base_conf = earned / total

    # -----------------------------
    # DIVERSITY PENALTY (IMPORTANT)
    # -----------------------------
    sources = (sql_count > 0) + (doc_count > 0)

    if sources == 1:
        base_conf *= 0.85   # penalize single-source answers

    return round(min(base_conf, 1.0), 2)


# -----------------------------
# MAIN VERIFY PIPELINE
# -----------------------------
def verify(fused_output, sql_result, docs_text):

    verified_claims = []
    insights_review = []

    # -----------------------------
    # 1. FACT VERIFICATION (SQL)
    # -----------------------------
    if fused_output.get("structured"):

        s = fused_output["structured"]

        if s.get("type") == "metric":
            claim = f"{s['name']} = {s['value']} {s.get('unit', '')}"

            verified_claims.append({
                "claim": claim,
                "verified": sql_result is not None,
                "source": "sql"
            })

    # -----------------------------
    # 2. EVIDENCE VERIFICATION (DOCS)
    # -----------------------------
    for signal in fused_output.get("unstructured_signals", []):

        verified_claims.append({
            "claim": signal,
            "verified": signal.lower() in (docs_text or "").lower(),
            "source": "docs"
        })

    # -----------------------------
    # 3. INSIGHT REVIEW (NON-BOOLEAN)
    # -----------------------------
    for insight in fused_output.get("insights", []):

        insights_review.append({
            "insight": insight,
            "type": "inferred",
            "note": "Requires reasoning layer (NOT fact-checked)"
        })

    # -----------------------------
    # 4. CONFIDENCE (CORRECT)
    # -----------------------------
    confidence = compute_confidence(verified_claims)

    return {
        "verified_claims": verified_claims,
        "insights_review": insights_review,
        "confidence": confidence,
        "raw_fused": fused_output
    }