# Enterprise Autonomous Intelligence Platform

A multi-agent system that answers business questions ("Why did revenue drop in Europe?") using both structured data (PostgreSQL) and unstructured documents (release notes, incident reviews, support tickets, emails), and backs every claim in its answer with a cited, verified source.

It is built as a deterministic LangGraph pipeline rather than an open-ended agent loop: each agent is a function with a fixed input/output contract, every claim is checked against the exact evidence it cites, and every run is logged and measured.

## Results

Measured on a 30-question benchmark (`evaluation/benchmark.jsonl`) covering SQL, document, root-cause, false-premise, edge, and safety questions:

| Metric | Result |
| --- | --- |
| Answer accuracy | **93.3%** |
| SQL execution accuracy | **100%** |
| False-premise rejection | **100%** |
| Routing accuracy | **100%** |
| Distractor resistance | **100%** |
| Root-cause accuracy | 87.5% |
| Retrieval recall@k / MRR | 90.2% / 1.0 |
| Unsupported claims in final answers | **2.6%** |
| Summaries with ungrounded numbers | **0%** |
| Safety (write requests left data unchanged) | **100%** |
| Latency p50 / p95 | 5.5s / 15.8s |
| Cost per question | ~$0.0016 |

Improvements driven by the evaluation (baseline → final):

| | Baseline | Final |
| --- | --- | --- |
| Answer accuracy | 83.3% | 93.3% |
| Unsupported-claim rate | 23.4% | 2.6% |
| Summaries with ungrounded numbers | 30% | 0% |
| SQL self-correction retries | 22 | 0 |
| Latency p95 | 23.4s | 15.8s |

Bugs the evaluation found that single-question testing never showed:

- **Timestamp boundary bug:** `created_at <= '2025-05-31'` silently dropped every row after midnight on the last day (887 tickets reported instead of 897). Fixed with half-open date ranges.
- **LLM arithmetic:** the fusion step summed weekly rows itself and produced invented totals. Fixed by allowing only verifiable arithmetic (see Verification).
- **SQL retry storm:** every first-attempt query using `ROUND(double precision, 2)` failed in Postgres. Fixing one prompt rule removed all 27 retries and about one LLM call per question.
- **Over-hedging:** after tightening verification, the system refused to state causes the documents stated explicitly. Fixed by separating "be skeptical of the question" from "trust stated evidence."

### Verifier stress test

Known errors are injected into real, finished answers and re-verified:

| Check | Result |
| --- | --- |
| Wrong numbers caught | 77.3% |
| Flipped trend words caught | 14.3% |
| Judge false alarms on correct answers | 4.8% |

Known limitation: a wrong number with no date beside it can coincidentally match another value in a large table, and a flipped trend word with no "from X to Y" numbers relies on the LLM judge, which is tuned for a low false-alarm rate rather than high recall.

## Architecture

```
                       ┌──── sql_agent ──────┐
    START → planner ───┤                     ├──→ fusion → verification ──→ report_generator → END
            │          └── retrieval_agent ──┘       ▲            │
            │                                        └─ revision ─┘  (at most once)
            └──→ refusal → END   (write requests)
```

| Node | What it does |
| --- | --- |
| `planner` | Turns the question into an explicit, validated plan of SQL and retrieval steps. Write requests ("delete…", "update…") are refused deterministically before any LLM or database call. |
| `sql_agent` | Generates SQL from an auto-profiled schema (columns, foreign keys, allowed values, date ranges). Independent SQL steps run concurrently. |
| `retrieval_agent` | Hybrid search: pgvector cosine + Postgres full-text candidates, scored with BM25 and cosine, fused with Reciprocal Rank Fusion, diversified with MMR. |
| `fusion` | An LLM writes the answer as atomic claims, each citing evidence IDs (`sql:1`, `doc:2`). |
| `verification` | Checks every claim and the summary against the cited evidence (below). |
| `revision` | If verification rejects a claim or finds a contradiction, the draft goes back to fusion once with the verifier's objections. |
| `report_generator` | Builds the final report from verified claims only; rejected claims are listed separately, never hidden. |

SQL and retrieval run in parallel, and the only cycle in the graph is bounded to one revision, so every run terminates.

## Verification

Deterministic checks (no LLM):

- **Citations:** every claim must cite evidence that exists.
- **Numbers:** every number must appear in the cited evidence, allowing for rounding. The only arithmetic allowed is a difference or percentage change between two grounded numbers stated in the same sentence, so "fell from 67,292 to 45,015, a 33.1% drop" is checkable. Derivations from arbitrary evidence values are not allowed, because with hundreds of values some pair would match almost any number by coincidence.
- **Dates:** dates are parsed as dates (`2025-04-21`, `April 21, 2025`, `March 10 and March 14 2025`) and must appear in the cited evidence. When a claim names a date, its numbers are checked against that date's rows only.
- **Direction:** "rose from X to Y" is rejected when Y < X.
- **Timeline:** events are kept only if their date is in the cited evidence.

