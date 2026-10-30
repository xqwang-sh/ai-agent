import json
import hashlib
from pathlib import Path

import pytest
from disclosure_agent import extract, runner

HEADER = "公告编号：2031-001\n关于召开2031年半年度业绩说明会的公告\n"

def output():
    data = {key: None for key in extract.SCHEMA["required"]}
    data.update(notice_kind="initial", report_period="2031-H1", notice_number="2031-001", meeting_date="2031-09-20", start_time="14:00", end_time="15:00", review_notes=[], meeting_evidence={"page": 1, "quote": "会议召开时间：2031年9月20日14:00-15:00"})
    return data


def config(tmp_path):
    path = tmp_path / "config.json"
    path.write_text(json.dumps({"companies": [{"code": "111111", "name": "虚构甲公司"}, {"code": "222222", "name": "虚构乙公司"}], "models": ["test/model"], "strategy": "fixed"}))
    return path


def seed_publication(workspace, state, summary=None):
    generation = workspace / "runs" / "synthetic-seed"
    generation.mkdir(parents=True)
    artifacts = {}
    for name, value in {"state.json": {**state, "last_run_id": "synthetic-seed"}, "summary.json": {**(summary or {}), "run_id": "synthetic-seed"}, "calendar.html": "synthetic test"}.items():
        path = generation / name
        path.write_text(json.dumps(value))
        artifacts[name] = {"path": str(path.relative_to(workspace)), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
    (workspace / "current.json").write_text(json.dumps({"run_id": "synthetic-seed", "artifacts": artifacts}))


def test_evidence_rejects_wrong_explicit_year():
    assert not extract._date_in("2031-09-20", "会议召开时间：2030年9月20日14:00-15:00")
    assert extract._date_in("2031-09-20", "会议召开时间：2031年9月20日14:00-15:00")
    assert not extract._date_in("2030-09-20", "会议召开时间：9月20日14:00-15:00")
    assert not extract._date_in("2030-09-20", "2031年9月10日至9月20日")
    assert extract._date_in("2031-09-20", "2031年9月10日至9月20日")


def test_evidence_rejects_assembled_quote():
    data = output()
    data["meeting_evidence"]["quote"] = "重要提示：会议召开时间：2031年9月20日14:00-15:00"
    source = [HEADER + "重要提示：会议方式为电话。会议召开时间：2031年9月20日14:00-15:00"]
    assert "ungrounded_quote:meeting_evidence" in extract.validate_evidence(data, source)


def test_cannot_take_date_from_another_page():
    data = output()
    pages = [HEADER + "会议在第二页说明。", data["meeting_evidence"]["quote"]]
    assert "ungrounded_quote:meeting_evidence" in extract.validate_evidence(data, pages)


def test_non_calendar_fields_cannot_create_event():
    data = output()
    data["notice_kind"] = "completed"
    errors = extract.validate_evidence(data, [HEADER + data["meeting_evidence"]["quote"]])
    assert "non_calendar_field:meeting_date" in errors


def test_missing_time_stays_missing():
    data = output()
    data.update(end_time=None, meeting_evidence={"page": 1, "quote": "会议召开时间：2031年9月20日14:00"})
    assert not extract.validate_evidence(data, [HEADER + data["meeting_evidence"]["quote"]])


def test_runtime_cache_and_partial_failure_preserve_business_state(tmp_path, monkeypatch):
    calls = []
    failed = set()
    data = output()
    item = {"id": "900001", "stock_code": "111111", "company": "虚构甲公司", "title": "关于召开2031年半年度业绩说明会的公告", "publication_date": "2031-09-01", "pdf_sha256": "a" * 64, "pdf_path": str(tmp_path / "fictional.pdf"), "url": "https://example.invalid/fictional", "pages": [HEADER + data["meeting_evidence"]["quote"]]}

    class Source:
        def __init__(self, *args, **kwargs):
            pass

        def acquire(self, company, start, end):
            bad = company["code"] in failed
            return {"company": company, "status": "failed" if bad else "complete", "query_complete": not bad, "failed_items": [], "error": "simulated outage" if bad else None, "query": {}, "items": [item] if company["code"] == "111111" and not bad else []}

    def mocked_extract(*args, **kwargs):
        calls.append(True)
        receipt = tmp_path / "synthetic-model-receipt.json"
        receipt.write_text(json.dumps({"fictional_test": True, "usage": {"total_tokens": 13}}))
        return {"status": "accepted", "data": data, "model": "test/model", "attempts": [{"usage": {"total_tokens": 13}, "receipt_path": str(receipt)}], "errors": []}

    monkeypatch.setattr(runner, "CninfoSource", Source)
    monkeypatch.setattr(runner, "extract_notice", mocked_extract)
    workspace = tmp_path / "live"
    path = config(tmp_path)
    first = runner.run(path, workspace)
    assert first["status"] == "complete" and first["event_count"] == 1
    assert first["changes"][0]["kind"] == "baseline"
    assert first["model_calls"] == 1 and first["usage"]["known_total_tokens"] == 13
    second = runner.run(path, workspace)
    assert second["model_calls"] == 0 and second["changes"] == [] and len(calls) == 1
    old = json.loads((workspace / "state.json").read_text())
    failed.add("111111")
    third = runner.run(path, workspace)
    state = json.loads((workspace / "state.json").read_text())
    assert third["status"] == "incomplete"
    assert state["events"] == old["events"]
    assert state["companies"]["111111"]["last_success"] == old["companies"]["111111"]["last_success"]
    assert "simulated outage" in (workspace / "summary.json").read_text()
    legacy = tmp_path / "old-validator-cache"
    legacy.mkdir()
    old["notices"]["900001"]["extraction"]["report_period"] = "2030-Q3"
    seed_publication(legacy, old)
    failed.clear()
    count = len(calls)
    fourth = runner.run(path, legacy)
    assert len(calls) == count + 1 and fourth["model_calls"] == 1
    assert runner.load_state(legacy)["notices"]["900001"]["extraction"]["report_period"] == "2031-H1"

    prior = (workspace / "current.json").read_bytes()
    original_write = runner.write_text

    def fail_generation_page(target, value):
        if target.name == "calendar.html" and workspace / "runs" in target.parents:
            raise OSError("injected interrupted generation")
        return original_write(target, value)

    monkeypatch.setattr(runner, "write_text", fail_generation_page)
    import pytest
    with pytest.raises(OSError, match="interrupted generation"):
        runner.run(path, workspace)
    assert (workspace / "current.json").read_bytes() == prior
    assert runner.load_state(workspace)["last_run_id"] == third["run_id"]


def test_live_cannot_reuse_replay_state(tmp_path):
    workspace = tmp_path / "live"
    workspace.mkdir()
    seed_publication(workspace, {"mode": "historical_replay"})
    import pytest
    with pytest.raises(ValueError, match="不同工作区"):
        runner.run(config(tmp_path), workspace)


def test_role_and_source_identity_are_checked_together():
    data = output()
    data["meeting_evidence"]["quote"] = "公司2031年半年度业绩说明会，提问截止2031年9月20日14:00-15:00"
    source = [HEADER + data["meeting_evidence"]["quote"] + "。实际会议召开时间：2031年9月21日14:00-15:00。"]
    assert "unproven_meeting_role" in extract.validate_evidence(data, source)
    data["meeting_evidence"]["quote"] = "会议召开时间：2031年9月20日14:00-15:00"
    data.update(report_period="2030-Q3", notice_number="2020-999")
    errors = extract.validate_evidence(data, [HEADER + data["meeting_evidence"]["quote"]])
    assert "unsupported_report_period" in errors and "unsupported_notice_number" in errors


def test_transient_retry_is_bounded_and_keeps_missing_usage(tmp_path, monkeypatch):
    data = output()
    item = {"id": "1", "stock_code": "111111", "publication_date": "2031-09-01", "title": "关于召开2031年半年度业绩说明会的公告", "pages": [HEADER + data["meeting_evidence"]["quote"]]}
    responses = [(None, {"error": "timeout", "retryable": True, "usage": None}), (data, {"usage": {"total_tokens": 13}})]

    def fake_call(model, messages, directory):
        value, receipt = responses.pop(0)
        receipt.update(model=model, receipt_path=str(tmp_path / (str(len(responses)) + ".json")))
        return value, receipt

    monkeypatch.setattr(extract, "call_model", fake_call)
    monkeypatch.setattr(extract.time, "sleep", lambda _: None)
    result = extract.extract_notice(item, ["test/model"], tmp_path, max_calls=2)
    assert result["status"] == "accepted" and len(result["attempts"]) == 2
    assert result["usage"] == {"known_total_tokens": 13, "calls_with_unknown_usage": 1}


def test_explicit_reschedule_phrase_is_a_valid_meeting_role():
    data = output()
    quote = "公司2031年半年度业绩说明会顺延至2031年9月20日14:00-15:00召开。"
    data.update(notice_kind="postponed", meeting_evidence={"page": 1, "quote": quote})
    assert not extract.validate_evidence(data, [HEADER + quote])
    bad = "公司2031年半年度业绩说明会提问截止时间改为2031年9月20日14:00-15:00。"
    data["meeting_evidence"]["quote"] = bad
    assert "unproven_meeting_role" in extract.validate_evidence(data, [HEADER + bad])


def test_meeting_role_does_not_include_the_next_sentences_date():
    data = output()
    quote = "会议召开时间：2031年9月20日14:00-15:00。2031年9月19日为财报发布日期。"
    data["meeting_evidence"]["quote"] = quote
    assert not extract.validate_evidence(data, [HEADER + quote])
    data["meeting_date"] = "2031-09-19"
    assert "unsupported_value:meeting_date" in extract.validate_evidence(data, [HEADER + quote])
    planned = "公司拟于2031年9月20日14:00-15:00召开业绩说明会。2031年9月19日为财报发布日期。"
    data["meeting_evidence"]["quote"] = planned
    assert "unsupported_value:meeting_date" in extract.validate_evidence(data, [HEADER + planned])


def test_omitted_year_needs_one_explicit_source_year_or_quote_context():
    data = output()
    quote = "会议召开时间：9月20日14:00-15:00"
    data["meeting_evidence"]["quote"] = quote
    assert not extract.validate_evidence(data, [HEADER + quote])
    data["meeting_date"] = "2030-09-20"
    assert "unsupported_value:meeting_date" in extract.validate_evidence(data, [HEADER + quote])
    data["meeting_date"] = "2031-09-20"
    assert "unsupported_value:meeting_date" in extract.validate_evidence(data, [HEADER + quote + "。另见2030年9月10日数据。"])


def test_body_period_needs_one_unambiguous_explicit_declaration():
    data = output()
    metadata = {"title": "关于参加2031年辖区集体接待日暨半年度报告说明会的公告"}
    data.update(notice_kind="collective", meeting_date=None, start_time=None, end_time=None, meeting_evidence=None)
    pages = ["公告编号：2031-001\n公司将介绍2031年半年度业绩。"]
    assert not extract.validate_evidence(data, pages, metadata)
    assert "unsupported_report_period" in extract.validate_evidence(data, [pages[0] + "对比2030年度数据。"], metadata)


def test_missing_usage_value_is_unknown_not_a_crash(tmp_path, monkeypatch):
    actions = iter([{"action": "query_company", "id": "111111"}, {"action": "query_company", "id": "222222"}, {"action": "finish", "id": None}])

    class EmptySource:
        def __init__(self, *args):
            pass
        def acquire(self, *args):
            return {"status": "complete", "query_complete": True, "failed_items": [], "error": None, "query": {}, "items": []}

    monkeypatch.setattr(runner, "CninfoSource", EmptySource)
    monkeypatch.setattr(runner, "call_model", lambda *args, **kwargs: (next(actions), {"usage": {"total_tokens": None}}))
    path = config(tmp_path)
    value = json.loads(path.read_text())
    value["strategy"] = "adaptive"
    path.write_text(json.dumps(value))
    result = runner.run(path, tmp_path / "unknown-usage")
    assert result["status"] == "complete"
    assert result["usage"] == {"known_total_tokens": 0, "calls_with_unknown_usage": 3}


def test_provider_error_cannot_write_the_api_key(tmp_path, monkeypatch):
    secret = "fake-private-token-for-test-only"
    class BadResponse:
        status_code = 401
        headers = {}
        text = secret
        def json(self):
            return {"error": secret}
        def raise_for_status(self):
            raise extract.requests.HTTPError("invalid token " + secret)
    monkeypatch.setattr(extract, "credentials", lambda: secret)
    monkeypatch.setattr(extract.requests, "post", lambda *args, **kwargs: BadResponse())
    data, receipt = extract.call_model("fictional-model", [], tmp_path)
    assert data is None and receipt["redacted_secret"]
    assert secret not in Path(receipt["receipt_path"]).read_text()


def test_provider_cannot_return_an_unredacted_parsed_secret(tmp_path, monkeypatch):
    secret = "fake-private-token-for-test-only"
    class EchoResponse:
        status_code = 200
        headers = {}
        text = secret
        def json(self):
            return {"model": "fictional-model", "choices": [{"finish_reason": "stop", "message": {"content": json.dumps({"action": secret, "id": secret})}}]}
        def raise_for_status(self):
            pass
    monkeypatch.setattr(extract, "credentials", lambda: secret)
    monkeypatch.setattr(extract.requests, "post", lambda *args, **kwargs: EchoResponse())
    data, receipt = extract.call_model("fictional-model", [], tmp_path)
    assert secret not in json.dumps(data)
    assert receipt["redacted_secret"]
    assert secret not in Path(receipt["receipt_path"]).read_text()


def test_missing_commit_pointer_cannot_silently_recover_a_convenience_copy(tmp_path):
    seed_publication(tmp_path, {"last_run_id": "new"})
    (tmp_path / "state.json").write_text(json.dumps({"last_run_id": "old"}))
    (tmp_path / "current.json").unlink()
    with pytest.raises(ValueError, match="指针current.json缺失"):
        runner.load_publication(tmp_path)


def test_provenance_hash_binds_the_actual_command_entrypoint(tmp_path, monkeypatch):
    (tmp_path / "disclosure_agent").mkdir()
    (tmp_path / "prompts").mkdir()
    entry = tmp_path / "run_agent.py"
    entry.write_text("original synthetic entry")
    monkeypatch.setattr(runner, "ROOT", tmp_path)
    original = runner._program_hash()
    entry.write_text("changed synthetic entry")
    assert runner._program_hash() != original


@pytest.mark.parametrize("damage", ["missing_calendar", "different_generation", "wrong_internal_run"])
def test_commit_pointer_requires_complete_same_run_artifacts(tmp_path, damage):
    seed_publication(tmp_path, {})
    path = tmp_path / "current.json"
    manifest = json.loads(path.read_text())
    if damage == "missing_calendar":
        del manifest["artifacts"]["calendar.html"]
    elif damage == "different_generation":
        other = tmp_path / "runs/other"
        other.mkdir()
        (other / "calendar.html").write_bytes((tmp_path / manifest["artifacts"]["calendar.html"]["path"]).read_bytes())
        manifest["artifacts"]["calendar.html"]["path"] = "runs/other/calendar.html"
    else:
        target = tmp_path / manifest["artifacts"]["summary.json"]["path"]
        target.write_text(json.dumps({"run_id": "other"}))
        manifest["artifacts"]["summary.json"]["sha256"] = hashlib.sha256(target.read_bytes()).hexdigest()
    path.write_text(json.dumps(manifest))
    with pytest.raises(ValueError):
        runner.load_publication(tmp_path)


@pytest.mark.parametrize("invalidity", ["validator_budget", "receipt_budget", "receipt_reextract_failed"])
def test_invalid_cached_evidence_marks_retained_event_for_review(tmp_path, monkeypatch, invalidity):
    data = output()
    old = {"id": "900002", "stock_code": "111111", "company": "虚构甲公司", "title": "关于召开2031年半年度业绩说明会的公告", "publication_date": "2031-09-02", "pdf_sha256": "a" * 64, "pdf_path": str(tmp_path / "fictional.pdf"), "url": "https://example.invalid/fictional", "pages": [HEADER + data["meeting_evidence"]["quote"]]}
    items = [old]
    fail = False
    class Source:
        def __init__(self, *args):
            pass
        def acquire(self, company, *args):
            return {"status": "complete", "query_complete": True, "failed_items": [], "query": {}, "items": items if company["code"] == "111111" else []}
    def fake_extract(item, *args, **kwargs):
        if fail and item["id"] == old["id"]:
            return {"status": "rejected", "data": None, "model": None, "attempts": [], "errors": ["synthetic service failure"]}
        receipt = tmp_path / (item["id"] + ".json")
        receipt.write_text(json.dumps({"synthetic": True}))
        return {"status": "accepted", "data": data, "model": "test/model", "attempts": [{"usage": {"total_tokens": 1}, "receipt_path": str(receipt)}], "errors": []}
    monkeypatch.setattr(runner, "CninfoSource", Source)
    monkeypatch.setattr(runner, "extract_notice", fake_extract)
    path = config(tmp_path)
    workspace = tmp_path / "live"
    first = runner.run(path, workspace)
    assert first["status"] == "complete"
    if invalidity.startswith("receipt"):
        (tmp_path / "900002.json").unlink()
    else:
        original_validate = runner.validate_evidence
        monkeypatch.setattr(runner, "validate_evidence", lambda value, pages, item: ["synthetic upgraded rule"] if item["id"] == "900002" else original_validate(value, pages, item))
    if invalidity.endswith("budget"):
        items.insert(0, {**old, "id": "900001", "publication_date": "2031-09-01"})
        value = json.loads(path.read_text())
        value["max_model_calls"] = 1
        path.write_text(json.dumps(value))
    else:
        fail = True
    second = runner.run(path, workspace)
    assert second["status"] == "incomplete"
    event = runner.load_state(workspace)["events"]["111111:900002"]
    assert event["validity"] == "needs_review"
    assert event["meeting_date"] == "2031-09-20"
