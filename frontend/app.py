import streamlit as st
import requests
import pandas as pd

API_URL = "http://127.0.0.1:8000/query"

st.set_page_config(
    page_title="Enterprise Autonomous Intelligence Platform",
    page_icon="🧠",
    layout="wide"
)

# ======================================================
# SIDEBAR
# ======================================================

st.sidebar.title("Enterprise AI Platform")

st.sidebar.markdown("""
### System

- Backend: FastAPI
- Database: PostgreSQL
- Vector DB: pgvector
- LLM: GPT-4o Mini
- Embeddings: text-embedding-3-small
""")

st.sidebar.success("System Online")

# ======================================================
# HEADER
# ======================================================

st.title("🧠 Enterprise Autonomous Intelligence Platform")
st.caption("Evidence-backed AI investigations for enterprise business questions")

query = st.text_input(
    "Business Question",
    placeholder="Why did revenue drop in Europe?"
)

# ======================================================
# RUN BUTTON
# ======================================================

if st.button("🚀 Investigate") and query:

    with st.status("Executing Investigation Pipeline...", expanded=True) as status:

        st.write("✅ Intent Router")
        st.write("✅ Planner")
        st.write("✅ SQL Agent")
        st.write("✅ Retrieval Agent")
        st.write("✅ Fusion Agent")
        st.write("✅ Verification Agent")
        st.write("✅ Report Generator")

        response = requests.post(
            API_URL,
            json={"query": query}
        )

        result = response.json()

        status.update(
            label="Investigation Complete",
            state="complete"
        )

    answer = result.get("answer", "")
    report = result.get("report", {})
    verified = result.get("verified", {})
    fused = result.get("fused", {})
    sql = result.get("sql", {})
    docs = result.get("docs", "")
    trace = result.get("trace", {})

    # ======================================================
    # CONFIDENCE
    # ======================================================

    confidence = verified.get(
        "confidence",
        fused.get("confidence", 0)
    )

    st.metric(
        "Overall Confidence",
        f"{confidence*100:.0f}%"
    )

    st.divider()

    # ======================================================
    # MAIN TABS
    # ======================================================

    tab1, tab2, tab3, tab4 = st.tabs(
        [
            "📋 Investigation Report",
            "📊 Evidence",
            "🧠 Pipeline",
            "⚙ Debug"
        ]
    )

    # ======================================================
    # TAB 1
    # ======================================================

    with tab1:

        st.subheader("Executive Summary")

        st.success(answer)

        st.subheader("Structured Report")

        if report:

            st.markdown("### Executive Summary")
            st.write(report.get("executive_summary", ""))

            st.markdown("### Root Cause")
            st.write(report.get("root_cause", "Not identified"))

            st.markdown("### Risk Level")
            st.info(report.get("risk_level", "Unknown"))

            st.markdown("### Recommendations")

            for r in report.get("recommendations", []):
                st.write(f"• {r}")

            metrics = report.get("key_metrics", [])

            if metrics:

                st.markdown("### Key Metrics")

                df = pd.DataFrame(metrics)

                st.dataframe(
                    df,
                    use_container_width=True
                )

    # ======================================================
    # TAB 2
    # ======================================================

    with tab2:

        col1, col2 = st.columns(2)

        with col1:
            st.subheader("📌 Final Answer")
            st.write(result.get("answer", ""))

            report = result.get("report", {})

            st.subheader("📋 Executive Summary")
            st.write(report.get("executive_summary", ""))

            st.subheader("📊 Key Metrics")
            st.json(report.get("key_metrics", []))

            st.subheader("💡 Recommendations")
            for rec in report.get("recommendations", []):
                st.write(f"• {rec}")

            st.subheader("🎯 Confidence")
            st.metric("Confidence", report.get("confidence", 0))

        with col2:

            st.subheader("Retrieved Documents")

            if docs:
                st.text_area(
                    "Retrieved Context",
                    docs,
                    height=350
                )
            else:
                st.info("No documents retrieved.")

            st.subheader("Insights")

            insights = fused.get("insights", [])

            if insights:

                for i in insights:
                    st.success(i)

            else:
                st.info("No insights generated.")

    # ======================================================
    # TAB 3
    # ======================================================

    with tab3:

        st.subheader("Execution Plan")

        steps = trace.get("steps", [])

        if steps:

            for step in steps:

                st.success(
                    f"Step {step.get('step')} • "
                    f"{step.get('tool')} • "
                    f"{step.get('action')}"
                )

        st.subheader("Fusion Output")

        st.json(fused)

    # ======================================================
    # TAB 4
    # ======================================================

    with tab4:

        with st.expander("Verified Evidence"):
            st.json(verified)

        with st.expander("Fusion Graph"):
            st.json(fused)

        with st.expander("Execution Trace"):
            st.json(trace)

        with st.expander("Raw SQL"):
            st.json(sql)

        with st.expander("Retrieved Documents"):
            st.text(docs)