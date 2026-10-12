"""
Report Generator: assembles the final report from verified claims only.

Rejected claims are never shown as findings; they are listed separately so
the user can see what the system refused to assert.
"""


def generate_report(question: str, fused: dict, verified: dict, sql_results, chunks) -> dict:
    accepted_ids = {c["id"] for c in verified["verified_claims"]}

    key_metrics = []
    for r in sql_results:
        if r.get("error") or not r["rows"]:
            continue
        for row in r["rows"][:20]:
            key_metrics.append({"evidence_id": r["evidence_id"], "metric": r["action"],
                                **dict(zip(r["columns"], row))})

    sources = sorted({c["source"] for c in chunks})

    return {
        "question": question,
        "executive_summary": fused.get("summary", ""),
        "root_cause": fused.get("root_cause") or "Not established by the evidence",
        "findings": [
            {"statement": c["statement"], "status": c["status"],
             "evidence_ids": c["valid_evidence_ids"]}
            for c in verified["verified_claims"]
        ],
        "rejected_claims": [
            {"statement": c["statement"], "reason": c["reason"]}
            for c in verified["rejected_claims"]
        ],
        "timeline": sorted(verified.get("timeline", []), key=lambda t: str(t.get("date", ""))),
        "rejected_timeline": verified.get("rejected_timeline", []),
        "key_metrics": key_metrics,
        "recommendations": fused.get("recommendations", []) if accepted_ids else [],
        "sources": sources,
        "summary_consistent": verified.get("summary_consistent", True),
        "consistency_issues": verified.get("consistency_issues", []),
        "consistency_notes": verified.get("consistency_notes", []),
        "confidence": verified["confidence"],
    }
