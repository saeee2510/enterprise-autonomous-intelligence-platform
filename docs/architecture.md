# Enterprise Autonomous Intelligence Platform (EAIP)

## 1. System Overview

EAIP is a hybrid AI intelligence system that combines:
- Structured SQL analytics
- Unstructured document retrieval
- Multi-agent reasoning pipeline
- Evidence-based verification
- Fully traceable execution logs

The system is designed for deterministic, reproducible business intelligence.

---

## 2. Core Design Principles

### 2.1 Stateless Backend Rule
- Backend does NOT store runtime state in memory
- All state is persisted in Postgres
- Every request is independent and reproducible

---

### 2.2 Deterministic Agent Design
Agents are NOT autonomous loops.

Each agent is a deterministic module:

Input → Processing Logic → Structured Output

No free-form chaining without orchestration.

---

### 2.3 Evidence-First Constraint
The system cannot generate final answers without evidence.

Evidence types:
- SQL query results
- Retrieved document chunks

Every claim must map to at least one evidence source.

---

### 2.4 Execution Transparency
Every query produces a full execution trace:

- Intent classification
- Execution plan
- SQL queries executed
- Retrieved documents
- Fusion reasoning
- Verification results

Stored in `execution_logs`.

---

## 3. High-Level Architecture
