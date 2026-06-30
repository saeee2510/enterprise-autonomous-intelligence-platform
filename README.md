# enterprise-autonomous-intelligence-platform

                ┌────────────────────┐
                │      Frontend      │
                │   Streamlit UI     │
                └─────────┬──────────┘
                          │
                          ▼
                ┌────────────────────┐
                │   FastAPI Backend  │
                └─────────┬──────────┘
                          │
                          ▼
                ┌────────────────────┐
                │  Intent Router     │
                └─────────┬──────────┘
                          │
        ┌─────────────────┼─────────────────┐
        ▼                 ▼                 ▼
┌──────────────┐  ┌──────────────┐  ┌──────────────┐
│ SQL Agent     │  │ Retrieval    │  │ Planner      │
│ (Postgres)    │  │ Agent        │  │ (LangGraph)  │
└──────┬────────┘  └──────┬───────┘  └──────┬───────┘
       ▼                 ▼                 ▼
   PostgreSQL        pgvector DB     Execution Plan
       └──────────────┬──────────────┘
                      ▼
            ┌────────────────────┐
            │ Fusion Agent       │
            └─────────┬──────────┘
                      ▼
            ┌────────────────────┐
            │ Verification Agent │
            └─────────┬──────────┘
                      ▼
            ┌────────────────────┐
            │ Report Generator   │
            └─────────┬──────────┘
                      ▼
              Final Answer + Evidence
