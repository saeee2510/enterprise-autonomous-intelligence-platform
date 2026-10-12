from core import verification_agent
from core.verification_agent import extract_dates, extract_numbers, verify

SQL = [{"evidence_id": "sql:1", "action": "EU net revenue before and after release",
        "columns": ["period", "net_revenue", "change_pct"],
        "rows": [["pre", 132253.0, None], ["post", 97843.21, -26.02]], "row_count": 2}]
DOCS = [{"evidence_id": "doc:1", "source": "release_3_2.txt", "department": "release_notes",
         "content": "Product Release Notes v3.2. Release Date: April 15 2025. "
                    "European customers reported duplicate payment attempts."}]


def _fused(*claims):
    return {"claims": [{"id": f"c{i}", "type": t, "statement": s, "evidence_ids": e}
                       for i, (t, s, e) in enumerate(claims, 1)]}


def _status(result):
    return [c["status"] for c in result["claims"]]


def test_extract_numbers():
    assert extract_numbers("Revenue fell 26.0% to $97,843.21 after v3.2") == ["26.0", "97843.21", "3.2"]


def test_grounded_sql_number_is_supported():
    r = verify(_fused(("fact", "EU net revenue fell 26% after the release", ["sql:1"])), SQL, DOCS, use_judge=False)
    assert _status(r) == ["supported"]


def test_hallucinated_number_is_rejected():
    r = verify(_fused(("fact", "EU net revenue fell 40% after the release", ["sql:1"])), SQL, DOCS, use_judge=False)
    assert _status(r) == ["unsupported"]
    assert r["claims"][0]["ungrounded_numbers"] == ["40"]


def test_missing_or_fake_citation_is_rejected():
    r = verify(_fused(("fact", "Refunds increased", []),
                      ("fact", "Refunds increased", ["doc:9"])), SQL, DOCS, use_judge=False)
    assert _status(r) == ["unsupported", "unsupported"]


def test_document_claim_needs_review():
    r = verify(_fused(("fact", "Release v3.2 shipped on April 15 2025", ["doc:1"])), SQL, DOCS, use_judge=False)
    assert _status(r) == ["needs_review"]


def test_confidence_and_rates():
    r = verify(_fused(("fact", "EU revenue fell 26%", ["sql:1"]),
                      ("fact", "EU revenue fell 40%", ["sql:1"])), SQL, DOCS, use_judge=False)
    assert r["confidence"] == 0.5
    assert r["unsupported_rate"] == 0.5


def _with_fake_judge(response, fn):
    original = verification_agent.llm.chat_json
    verification_agent.llm.chat_json = lambda messages, temperature=0.0: (response, None)
    try:
        return fn()
    finally:
        verification_agent.llm.chat_json = original


def test_judge_settles_document_claims():
    fused = _fused(("fact", "Release v3.2 shipped on April 15 2025", ["doc:1"]),
                   ("inference", "Release v3.2 caused APAC latency", ["doc:1"]))
    fused["summary"] = "EU revenue fell after release v3.2."
    judge = {"claims": [{"id": "c1", "verdict": "supported", "reason": "stated in release notes"},
                        {"id": "c2", "verdict": "unsupported", "reason": "doc says nothing about APAC"}],
             "issues": []}
    r = _with_fake_judge(judge, lambda: verify(fused, SQL, DOCS))
    assert _status(r) == ["supported", "unsupported"]
    assert r["summary_consistent"] is True


def test_contradicted_summary_halves_confidence():
    fused = _fused(("fact", "EU net revenue fell 26%", ["sql:1"]))
    fused["summary"] = "EU revenue rose sharply."
    judge = {"claims": [], "issues": [
        {"type": "direction", "severity": "high", "summary_statement": "EU revenue rose sharply",
         "sql_values": "change_pct -26.02", "explanation": "SQL shows a decline"}]}
    r = _with_fake_judge(judge, lambda: verify(fused, SQL, DOCS))
    assert r["summary_consistent"] is False
    assert r["confidence"] == 0.5


def test_extract_dates_handles_document_formats():
    text = ("Release Date: April 15 2025. Hotfix on May 2, 2025. "
            "Incident between March 10 and March 14 2025.")
    assert extract_dates(text) == {"2025-04-15", "2025-05-02", "2025-03-10", "2025-03-14"}


def test_timeline_event_with_wrong_date_is_dropped():
    from core.verification_agent import verify_timeline
    docs = {"doc:1": DOCS[0]}
    kept, dropped = verify_timeline(
        [{"date": "2025-04-15", "event": "Release v3.2", "evidence_ids": ["doc:1"]},
         {"date": "2025-03-10", "event": "Release v3.2", "evidence_ids": ["doc:1"]}],
        {}, docs)
    assert [t["date"] for t in kept] == ["2025-04-15"]
    assert [t["date"] for t in dropped] == ["2025-03-10"]


def test_vague_or_low_severity_issues_do_not_block():
    from core.verification_agent import classify_issues
    consistent, blocking, notes = classify_issues([
        {"type": "wording", "severity": "high", "sql_values": "x", "explanation": "says correlation"},
        {"type": "magnitude", "severity": "low", "sql_values": "x", "explanation": "minor"},
        {"type": "direction", "severity": "high", "sql_values": "", "explanation": "no values quoted"},
    ])
    assert consistent is True and blocking == [] and len(notes) == 3


