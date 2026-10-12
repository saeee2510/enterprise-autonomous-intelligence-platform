import pandas as pd
import requests
import streamlit as st

API_URL = "http://127.0.0.1:8000/query"

STATUS_LABEL = {
    "supported": "✅ supported",
    "needs_review": "🟡 needs review",
    "unsupported": "❌ rejected",
}

st.set_page_config(page_title="Enterprise Autonomous Intelligence Platform",
                   page_icon="🧠", layout="wide")

st.sidebar.title("Enterprise AI Platform")
st.sidebar.markdown("""
**Pipeline (LangGraph)**

Plan → SQL ∥ Retrieval → Fuse → Verify ⟲ (one revision) → Report

**Stack**

FastAPI · PostgreSQL · pgvector · GPT-4o-mini · text-embedding-3-small
""")

st.title("🧠 Enterprise Autonomous Intelligence Platform")
st.caption("Evidence-backed investigations of business questions")

query = st.text_input("Business question", placeholder="Why did revenue drop in Europe?")

if st.button("🚀 Investigate") and query:
    with st.spinner("Running investigation..."):
        response = requests.post(API_URL, json={"query": query}, timeout=180)

    if response.status_code != 200:
        st.error(f"Backend error {response.status_code}: {response.text[:500]}")
        st.stop()

    result = response.json()
    report = result.get("report", {})
    verified = result.get("verified", {})
    sql_results = result.get("sql", [])
    documents = result.get("documents", [])
    plan = result.get("trace", {})
    metrics = result.get("metrics", {})

    counts = verified.get("counts", {})
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Confidence", f"{verified.get('confidence', 0) * 100:.0f}%")
    c2.metric("Supported claims", counts.get("supported", 0))
    c3.metric("Needs review", counts.get("needs_review", 0))
    c4.metric("Rejected claims", counts.get("unsupported", 0))

    st.divider()
    tab1, tab2, tab3, tab4 = st.tabs(["📋 Report", "📊 Evidence", "🧠 Pipeline", "⚙ Debug"])

    with tab1:
        st.subheader("Executive summary")
        st.write(report.get("executive_summary", ""))
        for issue in report.get("consistency_issues", []):
            st.error(f"⚠ Summary contradicts the data ({issue.get('type')}): "
                     f"\"{issue.get('summary_statement', '')}\" vs SQL {issue.get('sql_values', '')}. "
                     f"{issue.get('explanation', '')}")
        if report.get("consistency_notes"):
            with st.expander(f"Verifier notes ({len(report['consistency_notes'])})"):
                for n in report["consistency_notes"]:
                    st.write(f"• ({n.get('type')}) {n.get('explanation', '')}")

        st.subheader("Root cause")
        st.info(report.get("root_cause", "Not established by the evidence"))

        st.subheader("Findings")
        for f in report.get("findings", []):
            st.write(f"{STATUS_LABEL.get(f['status'], f['status'])} · {f['statement']} "
                     f"`{', '.join(f['evidence_ids'])}`")

        if report.get("rejected_claims"):
            with st.expander(f"Rejected claims ({len(report['rejected_claims'])})"):
                for r in report["rejected_claims"]:
                    st.write(f"❌ {r['statement']}  \n_{r['reason']}_")

        if report.get("timeline"):
            st.subheader("Timeline")
            for t in report["timeline"]:
                st.write(f"**{t.get('date', '')}** · {t.get('event', '')} "
                         f"`{', '.join(t.get('evidence_ids', []))}`")
        if report.get("rejected_timeline"):
            with st.expander(f"Rejected timeline events ({len(report['rejected_timeline'])})"):
                for t in report["rejected_timeline"]:
                    st.write(f"❌ {t.get('date', '')} · {t.get('event', '')}  \n_{t['reason']}_")

        if report.get("recommendations"):
            st.subheader("Recommendations")
            for r in report["recommendations"]:
                st.write(f"• {r}")

    with tab2:
        st.subheader("SQL evidence")
        for r in sql_results:
            with st.expander(f"[{r['evidence_id']}] {r['action']}"):
                st.code(r.get("sql") or "", language="sql")
                if r.get("error"):
                    st.error(r["error"])
                elif r.get("rows"):
                    st.dataframe(pd.DataFrame(r["rows"], columns=r["columns"]),
                                 use_container_width=True)

        st.subheader("Document evidence")
        for d in documents:
            with st.expander(f"[{d['evidence_id']}] {d['source']} "
                             f"(vector {d['vector_score']}, bm25 {d['bm25_score']})"):
                st.text(d["content"])

    with tab3:
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Latency", f"{metrics.get('total_latency_ms', 0) / 1000:.1f}s")
        m2.metric("LLM calls", metrics.get("llm_calls", 0))
        m3.metric("Tokens", f"{metrics.get('tokens', 0):,}")
        m4.metric("Cost", f"${metrics.get('cost_usd', 0):.4f}")
        st.caption(f"Trace ID: {result.get('trace_id', '')} · revisions: {metrics.get('revisions', 0)}")
        if metrics.get("steps"):
            st.subheader("Step timings")
            st.dataframe(pd.DataFrame(metrics["steps"]), use_container_width=True)

        st.subheader(f"Execution plan · intent: {plan.get('intent', '')}")
        for step in plan.get("steps", []):
            st.write(f"Step {step['step']} · **{step['tool']}** · {step['action']}")
        if plan.get("fallback_reason"):
            st.warning(f"Fallback plan used: {plan['fallback_reason']}")

        st.subheader("Claim verification")
        claims = verified.get("claims", [])
        if claims:
            st.dataframe(pd.DataFrame([{
                "claim": c["statement"], "type": c["type"], "status": c["status"],
                "evidence": ", ".join(c["evidence_ids"]), "reason": c["reason"],
            } for c in claims]), use_container_width=True)

    with tab4:
        st.json(result)
