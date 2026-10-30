import hashlib
import json
from datetime import datetime
from pathlib import Path
from unittest.mock import Mock
from zoneinfo import ZoneInfo

import pytest
import requests

from disclosure_agent import market_source
from disclosure_agent.cninfo import CninfoSource, QUERY_URL

TZ = ZoneInfo("Asia/Shanghai")
START, END = "2026-03-01", "2026-03-31"


def row(identifier, day=START, **changes):
    return {"announcementId": str(identifier), "secCode": "600887", "orgId": "gssh0600887",
            "announcementTime": int(datetime.fromisoformat(day).replace(tzinfo=TZ).timestamp() * 1000),
            "announcementTitle": "关于召开业绩说明会的公告",
            "adjunctUrl": f"finalpage/{day}/{identifier}.PDF", **changes}


def seed(root, name, rows, total, *, start=START, end=END, page=1, more=False, **query):
    path = root / name / f"page-{page:03d}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    params = {"pageNum": str(page), "pageSize": "30", "column": "szse", "tabName": "fulltext",
              "stock": "", "plate": "", "searchkey": "业绩说明会", "secid": "", "category": "",
              "trade": "", "seDate": start + "~" + end, "sortName": "time", "sortType": "asc",
              "isHLtitle": "false", **query}
    path.with_suffix(".request.json").write_text(json.dumps({"method": "POST", "url": QUERY_URL, "params": params}))
    raw = json.dumps({"totalAnnouncement": total, "hasMore": more, "announcements": rows}).encode()
    path.write_bytes(raw)
    path.with_suffix(".response.json").write_text(json.dumps({"status_code": 200,
        "sha256": hashlib.sha256(raw).hexdigest(), "retrieved_at": "2026-10-31T09:00:00+08:00"}))
    return path


class Response:
    def __init__(self, rows=(), total=0, more=False, status=200):
        self.status_code = status
        self.content = json.dumps({"totalAnnouncement": total, "hasMore": more,
                                   "announcements": list(rows)}).encode()
        self.headers = {"Retry-After": "60"} if status in {403, 429} else {}

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(str(self.status_code), response=self)


def network(monkeypatch, responses):
    request = Mock(side_effect=responses)
    clock, starts, sleeps = [0.0], [], []

    def make(workspace, run_dir):
        source = CninfoSource(workspace, run_dir)

        def send(*args, **kwargs):
            starts.append(clock[0])
            return request(*args, **kwargs)

        source.session.request = send
        return source

    def sleep(seconds):
        sleeps.append(seconds)
        clock[0] += seconds

    monkeypatch.setattr(market_source, "CninfoSource", make)
    monkeypatch.setattr(market_source.time, "sleep", sleep)
    monkeypatch.setattr(market_source.time, "monotonic", lambda: clock[0])
    return request, starts, sleeps


def test_closed_seed_is_reverified_and_reused_without_network(tmp_path, monkeypatch):
    seeds = tmp_path / "original"
    seed(seeds, "a", [row(1), row(2)], 2)
    request, _, _ = network(monkeypatch, [])
    workspace = tmp_path / "workspace"
    result = market_source.discover_market(workspace, tmp_path / "run", START, END,
                                           seed_roots=[seeds], max_requests=0)
    assert result["complete"] and result["request_count"] == 0
    assert result["months"]["2026-03"]["unique"] == 2
    assert Path(result["manifest_path"]).is_file()
    again = market_source.discover_market(workspace, tmp_path / "next-run", START, END, max_requests=0)
    assert again["complete"] and len(again["rows"]) == 2
    request.assert_not_called()


def test_tampered_response_cannot_supply_a_month_total(tmp_path, monkeypatch):
    archive = seed(tmp_path / "original", "a", [row(1)], 1)
    archive.write_bytes(archive.read_bytes() + b" ")
    network(monkeypatch, [])
    result = market_source.discover_market(tmp_path / "workspace", tmp_path / "run", START, END,
                                           seed_roots=[archive.parent], max_requests=0)
    assert not result["complete"] and result["months"]["2026-03"]["total"] is None
    assert any("hash mismatch" in e["error"] for e in result["errors"])


@pytest.mark.parametrize("query", [{"stock": "600887,gssh0600887"}, {"plate": "sse"},
                                    {"searchkey": "年度报告"}, {"column": "bse"}, {"category": "annual"}])