def test_iso_dates_are_not_read_as_numbers():
    assert extract_numbers("Revenue from 2025-03-01 to 2025-05-31 was 589180") == ["589180"]


def test_summary_with_llm_arithmetic_is_flagged():
    fused = _fused(("fact", "EU net revenue fell 26%", ["sql:1"]))
    fused["summary"] = "Total EU revenue was 1,000,000.0 over the period."
    r = verify(fused, SQL, DOCS, use_judge=False)
    assert r["summary_consistent"] is False
    assert r["consistency_issues"][0]["type"] == "ungrounded_number"


def test_summary_numbers_from_the_question_are_allowed():
    fused = _fused(("fact", "EU net revenue fell 26%", ["sql:1"]))
    fused["summary"] = "Between 2025-04-15 and 2025-04-28 EU revenue fell 26%."
    fused["query"] = "What happened to EU revenue in the 14 days from 2025-04-15 to 2025-04-28?"
    fused["summary"] += " The 14-day window shows the drop."
    assert verify(fused, SQL, DOCS, use_judge=False)["summary_consistent"] is True


WEEKLY = [{"evidence_id": "sql:1", "action": "EU weekly net revenue",
           "columns": ["week", "net_revenue"],
           "rows": [["2025-03-31", 67292.0], ["2025-04-21", 45015.0], ["2025-04-28", 48211.0]],
           "row_count": 3}]


def test_written_dates_are_not_read_as_numbers():
    assert extract_numbers("Billing tickets rose from 6 on April 7, 2025 to 34 in March 2025") == ["6", "34"]


def test_claim_with_written_week_dates_is_supported():
    r = verify(_fused(("fact", "EU revenue fell from 67292.0 on March 31, 2025 to 45015.0 on April 21, 2025",
                       ["sql:1"])), WEEKLY, [], use_judge=False)
    assert _status(r) == ["supported"]


def test_claim_with_a_date_not_in_evidence_is_rejected():
    r = verify(_fused(("fact", "EU revenue was 45015.0 on April 22, 2025", ["sql:1"])),
               WEEKLY, [], use_judge=False)
    assert _status(r) == ["unsupported"]
    assert "2025-04-22" in r["claims"][0]["reason"]


def test_difference_and_percent_change_of_stated_values_are_allowed():
    r = verify(_fused(("fact", "EU revenue fell from 67292.0 to 45015.0, a decrease of 22277.0 (33.1%)",
                       ["sql:1"])), WEEKLY, [], use_judge=False)
    assert _status(r) == ["supported"]


def test_arithmetic_on_values_not_stated_is_rejected():
    # 22277 is 67292 - 45015, but the claim never states those two values
    r = verify(_fused(("fact", "EU revenue fell by 22277.0", ["sql:1"])), WEEKLY, [], use_judge=False)
    assert _status(r) == ["unsupported"]


def test_summary_dates_must_come_from_evidence_or_question():
    fused = _fused(("fact", "EU net revenue fell 26%", ["sql:1"]))
    fused["summary"] = "EU revenue fell 26% after 2025-04-15."
    fused["query"] = "What happened to EU revenue?"
    r = verify(fused, SQL, DOCS, use_judge=False)
    assert r["summary_consistent"] is True  # 2025-04-15 is stated in the release notes (DOCS)
    fused["summary"] = "EU revenue fell 26% after 2025-06-01."
    assert verify(fused, SQL, DOCS, use_judge=False)["summary_consistent"] is False


def test_direction_words_must_match_numbers():
    from core.verification_agent import direction_errors
    assert direction_errors("refunds rose from 6866.0 on April 21 to 4622.0, a 33.1% drop")
    assert direction_errors("revenue fell from 246409.0 in April to 264318.0 in May")
    assert not direction_errors("Revenue fell from 67292.0 on March 31, 2025 to 45015.0 on April 21, 2025")
    assert not direction_errors("Billing tickets rose from 6 on April 7, 2025 to 34 on April 14, 2025")


def test_summary_with_wrong_direction_is_inconsistent():
    fused = _fused(("fact", "EU net revenue fell 26%", ["sql:1"]))
    fused["summary"] = "EU net revenue rose from 132253.0 to 97843.21."
    r = verify(fused, SQL, DOCS, use_judge=False)
    assert r["summary_consistent"] is False
    assert r["consistency_issues"][0]["type"] == "direction"


def test_numbers_are_checked_against_the_row_for_the_named_date():
    tickets = [{"evidence_id": "sql:1", "action": "EU weekly billing tickets", "columns": ["week", "tickets"],
                "rows": [["2025-04-07", 6], ["2025-04-14", 34], ["2025-04-21", 9]], "row_count": 3}]
    ok = verify(_fused(("fact", "Billing tickets were 34 in the week of April 14, 2025", ["sql:1"])),
                tickets, [], use_judge=False)
    assert _status(ok) == ["supported"]
    # 9 exists in the table (April 21) but not in the April 14 row
    bad = verify(_fused(("fact", "Billing tickets were 9 in the week of April 14, 2025", ["sql:1"])),
                 tickets, [], use_judge=False)
    assert _status(bad) == ["unsupported"]
