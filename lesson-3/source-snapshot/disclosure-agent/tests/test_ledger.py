"""Synthetic fixtures only. No teacher reference or production source data."""
from copy import deepcopy

from disclosure_agent.ledger import merge


def notice(id="s1", code="600887", kind="initial", published="2030-01-01", **fields):
    data = dict(notice_kind=kind, report_period="2029年度", notice_number=f"2030-{id}",
                related_notice_number=None, meeting_date="2030-02-01", start_time="14:00",
                end_time="15:00", question_deadline_date="2030-01-30", question_deadline_time="16:00",
                participation_url="https://example.invalid/meeting", previous_meeting_date=None,
                previous_start_time=None, previous_end_time=None, review_notes=[],
                meeting_evidence={"page": 1, "quote": "合成会议安排"}, deadline_evidence=None,
                relation_evidence=None)
    data.update(fields)
    return dict(id=id, stock_code=code, company="Synthetic company", publication_date=published,
                pdf_sha256=f"synthetic-hash-{id}", extraction=data, model="synthetic", revision_reason=None)


def change(id="s2", **fields):
    base = dict(related_notice_number="2030-s1", relation_evidence={"page": 1, "quote": "合成原通知2030-s1"},
                meeting_date="2030-02-02", question_deadline_date=None, question_deadline_time=None)
    base.update(fields)
    return notice(id, kind="change", published="2030-01-05", **base)


def run(records, previous=None, coverage=None, run_id="r1", as_of="2030-01-10"):
    return merge(previous or {}, records, coverage or {
        "600887": dict(status="complete", query_complete=True, processing_complete=True)
    }, run_id, as_of)


def event(state):
    return state["events"]["600887:s1"]


def test_reschedule_is_same_event_retains_sources_history_and_is_idempotent():
    first, _, _ = run([notice()])
    state, changes, issues = run([change()], first)
    assert not issues and len(changes) == 1 and len(state["events"]) == 1
    assert event(state)["meeting_date"] == "2030-02-02"
    assert event(state)["source_ids"] == ["s1", "s2"]
    assert event(state)["history"][0]["before"]["meeting_date"] == "2030-02-01"
    repeated, changes, _ = run([notice(), change()], state, run_id="r2", as_of="2030-01-11")
    assert changes == [] and repeated["events"] == state["events"]


def test_different_periods_are_not_merged_and_wrong_period_change_is_reviewed():
    state, _, _ = run([notice(), notice("s3", report_period="2030一季度")])
    revised, changes, issues = run([change(report_period="2030一季度")], state)
    assert len(revised["events"]) == 2 and not changes
    assert issues[0]["reason"] == "report_period_conflict"


def test_missing_or_ambiguous_original_requires_review():
    _, _, issues = run([change()])
    assert issues[0]["reason"] == "ambiguous_or_missing_original_notice"
    state, _, issues = run([notice(), notice("dup", notice_number="2030-s1"), change()])
    assert len(state["events"]) == 2 and issues[0]["reason"] == "ambiguous_or_missing_original_notice"


def test_late_old_announcement_does_not_roll_back_new_schedule():
    state, _, _ = run([notice(), change()])
    delayed = change("s0", meeting_date="2030-02-03")
    delayed["publication_date"] = "2030-01-03"
    updated, changes, _ = run([delayed], state)
    assert event(updated)["meeting_date"] == "2030-02-02" and changes == []


def test_cancel_and_unknown_postponement_clear_active_time_but_keep_history():
    for kind in ("cancelled", "postponed"):
        initial, _, _ = run([notice()])
        update = change(meeting_date=None, start_time=None, end_time=None)
        update["extraction"]["notice_kind"] = kind
        state, _, _ = run([update], initial)
        assert event(state)["status"] == kind
        assert all(event(state)[field] is None for field in ("meeting_date", "start_time", "end_time"))
        assert event(state)["history"][0]["before"]["meeting_date"] == "2030-02-01"


def test_null_missing_values_do_not_clear_unchanged_fields():
    state, _, _ = run([notice(), change(start_time=None, end_time=None, participation_url=None)])
    assert event(state)["start_time"] == "14:00"
    assert event(state)["participation_url"] == "https://example.invalid/meeting"


def test_unchanged_claim_keeps_deadline_pending_but_updates_meeting():
    update = change(question_deadline_date="2030-01-31", deadline_evidence={"page": 2, "quote": "提问截止改为2030-01-31"})
    update["source_flags"] = {"other_fields_unchanged": True}
    state, changes, issues = run([notice(), update])
    assert event(state)["meeting_date"] == "2030-02-02"
    assert event(state)["question_deadline_date"] == "2030-01-30"
    assert event(state)["pending_fields"]["question_deadline_date"][0]["candidate"] == "2030-01-31"
    assert issues[0]["reason"] == "other_fields_unchanged_conflict"
    assert "last_success" not in state["companies"]["600887"]
    _, changes, _ = run([notice(), update], state)
    assert changes == []