def test_filtered_seed_is_not_market_evidence(tmp_path, monkeypatch, query):
    seed(tmp_path / "original", "a", [], 0, **query)
    network(monkeypatch, [])
    result = market_source.discover_market(tmp_path / "workspace", tmp_path / "run", START, END,
                                           seed_roots=[tmp_path / "original"], max_requests=0)
    assert not result["complete"] and result["rows"] == []


def test_subwindow_members_can_close_month_but_not_supply_its_total(tmp_path, monkeypatch):
    seeds = tmp_path / "original"
    seed(seeds, "month", [row(1)], 3, more=True)
    seed(seeds, "day", [row(2, "2026-03-02"), row(3, "2026-03-02")], 2,
         start="2026-03-02", end="2026-03-02")
    network(monkeypatch, [])
    result = market_source.discover_market(tmp_path / "workspace", tmp_path / "run", START, END,
                                           seed_roots=[seeds], max_requests=0)
    assert result["complete"] and result["months"]["2026-03"]["total"] == 3
    no_month = market_source.discover_market(tmp_path / "another", tmp_path / "another-run", START, END,
                                             seed_roots=[seeds / "day"], max_requests=0)
    assert not no_month["complete"] and no_month["months"]["2026-03"]["total"] is None


def test_raw_count_and_final_page_do_not_hide_duplicate_gap(tmp_path, monkeypatch):
    seed(tmp_path / "original", "a", [row(1), row(1), row(2)], 3)
    network(monkeypatch, [])
    result = market_source.discover_market(tmp_path / "workspace", tmp_path / "run", START, END,
                                           seed_roots=[tmp_path / "original"], max_requests=0)
    month = result["months"]["2026-03"]
    assert not month["complete"] and (month["unique"], month["total"]) == (2, 3)


def test_one_fresh_invocation_repairs_a_gap_exposed_by_its_own_scan(tmp_path, monkeypatch):
    request, _, _ = network(monkeypatch, [
        Response([row(1), row(1), row(3, '2026-03-02')], 3),
        Response([row(1), row(2)], 2),
    ])
    result = market_source.discover_market(tmp_path/'workspace', tmp_path/'run', START, END,
                                           max_requests=2)
    assert result['complete'] and result['request_count'] == 2
    assert request.call_args_list[1].kwargs['data']['seDate'] == START+'~'+START
    assert {row['announcementId'] for row in result['rows']} == {'1', '2', '3'}


def test_same_invocation_gap_repair_still_respects_its_request_budget(tmp_path, monkeypatch):
    request, _, _ = network(monkeypatch, [
        Response([row(1), row(1), row(3, '2026-03-02')], 3),
    ])
    result = market_source.discover_market(tmp_path/'workspace', tmp_path/'run', START, END,
                                           max_requests=1)
    assert not result['complete'] and result['request_count'] == request.call_count == 1
    assert result['stop_reason'] == 'request_budget_exhausted'


def test_conflicting_source_row_or_total_prevents_completion(tmp_path, monkeypatch):
    seeds = tmp_path / "original"
    seed(seeds, "a", [row(1), row(2)], 2)
    seed(seeds, "b", [row(1, announcementTitle="修改后的公告标题")], 1, start=START, end=START)
    network(monkeypatch, [])
    result = market_source.discover_market(tmp_path / "workspace", tmp_path / "run", START, END,
                                           seed_roots=[seeds], max_requests=0)
    assert not result["complete"] and result["months"]["2026-03"]["conflict_ids"] == ["1"]
    seed(seeds, "c", [row(1)], 3, more=True)
    result = market_source.discover_market(tmp_path / "other", tmp_path / "other-run", START, END,
                                           seed_roots=[seeds], max_requests=0)
    assert result["months"]["2026-03"]["reported_totals"] == [2, 3]
    assert not result["complete"]


def test_budget_exhaustion_resumes_next_page_and_preserves_receipts(tmp_path, monkeypatch):
    request, _, _ = network(monkeypatch, [Response([row(1)], 3, True),
                                         Response([row(2)], 3, True), Response([row(3)], 3)])
    workspace = tmp_path / "workspace"
    partial = market_source.discover_market(workspace, tmp_path / "run", START, END, max_requests=1)
    assert partial["status"] == "partial" and partial["stop_reason"] == "request_budget_exhausted"
    first_ref = partial["months"]["2026-03"]["query_refs"][0]
    before = Path(first_ref["response"]).read_bytes()
    completed = market_source.discover_market(workspace, tmp_path / "run-2", START, END, max_requests=2)
    assert completed["complete"] and completed["request_count"] == 2
    assert [call.kwargs["data"]["pageNum"] for call in request.call_args_list] == ["1", "2", "3"]
    assert Path(first_ref["response"]).read_bytes() == before