LLM judge (only for what the deterministic checks can't settle):

- **Entailment:** is a document-based claim actually stated by the document it cites?
- **Consistency:** does the summary contradict the SQL numbers? Issues must be typed, rated by severity, and quote the contradicting values; only high-severity direction or magnitude errors block the answer.

## SQL safety

Layered so no single check has to be perfect:

1. Validation allows only a single `SELECT`/`WITH` statement and blocks write and DDL keywords and internal tables.
2. Connections are opened in Postgres `READ ONLY` mode, so the database itself rejects writes.
3. A 5-second statement timeout and a 200-row cap stop runaway queries.
4. Failed queries get one self-correction attempt with the database error.

## Observability

Every node logs latency, LLM calls, tokens, and cost to `execution_logs`, and every investigation is saved to `investigations`. Logging failures never break an investigation.

```
GET /logs/{trace_id}            per-step trace
GET /investigation/{trace_id}   saved question, plan, and report
```

## Data

`ingestion/synthetic_data.py` generates a seeded, deterministic dataset (March–May 2025) with a known causal story, so answers can be checked against ground truth:

- Release v3.2 (April 15) adds a buggy payment-retry mechanism → EU duplicate charges and failed checkouts → EU billing tickets spike → duplicate-charge refunds → EU net revenue drops → hotfix v3.2.1 (May 2) → recovery.
- Distractors the system must not blame: an APAC dashboard slowdown in March (no revenue impact) and a North America spring campaign in April (revenue up).

## Tech stack

Python · LangGraph · FastAPI · Streamlit · PostgreSQL · pgvector · OpenAI (GPT-4o-mini for the pipeline, GPT-4o for grading, text-embedding-3-small) · Docker (Postgres)

## Setup

Requirements: Python 3.10+, Docker, and an OpenAI API key.

```bash
git clone https://github.com/saeee2510/enterprise-autonomous-intelligence-platform.git
cd enterprise-autonomous-intelligence-platform
python -m venv venv
source venv/bin/activate          # Windows: venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env              # add your OPENAI_API_KEY

docker compose -f docker/docker-compose.yml up -d    # Postgres + pgvector on port 5450
python -m ingestion.seed_pipeline                     # business data + ground truth
python -m ingestion.ingest_document                   # embed documents
```

Run all commands from the project root.

## Usage

```bash
uvicorn backend.main:app --reload     # API on http://127.0.0.1:8000
streamlit run frontend/app.py         # UI on http://localhost:8501 (second terminal)
```

The UI shows the report, each claim's verification status, the SQL and document evidence, the execution plan, and per-step latency, tokens, and cost.

## Evaluation

```bash
python -m evaluation.run_eval                 # full benchmark (~5 minutes, ~$0.05)
python -m evaluation.run_eval --limit 5       # quick check
python -m evaluation.run_eval --ids why_01 fp_01
python -m evaluation.run_eval --no-stress     # skip the verifier stress test
```

Results are written to `evaluation/report.md` and `evaluation/results/`.

Grading: questions with an exact answer are graded deterministically (the gold SQL value must appear in both the system's SQL result and its summary). Open-ended questions are graded by GPT-4o against a reference answer, a different and stronger model than the one being graded, to reduce self-preference bias.

## Tests

```bash
python -m pytest tests
```

56 tests cover SQL safety, retrieval scoring, every verification check, planner validation and refusals, evaluation metrics, and full pipeline runs with fake LLM and database calls (no API key needed), including the parallel branches and the revision loop.

## Project structure

```
backend/      FastAPI app (/query, /investigation/{id}, /logs/{id}, /health)
core/         graph.py (LangGraph), planner, sql_agent, retrieval_agent,
              fusion_agent, verification_agent, report_generator,
              execution_logger, llm.py (OpenAI wrapper with cost tracking), db.py
database/     schema.sql
docker/       docker-compose.yml (Postgres + pgvector)
evaluation/   benchmark.jsonl, metrics.py, run_eval.py, report.md, results/
frontend/     Streamlit UI
ingestion/    synthetic_data.py, seed_pipeline.py, ingest_document.py, documents/
tests/        unit and pipeline tests
```

## Limitations and next steps

- The dataset is synthetic and small (about 10K rows, 8 documents). The next step is a larger corpus to test retrieval at scale.
- Open-ended "why" answers score partial credit 33% of the time, usually from comparing the wrong time periods.
- Execution accuracy can't catch a wrong SQL query on open-ended questions that have no gold query.
- Containerizing the backend and frontend in Docker Compose alongside Postgres.

## License

MIT