def test_explicit_deadline_change_applies_and_implicit_change_needs_review():
    explicit = change(question_deadline_date="2030-01-31", deadline_evidence={"page": 1, "quote": "提问征集截止调整至2030-01-31"})
    state, _, issues = run([notice(), explicit])
    assert not issues and event(state)["question_deadline_date"] == "2030-01-31"
    implicit = deepcopy(explicit)
    implicit["extraction"]["deadline_evidence"]["quote"] = "提问截止2030-01-31"
    state, _, issues = run([notice(), implicit])
    assert issues and event(state)["question_deadline_date"] == "2030-01-30"


def test_source_hash_change_preserves_old_record_and_conflicting_version():
    first, _, _ = run([notice()])
    altered = notice(meeting_date="2030-04-01")
    altered["pdf_sha256"] = "changed-source-bytes"
    state, changes, issues = run([altered], first)
    assert not changes and event(state)["meeting_date"] == "2030-02-01"
    assert state["notices"]["s1"]["versions"][0]["pdf_sha256"] == "changed-source-bytes"
    assert issues[0]["reason"] == "source_hash_changed"
    repeated, _, _ = run([altered], state)
    assert len(repeated["notices"]["s1"]["versions"]) == 1


def test_extraction_revision_is_not_market_change_and_is_idempotent():
    initial, _, _ = run([notice()])
    revised = notice(start_time="13:00")
    revised["revision_reason"] = "model_changed"
    state, changes, _ = run([revised], initial)
    assert changes[0]["kind"] == "extraction_revision"
    assert state["notices"]["s1"]["versions"][0]["extraction"]["start_time"] == "14:00"
    _, changes, _ = run([revised], state)
    assert not changes


def test_partial_failure_keeps_failed_company_and_success_watermark():
    initial, _, _ = run([notice()])
    before = deepcopy(initial)
    coverage = {"600887": dict(status="failed", query_complete=False, processing_complete=False),
                "688246": dict(status="complete", query_complete=True, processing_complete=True)}
    state, changes, issues = run([change(), notice("other", code="688246")], initial, coverage, as_of="2030-01-11")
    assert initial == before
    assert event(state) == event(initial)
    assert state["companies"]["600887"]["last_success"] == "2030-01-10"
    assert state["companies"]["688246"]["last_success"] == "2030-01-11"
    assert all(change["stock_code"] == "688246" for change in changes)
    recovered, changes, _ = run([], state, as_of="2030-01-12")
    assert event(recovered)["meeting_date"] == "2030-02-02"


def test_past_meeting_keeps_scheduled_semantics_and_completed_notice_is_excluded():
    state, _, issues = run([notice(), notice("after", kind="completed")], as_of="2031-01-01")
    assert not issues and len(state["events"]) == 1
    assert event(state)["status"] == "scheduled"


def test_late_intermediate_notice_cannot_override_latest_explicit_date():
    latest = change(previous_meeting_date="2030-02-01")
    first, _, _ = run([notice(), latest])
    delayed = change("older", meeting_date="2030-02-03", previous_meeting_date="2030-02-01")
    delayed["publication_date"] = "2030-01-03"
    state, changes, _ = run([delayed], first)
    assert event(state)["meeting_date"] == "2030-02-02" and changes == []


def test_later_explicit_deadline_resolves_pending_and_allows_watermark():
    conflict = change(question_deadline_date="2030-01-31")
    conflict["source_flags"] = {"other_fields_unchanged": True}
    first, _, _ = run([notice(), conflict])
    correction = change("s3", question_deadline_date="2030-02-01",
                        deadline_evidence={"page": 1, "quote": "提问截止变更为2030-02-01"})
    correction["publication_date"] = "2030-01-06"
    state, _, issues = run([correction], first)
    assert event(state)["pending_fields"] == {} and issues == []
    assert state["companies"]["600887"]["last_success"] == "2030-01-10"


def test_explicit_correction_can_confirm_old_value_and_close_pending():
    conflict = change(question_deadline_date="2030-01-31")
    first, _, _ = run([notice(), conflict])
    correction = change("s3", question_deadline_date="2030-01-30",
                        deadline_evidence={"page": 1, "quote": "提问截止变更回2030-01-30"})
    correction["publication_date"] = "2030-01-06"
    state, changes, issues = run([correction], first)
    assert not event(state)["pending_fields"] and not issues and not changes


def test_deferred_extraction_revision_survives_failure_and_cached_recovery():
    initial, _, _ = run([notice(meeting_date="2030-01-20")])
    revised = notice(meeting_date="2030-01-21")
    revised["revision_reason"] = "model_changed"
    failed_coverage = {"600887": dict(status="failed", query_complete=False, processing_complete=False)}
    failed, changes, _ = run([revised], initial, failed_coverage)
    assert changes == [] and event(failed)["meeting_date"] == "2030-01-20"
    assert failed["notices"]["s1"]["extraction"]["meeting_date"] == "2030-01-21"
    failed_again, changes, _ = run([], failed, failed_coverage)
    assert changes == []
    recovered, changes, _ = run([], failed_again)
    assert event(recovered)["meeting_date"] == "2030-01-21"
    assert len(changes) == 1 and changes[0]["kind"] == "extraction_revision"
    repeated, changes, _ = run([], recovered)
    assert changes == []
    _, changes, _ = run([change()], repeated)
    assert len(changes) == 1 and changes[0]["kind"] == "updated"