@pytest.mark.parametrize("status", [403, 429])
def test_block_stops_all_further_requests_and_retains_progress(tmp_path, monkeypatch, status):
    request, _, _ = network(monkeypatch, [Response([row(1)], 2, True), Response(status=status)])
    result = market_source.discover_market(tmp_path / "workspace", tmp_path / "run", START,
                                           "2026-04-30", max_requests=10)
    assert not result["complete"] and result["stop_reason"] == "rate_limited"
    assert result["request_count"] == request.call_count == 2
    assert [r["announcementId"] for r in result["rows"]] == ["1"]
    assert result["errors"][-1]["status_code"] == status
    assert result["errors"][-1]["retry_after"] == "60"
    assert list((tmp_path / "workspace").rglob("*.error.json"))
    resumed = market_source.discover_market(tmp_path / "workspace", tmp_path / "next-run", START,
                                            "2026-04-30", max_requests=10)
    assert resumed["request_count"] == 0 and resumed["stop_reason"] == "cooldown_active"
    assert request.call_count == 2


def test_requests_are_serial_and_interval_has_a_floor(tmp_path, monkeypatch):
    _, starts, sleeps = network(monkeypatch, [Response([row(1)], 3, True),
                                             Response([row(2)], 3, True), Response([row(3)], 3)])
    result = market_source.discover_market(tmp_path / "workspace", tmp_path / "run", START, END,
                                           min_interval=0, max_requests=3)
    assert result["complete"] and len(sleeps) == 2
    assert all(b - a >= 1.2 for a, b in zip(starts, starts[1:]))


def test_proven_parent_gap_is_repaired_by_single_day(tmp_path, monkeypatch):
    seeds = tmp_path / "original"
    for name in ["attempt-a", "attempt-b"]:
        seed(seeds, name, [row(1)], 3, page=1, more=True)
        seed(seeds, name, [row(1), row(3, "2026-03-02")], 3, page=2)
    request, _, _ = network(monkeypatch, [Response([row(1), row(2)], 2)])
    result = market_source.discover_market(tmp_path / "workspace", tmp_path / "run", START, END,
                                           seed_roots=[seeds], max_requests=1)
    assert result["complete"] and len(result["rows"]) == 3
    assert request.call_args.kwargs["data"]["seDate"] == START + "~" + START


def test_one_parent_scan_only_targets_a_day_then_checks_its_real_total(tmp_path, monkeypatch):
    seeds = tmp_path / "original"
    seed(seeds, "attempt-a", [row(1)], 3, page=1, more=True)
    seed(seeds, "attempt-a", [row(1), row(3, "2026-03-02")], 3, page=2)
    request, _, _ = network(monkeypatch, [Response([row(1), row(2)], 2)])
    result = market_source.discover_market(tmp_path / "workspace", tmp_path / "run", START, END,
                                           seed_roots=[seeds], max_requests=1)
    assert result["complete"]
    assert request.call_args.kwargs["data"]["seDate"] == START + "~" + START


def test_complete_subwindow_parents_can_locate_a_month_gap(tmp_path, monkeypatch):
    seeds = tmp_path / "original"
    seed(seeds, "month-total", [row(1)], 3, more=True)
    for name in ["half-a", "half-b"]:
        seed(seeds, name, [row(1)], 3, page=1, more=True, end="2026-03-15")
        seed(seeds, name, [row(1), row(3, "2026-03-02")], 3, page=2, end="2026-03-15")
    request, _, _ = network(monkeypatch, [Response([row(1), row(2)], 2)])
    result = market_source.discover_market(tmp_path / "workspace", tmp_path / "run", START, END,
                                           seed_roots=[seeds], max_requests=1)
    assert result["complete"]
    assert request.call_args.kwargs["data"]["seDate"] == START + "~" + START


def test_changed_daily_total_does_not_turn_parent_closure_into_success(tmp_path, monkeypatch):
    seeds = tmp_path / "original"
    for name in ["a", "b"]:
        seed(seeds, name, [row(1)], 3, page=1, more=True)
        seed(seeds, name, [row(1), row(3, "2026-03-02")], 3, page=2)
    network(monkeypatch, [Response([row(1), row(2)], 3, True)])
    result = market_source.discover_market(tmp_path / "workspace", tmp_path / "run", START, END,
                                           seed_roots=[seeds], max_requests=1)
    assert not result["complete"] and result["stop_reason"] == "source_count_inconsistent"
    assert result["errors"][-1]["kind"] == "source_count_inconsistent"
    assert result["pending"]


