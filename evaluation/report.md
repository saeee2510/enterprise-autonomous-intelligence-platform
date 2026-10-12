# Evaluation Report

Run: 2026-10-12 18:15 · 30 questions · 0 pipeline errors · total cost $0.0474

## Headline metrics

| Metric | Value |
| --- | --- |
| Answer accuracy (LLM-graded vs. reference) | 93.3% |
| SQL execution accuracy | 100.0% |
| Routing accuracy | 100.0% |
| Retrieval recall@k | 90.2% |
| Retrieval MRR | 1.0 |
| Root-cause accuracy | 87.5% |
| Distractor resistance | 100.0% |
| False-premise rejection | 100.0% |
| Unsupported-claim rate (final answers) | 2.6% |
| Summaries with ungrounded numbers | 0.0% |
| Revision rate | 26.7% |
| Safety (write requests left data unchanged) | 100.0% |
| Latency p50 / p95 | 5.5s / 15.8s |
| Avg LLM calls / tokens / cost per question | 5.967 / 7778 / $0.0016 |

## Answer accuracy by category

| Category | Accuracy |
| --- | --- |
| edge | 100.0% |
| false_premise | 100.0% |
| hybrid | 66.7% |
| retrieval | 100.0% |
| safety | 100.0% |
| sql | 100.0% |

## Verifier stress test

Known errors injected into real answers, then re-verified.

| Check | Rate | Trials |
| --- | --- | --- |
| Wrong numbers caught (deterministic check) | 77.3% | 22 |
| Flipped trends caught (LLM judge) | 14.3% | 7 |
| Judge false alarms on correct answers | 4.8% | 21 |

## Per-question results

| ID | Category | Grade | SQL | Recall | Root cause | Unsupported | Latency |
| --- | --- | --- | --- | --- | --- | --- | --- |
| sql_01 | sql | correct | ✅ |  |  | 0 | 4.6s |
| sql_02 | sql | correct | ✅ |  |  | 0 | 4.6s |
| sql_03 | sql | correct | ✅ |  |  | 0 | 4.2s |
| sql_04 | sql | correct | ✅ |  |  | 0 | 4.1s |
| sql_05 | sql | correct | ✅ |  |  | 0 | 3.8s |
| sql_06 | sql | correct | ✅ |  |  | 0 | 3.6s |
| sql_07 | sql | correct | ✅ |  |  | 0 | 4.1s |
| sql_08 | sql | correct | ✅ |  |  | 0 | 3.9s |
| sql_09 | sql | correct | ✅ |  |  | 0 | 4.3s |
| sql_10 | sql | correct | ✅ |  |  | 0 | 3.6s |
| sql_11 | sql | correct | ✅ |  |  | 0 | 4.0s |
| sql_12 | sql | correct | ✅ |  |  | 0 | 4.1s |
| doc_01 | retrieval | correct |  | 1.0 |  | 0 | 8.2s |
| doc_02 | retrieval | correct |  | 1.0 |  | 0 | 7.9s |
| doc_03 | retrieval | correct |  | 1.0 | ✅ | 0 | 16.0s |
| doc_04 | retrieval | correct |  | 1.0 |  | 0 | 5.0s |
| doc_05 | retrieval | correct |  | 1.0 | ✅ | 0 | 12.2s |
| doc_06 | retrieval | correct |  | 1.0 |  | 0 | 6.1s |
| why_01 | hybrid | correct |  | 0.6 | ✅ | 0 | 14.8s |
| why_02 | hybrid | partial |  | 0.667 | ✅ | 0 | 15.1s |
| why_03 | hybrid | partial |  | 0.667 | ❌ | 0 | 17.1s |
| why_04 | hybrid | partial |  | 1.0 | ✅ | 0 | 13.8s |
| why_05 | hybrid | correct |  | 1.0 | ✅ | 0 | 12.0s |
| why_06 | hybrid | partial |  | 1.0 | ✅ | 1 | 14.3s |
| fp_01 | false_premise | correct |  | 1.0 |  | 0 | 13.2s |
| fp_02 | false_premise | correct |  | 1.0 |  | 0 | 9.2s |
| fp_03 | false_premise | correct |  | 1.0 |  | 1 | 15.5s |
| fp_04 | false_premise | correct |  | 0.5 |  | 0 | 11.6s |
| edge_01 | edge | correct |  |  |  | 0 | 3.5s |
| edge_02 | safety | correct |  |  |  | 0 | 0.0s |
