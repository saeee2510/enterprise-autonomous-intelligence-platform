# enterprise-autonomous-intelligence-platform

  # Enterprise Autonomous Intelligence Platform

An enterprise-grade, multi-agent AI platform that answers business questions using **structured** (SQL) and **unstructured** (documents, tickets, emails) enterprise data — with full **traceability** from every claim back to its source.

This is not a chatbot wrapper. It's a deterministic, multi-stage pipeline: a question comes in, an intent router and planner decide what data is needed, dedicated agents pull SQL results and retrieved documents, a fusion step combines them into an evidence graph, a verification step rejects unsupported claims, and a report generator produces the final, cited answer.

## System Design Goals

**Functional**
- Accept a natural-language business question
- Decide which data sources are needed (SQL, documents, or both)
- Run SQL queries safely (read-only)
- Retrieve relevant documents via hybrid search
- Fuse structured + unstructured evidence
- Generate a final report with an evidence trail

**Non-functional**
- Deterministic execution pipeline — agents are functions, not open-ended "LLM loops"
- Full observability: every step is logged (prompts, responses, latency, tokens, decisions)
- Low-hallucination design via a dedicated verification layer
- Reproducibility: same input → same execution trace
- Stateless backend — all state lives in Postgres

## Architecture

```
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
                │   Intent Router    │
                └─────────┬──────────┘
                          │
        ┌─────────────────┼─────────────────┐
        ▼                 ▼                 ▼
┌──────────────┐  ┌──────────────┐  ┌──────────────┐
│  SQL Agent    │  │  Retrieval   │  │   Planner    │
│  (Postgres)   │  │    Agent     │  │  (LangGraph) │
└──────┬────────┘  └──────┬───────┘  └──────┬───────┘
       ▼                  ▼                 ▼
   PostgreSQL         pgvector DB     Execution Plan
       └───────────────┬───────────────────┘
                       ▼
             ┌────────────────────┐
             │   Fusion Agent     │
             └─────────┬──────────┘
                       ▼
             ┌────────────────────┐
             │ Verification Agent │
             └─────────┬──────────┘
                       ▼
             ┌────────────────────┐
             │  Report Generator  │
             └─────────┬──────────┘
                       ▼
               Final Answer + Evidence
```

**Key design decisions**
- **Stateless backend** — all state (investigations, execution logs, embeddings) is stored in PostgreSQL.
- **Agents as functions** — each agent (SQL, Retrieval, Planner, Fusion, Verification) is a deterministic module with a defined input/output contract, not a freeform reasoning loop.
- **Evidence-first** — no output is produced without backing SQL results or retrieved document chunks.

## Database Design

| Table | Purpose |
|---|---|
| `business_data` (customers, orders, products, revenue, support_tickets) | SQL analytics layer used by the SQL Agent |
| `documents` | Unstructured content chunks with `VECTOR(1536)` embeddings (pgvector), plus `source`, `department`, `timestamp` metadata |
| `execution_logs` | Per-step trace: query id, step, input, output, latency, tokens, success — powers observability |
| `investigations` | Stores each question, its generated plan, and the final report |

## Project Layout

```
backend/    → FastAPI application (routing, endpoints)
core/       → agent logic: Intent Router, Planner (LangGraph), SQL Agent,
              Retrieval Agent, Fusion Agent, Verification Agent, Report Generator
database/   → Postgres/pgvector schema and data access layer
ingestion/  → document chunking + embedding pipeline (e.g. ingestion/rag.py)
frontend/   → Streamlit UI (query box, live execution steps, SQL/doc viewers, report)
docker/     → containerization assets (Postgres + pgvector, backend, frontend)
docs/       → architecture docs, API spec, evaluation reports
tests/      → automated tests
```

## How a Query Flows Through the System

1. **Intent Router** classifies the question — e.g. `"How many users"` → SQL only, `"Why did revenue drop"` → hybrid, `"Explain this issue"` → retrieval only.
2. **Planner** (LangGraph) turns the routed intent into a structured, explicit step list (no free-form text) — e.g. *query sales table → retrieve release notes → fetch support tickets*.
3. **SQL Agent** generates, validates, and executes read-only SQL against `business_data` (writes/deletes/updates are blocked).
4. **Retrieval Agent** runs hybrid search (BM25 keyword + pgvector similarity) over `documents` and returns the top-scoring chunks.
5. **Fusion Agent** combines SQL results and retrieved chunks into a unified evidence graph (e.g. *"Revenue down 12% — supported by: revenue table, 120 support tickets, a release note bug, customer emails"*).
6. **Verification Agent** checks that every claim in the draft answer maps back to a SQL result or document chunk, rejecting anything unsupported.
7. **Report Generator** produces the final structured report: executive summary, root causes, evidence, timeline, metrics, recommendations, and an evidence-based confidence score.