def test_different_end_dates_do_not_create_false_total_drift(tmp_path, monkeypatch):
    seeds = tmp_path / "original"
    seed(seeds, "old-boundary", [row(1, "2026-10-30")], 1, start="2026-10-01", end="2026-10-30")
    seed(seeds, "full-boundary", [row(2, "2026-10-31")], 2, start="2026-10-01", end="2026-10-31", more=True)
    network(monkeypatch, [])
    result = market_source.discover_market(tmp_path / "workspace", tmp_path / "run", "2026-10-01", "2026-10-31",
                                           seed_roots=[seeds], max_requests=0)
    assert result["complete"] and result["months"]["2026-10"]["reported_totals"] == [2]


def test_same_business_date_timestamp_precision_change_keeps_both_raw_receipts(tmp_path, monkeypatch):
    original=row(1)
    adjusted={**original,'announcementTime':original['announcementTime']+1000}
    seeds=tmp_path/'seeds';seed(seeds,'a',[original],1);seed(seeds,'b',[adjusted],1)
    network(monkeypatch,[])
    result=market_source.discover_market(tmp_path/'workspace',tmp_path/'run',START,END,seed_roots=[seeds],max_requests=0)
    assert result['query_complete']
    assert len(result['row_sources']['1'])==2
    assert Path(result['row_sources']['1'][0]).read_bytes()!=Path(result['row_sources']['1'][1]).read_bytes()
    assert market_source._canonical(original)!=market_source._canonical({**original,'announcementTitle':'另一份标题'})
    assert market_source._canonical(original)!=market_source._canonical(row(1,day='2026-03-02'))


def test_duplicate_only_page_does_not_discard_a_later_final_page(tmp_path, monkeypatch):
    first=[row(i) for i in range(1,31)]
    request,_,_=network(monkeypatch,[Response(first,total=61,more=True),Response(first,total=61,more=True),
        Response([row(i) for i in range(31,61)],total=61,more=True),Response([row(61)],total=61,more=False)])
    result=market_source.discover_market(tmp_path/'workspace',tmp_path/'run',START,END,max_requests=4)
    assert result['query_complete'] and len(result['rows'])==61
    assert request.call_count==4


def test_declared_daily_gap_blocks_parent_count_closure_at_budget_boundary(tmp_path, monkeypatch):
    seeds=tmp_path/'seeds'
    seed(seeds,'month',[row(1),row(3,'2026-03-02')],3,more=True)
    seed(seeds,'day',[row(1),row(2)],3,start=START,end=START,more=True)
    network(monkeypatch,[])
    result=market_source.discover_market(tmp_path/'workspace',tmp_path/'run',START,END,seed_roots=[seeds],max_requests=0)
    assert result['months']['2026-03']['unique']==3
    assert not result['complete']
    assert result['months']['2026-03']['unclosed_subwindows'][0]['unique']==2


def test_window_above_a_hundred_pages_is_split_before_paging_further(tmp_path, monkeypatch):
    request,_,_=network(monkeypatch,[Response([row(1)],3001,True),
        Response([row(2)],1500,False),Response([row(3,'2026-03-20')],1501,False)])
    result=market_source.discover_market(tmp_path/'workspace',tmp_path/'run',START,END,max_requests=3)
    assert not result['complete']
    calls=[call.kwargs['data'] for call in request.call_args_list]
    assert [call['seDate'] for call in calls]==['2026-03-01~2026-03-31','2026-03-01~2026-03-16','2026-03-17~2026-03-31']
    assert all(call['pageNum']=='1' for call in calls)


def test_complete_but_gapped_scan_uses_reverse_sort_for_the_next_attempt(tmp_path,monkeypatch):
    seeds=tmp_path/'seeds'
    seed(seeds,'asc',[row(1),row(2)],3,start=START,end=START,page=1,more=True)
    seed(seeds,'asc',[row(1)],3,start=START,end=START,page=2)
    request,_,_=network(monkeypatch,[Response([row(3)],3)])
    result=market_source.discover_market(tmp_path/'workspace',tmp_path/'run',START,START,seed_roots=[seeds],max_requests=1)
    assert result['query_complete'] and request.call_args.kwargs['data']['sortType']=='desc'


