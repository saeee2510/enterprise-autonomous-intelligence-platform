import json
from pathlib import Path

from core.sql_agent import validate_sql
from evaluation import metrics as M

BENCHMARK = [json.loads(l) for l in Path("evaluation/benchmark.jsonl").read_text().splitlines() if l.strip()]


def test_benchmark_is_well_formed():
    ids = [i["id"] for i in BENCHMARK]
    assert len(ids) == len(set(ids)) == 30
    for item in BENCHMARK:
        assert item["category"] in {"sql", "retrieval", "hybrid", "false_premise", "edge", "safety"}
        assert item.get("gold_sql") or item.get("reference_answer"), item["id"]


def test_every_gold_query_passes_the_safety_validator():
    for item in BENCHMARK:
        if item.get("gold_sql"):
            validate_sql(item["gold_sql"])


def test_sql_execution_accuracy_compares_results_not_query_text():
    system = [{"rows": [["EU", 897.0]], "error": None}]
    assert M.sql_execution_correct([[897]], system)
    assert not M.sql_execution_correct([[900]], system)
    assert M.sql_execution_correct([["EU"]], system)


def test_text_answers_need_whole_word_match():
    system = [{"rows": [["analysis complete"]], "error": None}]
    assert not M.sql_execution_correct([["NA"]], system)
    assert M.sql_execution_correct([["NA"]], [{"rows": [["NA", 1.0]], "error": None}])


def test_failed_sql_results_are_ignored():
    assert not M.sql_execution_correct([[897]], [{"rows": [[897]], "error": "boom"}])


def test_retrieval_recall_and_mrr():
    s = M.retrieval_scores(["a.txt", "b.txt"], ["x.txt", "a.txt", "y.txt"])
    assert s == {"recall": 0.5, "mrr": 0.5}
    assert M.retrieval_scores(None, ["a.txt"]) is None


def test_keyword_check_detects_distractors():
    r = M.keyword_check("Release v3.2 retry bug caused duplicate charges",
                        [["3.2"], ["retry", "duplicate"]], ["cache", "campaign"])
    assert r == {"root_cause_hit": True, "distractor_hits": []}
    r = M.keyword_check("The spring campaign caused it", [["3.2"]], ["campaign"])
    assert r == {"root_cause_hit": False, "distractor_hits": ["campaign"]}


def test_ungrounded_summary_numbers():
    sql = [{"rows": [["2025-04-21", 45015.0]], "error": None}]
    assert M.ungrounded_summary_numbers("Revenue fell to 45015 by 2025-04-21", sql, []) == []
    assert M.ungrounded_summary_numbers("Revenue fell to 12345", sql, []) == ["12345"]


def test_stress_helpers():
    assert M.perturb_first_number("EU revenue fell 26% to 45015") == "EU revenue fell 39% to 45015"
    assert M.perturb_first_number("no numbers here") is None
    assert M.flip_direction("Revenue in Europe dropped sharply.") == "Revenue in Europe rose sharply."
    assert M.flip_direction("Tickets increased after the release.") == "Tickets decreased after the release."
    assert M.flip_direction("Everything was flat.") is None


def test_percentile():
    assert M.percentile([1, 2, 3, 4], 50) == 2.5
    assert M.percentile([], 50) is None


def test_gold_references_are_plain_english():
    from evaluation.run_eval import format_reference
    assert format_reference(["region"], [["NA"]]) == "The correct answer is NA."
    assert format_reference(["region", "customers"], [["EU", 100], ["NA", 100]]) == \
        "The correct answer is: region = EU; customers = 100 | region = NA; customers = 100."


def test_gold_in_text():
    assert M.gold_in_text([["NA"]], "The North America (NA) region had the highest net revenue, totaling 326182.0.")
    assert M.gold_in_text([[897]], "There were 897 support tickets in total.")
    assert not M.gold_in_text([[897]], "There were 887 support tickets in total.")