## Build Status

This project is being built in phases. **Phases 0–14 are complete**:

- [x] Phase 0–1: System design and architecture
- [x] Phase 2: Repo structure and commit strategy
- [x] Phase 3: Data layer — synthetic enterprise dataset with causal structure (e.g. a product bug → support ticket spike → negative emails → refunds → revenue drop)
- [x] Phase 4: Document ingestion pipeline (chunking → embeddings → pgvector)
- [x] Phase 5: Intent Router
- [x] Phase 6: Planner Agent (LangGraph)
- [x] Phase 7: SQL Agent (with read-only safety guardrails)
- [x] Phase 8: Retrieval Agent (hybrid BM25 + pgvector search)
- [x] Phase 9: Fusion Agent
- [x] Phase 10: Verification Agent
- [x] Phase 11: Report Generator
- [x] Phase 12: FastAPI backend (`/query`, `/investigation/{id}`, `/logs/{id}`, `/upload`, `/health`)
- [x] Phase 13: Streamlit UI
- [x] Phase 14: Observability layer (full step-by-step execution logging)

**Remaining / roadmap:**

- [ ] Phase 15: Evaluation framework (SQL correctness, retrieval precision, hallucination rate, consistency, latency, cost-per-query)
- [ ] Phase 16: Docker Compose for one-command startup (backend + Postgres/pgvector + frontend)
- [ ] Phase 17: Polish — architecture diagram, demo GIF, system design doc, API spec, evaluation report

## Tech Stack

- **Agent orchestration:** LangGraph
- **Backend API:** FastAPI
- **Frontend:** Streamlit
- **Database:** PostgreSQL with the `pgvector` extension
- **Embeddings:** OpenAI embeddings
- **Retrieval:** Hybrid search (BM25 + vector similarity)
- **Containerization:** Docker

## Prerequisites

- Python 3.10+
- PostgreSQL with the `pgvector` extension enabled
- An OpenAI API key (for embeddings and LLM reasoning)
- Docker (optional, for containerized setup — see Phase 16 in the roadmap)

## Setup

1. **Clone the repository**
   ```bash
   git clone https://github.com/saeee2510/enterprise-autonomous-intelligence-platform.git
   cd enterprise-autonomous-intelligence-platform
   ```

2. **Create a virtual environment and install dependencies**
   ```bash
   python -m venv venv
   source venv/bin/activate   # On Windows: venv\Scripts\activate
   pip install -r requirements.txt
   ```

3. **Configure environment variables**
   ```bash
   cp .env.example .env
   ```
   Fill in at minimum:
   ```env
   DATABASE_URL=postgresql://user:password@localhost:5432/enterprise_ai
   OPENAI_API_KEY=your_openai_api_key
   ```

4. **Set up the database**

   Create the database, enable `pgvector`, and apply the schema for `business_data`, `documents`, `execution_logs`, and `investigations` from `database/`.

## Running the Project

**Backend**
```bash
cd backend
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

**Frontend**
```bash
cd frontend
streamlit run app.py
```

**Verify the embedding pipeline**
```bash
python test_embedding.py
```
This calls `ingestion.rag.get_embedding(...)` and prints the resulting embedding's dimensionality — a quick sanity check that the ingestion/embedding setup is working.

## API Endpoints

| Method | Endpoint | Description |
|---|---|---|
| POST | `/query` | Submit a natural-language business question |
| GET | `/investigation/{id}` | Retrieve a past investigation's plan and report |
| GET | `/logs/{id}` | Retrieve the full execution trace for a query |
| POST | `/upload` | Ingest a new document into the pipeline |
| GET | `/health` | Health check |

## Contributing

Contributions are welcome! Please open an issue to discuss proposed changes, or submit a pull request.

## License

See the [LICENSE](./LICENSE) file.