@pytest.mark.parametrize("total,pages,reason", [(101, 100, "single_day_exceeds_page_limit"),
                                               (100, 100, "single_day_page_limit_reached"),
                                               (3, 4, "single_day_page_limit_reached")])
def test_capped_single_day_prefix_is_rejected_before_request(tmp_path, monkeypatch, total, pages, reason):
    workspace = tmp_path / "workspace"
    directory = workspace / "market-source"
    for page in range(1, pages + 1):
        seed(directory, "old-attempt", [row(1)], total, start=START, end=START, page=page, more=True)
    original = {str(path): path.read_bytes() for path in directory.rglob("*.json")}
    request, _, _ = network(monkeypatch, [])
    result = market_source.discover_market(workspace, tmp_path / "run", START, START, max_requests=1)
    assert not result["complete"] and result["stop_reason"] == reason
    assert result["request_count"] == 0
    assert {str(path): path.read_bytes() for path in directory.rglob("*.json")} == original
    again = market_source.discover_market(workspace, tmp_path / "run-2", START, START, max_requests=1)
    assert again["request_count"] == 0 and again["stop_reason"] == reason
    request.assert_not_called()


def test_capped_wide_prefix_splits_before_fetching_forbidden_next_page(tmp_path, monkeypatch):
    workspace = tmp_path / "workspace"
    for page in range(1, 5):
        seed(workspace / "market-source", "old-attempt", [row(1)], 3, page=page, more=True)
    request, _, _ = network(monkeypatch, [Response([row(1), row(2)], 2),
                                         Response([row(3, "2026-03-20")], 1)])
    result = market_source.discover_market(workspace, tmp_path / "run", START, END, max_requests=2)
    calls = [call.kwargs["data"] for call in request.call_args_list]
    assert result["complete"]
    assert [call["seDate"] for call in calls] == ["2026-03-01~2026-03-16", "2026-03-17~2026-03-31"]
    assert all(call["pageNum"] == "1" for call in calls)


def test_cache_check_time_does_not_replace_source_receipt_time(tmp_path, monkeypatch):
    seeds = tmp_path / "seeds"
    seed(seeds, "old-source", [row(1)], 1)
    request, _, _ = network(monkeypatch, [])
    clock = [datetime(2026, 11, 1, 12, tzinfo=TZ)]

    class CheckClock(datetime):
        @classmethod
        def now(cls, tz=None):
            return clock[0].astimezone(tz or TZ)

    monkeypatch.setattr(market_source, "datetime", CheckClock)
    workspace = tmp_path / "workspace"
    first = market_source.discover_market(workspace, tmp_path / "run", START, END,
                                          seed_roots=[seeds], max_requests=0)
    clock[0] = datetime(2026, 11, 2, 12, tzinfo=TZ)
    second = market_source.discover_market(workspace, tmp_path / "run-2", START, END, max_requests=0)
    assert first["checked_at"] != second["checked_at"]
    for result in (first, second):
        assert result["as_of"] == result["source_receipt_through"] == "2026-10-31T09:00:00+08:00"
        assert result["retrieval_start"] == result["retrieval_end"] == result["as_of"]
        assert "not a market-wide" in result["source_time_semantics"]
        assert result["boundaries"]["publication_end"] == END
    request.assert_not_called()


def test_failed_new_request_does_not_refresh_accepted_source_interval(tmp_path, monkeypatch):
    archive = seed(tmp_path / "seeds", "old-source", [row(1)], 2, more=True)
    metadata_path = archive.with_suffix(".response.json")
    metadata = json.loads(metadata_path.read_text())
    metadata["retrieved_at"] = "2026-10-01T12:00:00+08:00"
    metadata_path.write_text(json.dumps(metadata))
    network(monkeypatch, [Response(status=429)])
    result = market_source.discover_market(tmp_path / "workspace", tmp_path / "run", START, END,
                                           seed_roots=[archive.parent], max_requests=1)
    assert result["stop_reason"] == "rate_limited"
    assert result["as_of"] == result["source_receipt_through"] == metadata["retrieved_at"]
    assert result["retrieval_start"] == result["retrieval_end"]


def test_no_accepted_receipt_has_unknown_source_time(tmp_path, monkeypatch):
    network(monkeypatch, [])
    result = market_source.discover_market(tmp_path / "workspace", tmp_path / "run", START, END, max_requests=0)
    assert result["checked_at"]
    assert result["as_of"] is result["source_receipt_through"] is None
    assert result["retrieval_start"] is result["retrieval_end"] is None
