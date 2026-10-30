"""Resumable CNINFO market discovery. Counts close before local scope filters."""
from __future__ import annotations

from collections import Counter, defaultdict
from datetime import date, datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
import hashlib
import json
import math
from pathlib import Path
import re
import time
import uuid
from zoneinfo import ZoneInfo

from .cninfo import CninfoSource, QUERY_URL

TZ = ZoneInfo("Asia/Shanghai")
KEYWORD = "业绩说明会"
PAGE_LIMIT = 100


def _write(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + "." + uuid.uuid4().hex + ".tmp")
    temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(path)


def _day(value):
    result = date.fromisoformat(value)
    if result.isoformat() != value:
        raise ValueError("Dates must use YYYY-MM-DD")
    return result


def _publication_day(row):
    value = row.get("announcementTime")
    if type(value) is not int:
        raise ValueError("Invalid announcement timestamp")
    return datetime.fromtimestamp(value / 1000, TZ).date().isoformat()


def _canonical(row):
    return json.dumps({**row, "announcementTime": _publication_day(row)},
                      sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def _receipt(request_path):
    request = json.loads(request_path.read_text(encoding="utf-8"))
    params = request.get("params") or {}
    if (request.get("method") != "POST" or request.get("url") != QUERY_URL
            or not isinstance(params, dict) or params.get("searchkey") != KEYWORD
            or params.get("column") != "szse" or params.get("tabName") != "fulltext"
            or any(params.get(key, "") for key in ("stock", "plate", "secid", "category", "trade"))
            or params.get("sortName") != "time" or params.get("sortType") not in {"asc", "desc"}
            or params.get("isHLtitle") != "false"):
        return None
    stem = request_path.name.removesuffix(".request.json")
    raw_path = request_path.with_name(stem + ".json")
    metadata_path = request_path.with_name(stem + ".response.json")
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    raw = raw_path.read_bytes()
    if len(raw) > 20 * 1024 * 1024 or metadata.get("status_code") != 200:
        raise ValueError("Seed is not a successful bounded response")
    digest = hashlib.sha256(raw).hexdigest()
    if metadata.get("sha256") != digest:
        raise ValueError("Response hash mismatch")
    retrieved = datetime.fromisoformat(metadata["retrieved_at"])
    if retrieved.tzinfo is None:
        raise ValueError("Response time needs a timezone")
    first, last = params["seDate"].split("~")
    if _day(first) > _day(last):
        raise ValueError("Invalid query interval")
    page, page_size = int(params["pageNum"]), int(params["pageSize"])
    if page < 1 or page_size < 1:
        raise ValueError("Invalid page number or size")
    payload = json.loads(raw)
    if not isinstance(payload, dict):
        raise ValueError("Invalid response structure")
    total, more = payload.get("totalAnnouncement"), payload.get("hasMore")
    rows = payload.get("announcements")
    if rows is None and total == 0:
        rows = []
    if type(total) is not int or total < 0 or type(more) is not bool or not isinstance(rows, list):
        raise ValueError("Invalid response count/list")
    if len(rows) > total or (more and not rows):
        raise ValueError("Inconsistent response count/list")
    for row in rows:
        if (not isinstance(row, dict) or not re.fullmatch(r"\d+", str(row.get("announcementId", "")))
                or not first <= _publication_day(row) <= last):
            raise ValueError("Invalid announcement ID/date in response")
    return {"start": first, "end": last, "page": page, "page_size": page_size,
            "sort": params["sortType"], "total": total, "has_more": more, "rows": rows,
            "group": str(request_path.parent.resolve()),
            "ref": {"request": str(request_path.resolve()), "response": str(raw_path.resolve()),
                    "metadata": str(metadata_path.resolve()), "sha256": digest,
                    "retrieved_at": retrieved.isoformat(), "start": first, "end": last,
                    "page": page, "count": len(rows), "total": total, "has_more": more}}


def _month_ranges(start, end):
    result = {}
    cursor = start.replace(day=1)
    while cursor <= end:
        following = (cursor.replace(day=28) + timedelta(days=4)).replace(day=1)
        result[cursor.strftime("%Y-%m")] = (max(cursor, start).isoformat(),
                                           min(following - timedelta(days=1), end).isoformat())
        cursor = following
    return result


def _groups(receipts, first, last):
    groups = defaultdict(list)
    for receipt in receipts:
        if (receipt["start"], receipt["end"]) == (first, last):
            groups[(receipt["group"], receipt["page_size"], receipt["sort"])].append(receipt)
    return list(groups.values())


def _page_bounds(receipts, first, last):
    matching = [r for r in receipts if (r["start"], r["end"]) == (first, last)]
    totals = {r["total"] for r in matching}
    total = next(iter(totals)) if len(totals) == 1 else None
    capacity = min((len(r["rows"]) for r in matching if r["has_more"] and r["rows"]), default=30)
    limit = min(PAGE_LIMIT, math.ceil(total / capacity) + 1) if total is not None else PAGE_LIMIT
    return total, capacity, limit


def _retrieval_interval(refs):
    timestamps = [datetime.fromisoformat(ref["retrieved_at"]).astimezone(TZ) for ref in refs]
    return ((min(timestamps).isoformat(), max(timestamps).isoformat()) if timestamps else (None, None))


def _complete_scan(group):
    ordered = sorted(group, key=lambda r: r["page"])
    if (not ordered or [r["page"] for r in ordered] != list(range(1, len(ordered) + 1))
            or ordered[-1]["has_more"] or any(not r["has_more"] for r in ordered[:-1])
            or len({r["total"] for r in ordered}) != 1):
        return None
    rows = [row for receipt in ordered for row in receipt["rows"]]
    days = [_publication_day(row) for row in rows]
    if len(rows) != ordered[0]["total"] or days != sorted(days, reverse=ordered[0]["sort"] == "desc"):
        return None
    return Counter(days)


def _proven_gaps(receipts, first, last, rows):
    day_totals = defaultdict(set)
    windows = {(r["start"], r["end"]) for r in receipts
               if first <= r["start"] <= r["end"] <= last}
    for window_start, window_end in windows:
        scans = [counts for group in _groups(receipts, window_start, window_end)
                 if (counts := _complete_scan(group)) is not None]
        if scans and all(counts == scans[0] for counts in scans[1:]):
            for day, count in scans[0].items():
                day_totals[day].add(count)
    observed = Counter(_publication_day(row) for row in rows)
    known_days = {r["start"] for r in receipts if r["start"] == r["end"] and observed[r["start"]] == r["total"]}
    return [{"date": day, "parent_raw_total": next(iter(counts)), "unique": observed[day],
             "gap": next(iter(counts)) - observed[day]} for day, counts in sorted(day_totals.items())
            if len(counts) == 1 and day not in known_days and observed[day] < next(iter(counts))]


def _collate(receipts, ranges):
    rows, row_refs, conflicts = {}, defaultdict(list), set()
    for receipt in receipts:
        for row in receipt["rows"]:
            day = _publication_day(row)
            if not any(first <= day <= last for first, last in ranges.values()):
                continue
            key = str(row["announcementId"])
            if key in rows and _canonical(rows[key]) != _canonical(row):
                conflicts.add(key)
            rows.setdefault(key, row)
            row_refs[key].append(receipt["ref"]["response"])
    months = {}
    for name, (first, last) in ranges.items():
        members = [row for row in rows.values() if first <= _publication_day(row) <= last]
        exact = [r for r in receipts if (r["start"], r["end"]) == (first, last)]
        totals = sorted({r["total"] for r in exact})
        total = totals[0] if len(totals) == 1 else None
        conflict_ids = sorted(str(row["announcementId"]) for row in members
                              if str(row["announcementId"]) in conflicts)
        constraints = []
        inconsistent = False
        for sub_start, sub_end in {(r["start"], r["end"]) for r in receipts
                                  if first <= r["start"] <= r["end"] <= last and (r["start"], r["end"]) != (first, last)}:
            declared = {r["total"] for r in receipts if (r["start"], r["end"]) == (sub_start, sub_end)}
            count = sum(sub_start <= _publication_day(row) <= sub_end for row in members)
            if total is not None and len(declared) == 1 and next(iter(declared)) + len(members) - count > total:
                inconsistent = True
            if len(declared) != 1 or count != next(iter(declared)):
                constraints.append({"start": sub_start, "end": sub_end, "reported_totals": sorted(declared), "unique": count})
        complete = total is not None and len(members) == total and not conflict_ids and not constraints
        reason = (None if complete else "source_count_inconsistent" if inconsistent else "conflicting_month_totals" if len(totals) > 1
                  else "month_receipt_required" if total is None else "row_conflict" if conflict_ids
                  else "unique_exceeds_total" if len(members) > total else "known_subwindow_gap" if constraints and len(members) == total else "missing_unique_ids")
        refs = [r["ref"] for r in receipts if r["start"] <= last and r["end"] >= first]
        retrieval_start, retrieval_end = _retrieval_interval(refs)
        months[name] = {"start": first, "end": last, "total": total, "reported_totals": totals,
                        "unique": len(members), "complete": complete, "reason": reason,
                        "conflict_ids": conflict_ids, "query_refs": refs,
                        "retrieval_start": retrieval_start, "retrieval_end": retrieval_end,
                        "unclosed_subwindows": constraints,
                        "proven_gap_days": _proven_gaps(receipts, first, last, members) if not complete else []}
    ordered = sorted(rows.values(), key=lambda row: (row["announcementTime"], str(row["announcementId"])))
    return ordered, months, dict(row_refs)


def discover_market(workspace: Path, run_dir: Path, start: str, end: str, *,
                    seed_roots=(), max_requests=160, min_interval=1.2) -> dict:
    """Return verified raw rows and count closure; never download PDFs or call a model.

    A source gap, budget exhaustion or request error leaves a resumable partial
    result. Repeated invocation reloads and verifies the archived source receipts.
    """
    first, last = _day(start), _day(end)
    if first > last or type(max_requests) is not int or max_requests < 0:
        raise ValueError("Invalid market interval/request budget")
    if not math.isfinite(float(min_interval)):
        raise ValueError("Invalid request interval")
    interval = max(1.2, float(min_interval))
    workspace, run_dir = Path(workspace).resolve(), Path(run_dir).resolve()
    storage = workspace / "market-source"
    workspace.mkdir(parents=True, exist_ok=True)
    run_dir.mkdir(parents=True, exist_ok=True)
    previous_path = workspace / "market-discovery.json"
    previous = json.loads(previous_path.read_text()) if previous_path.is_file() else {}
    roots = {str(Path(p).resolve()) for p in seed_roots}
    roots.update(previous.get("seed_roots", []))
    roots.add(str(storage))
    receipts, errors, seen_paths = [], [], set()
    for root in sorted(roots):
        path = Path(root)
        candidates = [path] if path.name.endswith(".request.json") and path.is_file() else path.rglob("*.request.json")
        for request_path in candidates:
            resolved = str(request_path.resolve())
            if resolved in seen_paths:
                continue
            seen_paths.add(resolved)
            try:
                receipt = _receipt(request_path)
                if receipt is not None:
                    receipts.append(receipt)
            except Exception as exc:
                errors.append({"kind": "seed_rejected", "request": resolved,
                               "error": type(exc).__name__ + ": " + str(exc)[:400]})
    ranges = _month_ranges(first, last)
    source = CninfoSource(workspace, run_dir)
    request_count, stopped = 0, None
    invocation = run_dir / ("market-discovery-" + uuid.uuid4().hex[:12] + ".json")
    rate_path = workspace / "market-source-rate.json"
    last_finished = None
    blocked_until = None
    if rate_path.is_file():
        blocked_until = json.loads(rate_path.read_text()).get("blocked_until")

    def save_rate():
        _write(rate_path, {"last_attempt_at": datetime.now(timezone.utc).isoformat(),
                           "blocked_until": blocked_until})

    def snapshot(persist_full=True):
        rows, months, refs = _collate(receipts, ranges)
        complete = all(month["complete"] for month in months.values()) and stopped is None
        retrieval_start, retrieval_end = _retrieval_interval(
            [r["ref"] for r in receipts if r["start"] <= end and r["end"] >= start])
        result = {"status": "complete" if complete else "partial", "complete": complete,
                  "query_complete": complete, "rows": rows, "months": months,
                  "errors": errors, "request_count": request_count,
                  "checked_at": datetime.now(TZ).isoformat(), "as_of": retrieval_end,
                  "source_receipt_through": retrieval_end,
                  "retrieval_start": retrieval_start, "retrieval_end": retrieval_end,
                  "source_time_semantics": "earliest/latest referenced response retrieval times; not a market-wide as-of watermark",
                  "stop_reason": stopped,
                  "boundaries": {"publication_start": start, "publication_end": end,
                                 "keyword": KEYWORD, "stock": "", "plate": "", "column": "szse",
                                 "scope": "CNINFO query before identity, period or meeting-date filtering"},
                  "pending": [{"month": name, "reason": month["reason"], "total": month["total"],
                               "unique": month["unique"], "proven_gap_days": month["proven_gap_days"]}
                              for name, month in months.items() if not month["complete"]],
                  "row_sources": refs, "seed_roots": sorted(roots), "manifest_path": str(invocation)}
        result["cooldown_until"] = blocked_until
        if stopped and not result["pending"]:
            result["pending"].append({"month": None, "reason": stopped, "total": None,
                                      "unique": None, "proven_gap_days": []})
        if persist_full:
            _write(invocation, result)
            _write(previous_path, result)
        else:
            progress = {key: value for key, value in result.items() if key not in {"rows", "row_sources", "months"}}
            progress["months"] = {name: {key: value for key, value in month.items() if key != "query_refs"}
                                  for name, month in months.items()}
            progress["progress_only"] = True
            _write(previous_path, progress)
        return result

    def request_window(window_start, window_end, month_name):
        nonlocal request_count, stopped, last_finished, blocked_until
        known_total, capacity, limit = _page_bounds(receipts, window_start, window_end)

        def split_or_stop(reason, next_page=None):
            nonlocal stopped
            if window_start == window_end:
                stopped = reason
                errors.append({"kind": reason, "start": window_start, "end": window_end,
                               "total": known_total, "observed_capacity": capacity,
                               "page_limit": limit, "next_page": next_page})
                return
            middle = _day(window_start) + (_day(window_end) - _day(window_start)) // 2
            request_window(window_start, middle.isoformat(), month_name)
            if not stopped and request_count < max_requests:
                request_window((middle + timedelta(days=1)).isoformat(), window_end, month_name)

        if known_total is not None:
            members = {str(row["announcementId"]) for r in receipts for row in r["rows"]
                       if window_start <= _publication_day(row) <= window_end}
            if len(members) == known_total:
                return
            if known_total > PAGE_LIMIT * capacity:
                split_or_stop("single_day_exceeds_page_limit")
                return
        resumable = []
        for group in _groups(receipts, window_start, window_end):
            ordered = sorted(group, key=lambda r: r["page"])
            if (Path(ordered[0]["group"]).is_relative_to(storage)
                    and [r["page"] for r in ordered] == list(range(1, len(ordered) + 1))
                    and all(r["has_more"] for r in ordered) and len({r["total"] for r in ordered}) == 1):
                resumable.append(ordered)
        prefix = max(resumable, key=len) if resumable else []
        completed = [group for group in _groups(receipts, window_start, window_end) if _complete_scan(group) is not None]
        latest = max((r for group in completed for r in group), key=lambda r: r["ref"]["retrieved_at"], default=None)
        direction = prefix[0]["sort"] if prefix else "desc" if latest and latest["sort"] == "asc" else "asc"
        directory = (Path(prefix[0]["group"]) if prefix else
                     storage / (window_start + "_" + window_end) / ("attempt-" + uuid.uuid4().hex[:12]))
        page = len(prefix) + 1
        scan_ids = {str(row["announcementId"]) for r in prefix for row in r["rows"]}
        while request_count < max_requests and stopped is None:
            known_total, capacity, limit = _page_bounds(receipts, window_start, window_end)
            if known_total is not None and known_total > PAGE_LIMIT * capacity:
                split_or_stop("single_day_exceeds_page_limit", page)
                return
            if page > limit:
                split_or_stop("single_day_page_limit_reached", page)
                return
            if blocked_until and datetime.fromisoformat(blocked_until) > datetime.now(timezone.utc):
                stopped = "cooldown_active"
                break
            wait = 0
            if last_finished is not None:
                wait = interval - (time.monotonic() - last_finished)
            elif rate_path.is_file():
                try:
                    stamp = datetime.fromisoformat(json.loads(rate_path.read_text())["last_attempt_at"])
                    wait = min(interval, interval - (datetime.now(timezone.utc) - stamp).total_seconds())
                except (ValueError, KeyError, TypeError):
                    wait = interval
            if wait > 0:
                time.sleep(wait)
            archive = directory / f"page-{page:03d}.json"
            if archive.exists() or archive.with_suffix(".request.json").exists():
                archive = directory / (f"page-{page:03d}-retry-" + uuid.uuid4().hex[:8] + ".json")
            params = {"pageNum": str(page), "pageSize": "30", "column": "szse", "tabName": "fulltext",
                      "plate": "", "stock": "", "searchkey": KEYWORD, "secid": "", "category": "",
                      "trade": "", "seDate": window_start + "~" + window_end,
                      "sortName": "time", "sortType": direction, "isHLtitle": "false"}
            request_count += 1
            save_rate()
            try:
                source._json("POST", QUERY_URL, archive, params)
                receipt = _receipt(archive.with_suffix(".request.json"))
                if receipt is None:
                    raise ValueError("New request did not match the market query")
                receipts.append(receipt)
                if len({r["total"] for r in receipts if (r["start"], r["end"]) == (window_start, window_end)}) > 1:
                    raise ValueError("Count changed for the same source interval")
                new_ids = {str(row["announcementId"]) for row in receipt["rows"]}
                scan_ids.update(new_ids)
            except Exception as exc:
                metadata_path = archive.with_suffix(".response.json")
                metadata = json.loads(metadata_path.read_text()) if metadata_path.is_file() else {}
                status_code = metadata.get("status_code")
                stopped = "rate_limited" if status_code in {403, 429} else "request_failed"
                if status_code in {403, 429}:
                    now = datetime.now(timezone.utc)
                    retry_after = metadata.get("retry_after")
                    try:
                        until = now + timedelta(seconds=float(retry_after))
                    except (TypeError, ValueError, OverflowError):
                        try:
                            until = parsedate_to_datetime(retry_after).astimezone(timezone.utc)
                        except (TypeError, ValueError, AttributeError):
                            until = now
                    blocked_until = max(until, now + timedelta(seconds=60)).isoformat()
                error = {"kind": stopped, "status_code": status_code, "request": str(archive.with_suffix(".request.json")),
                         "error": type(exc).__name__ + ": " + str(exc)[:400],
                         "at": datetime.now(TZ).isoformat(), "retry_after": metadata.get("retry_after")}
                errors.append(error)
                _write(archive.with_suffix(".error.json"), error)
                receipt = None
            finally:
                last_finished = time.monotonic()
                save_rate()
            current = snapshot(False)
            if current["months"][month_name]["reason"] == "source_count_inconsistent":
                stopped = "source_count_inconsistent"
                errors.append({"kind": stopped, "month": month_name, "request": str(archive.with_suffix(".request.json"))})
                break
            window_members = {str(row["announcementId"]) for r in receipts for row in r["rows"]
                              if window_start <= _publication_day(row) <= window_end}
            if receipt is None or not receipt["has_more"] or len(window_members) == receipt["total"]:
                break
            page += 1

    snapshot(False)
    while True:
        before_requests = request_count
        for name, (window_start, window_end) in ranges.items():
            month = _collate(receipts, ranges)[1][name]
            if month["complete"]:
                continue
            if month["reason"] in {"conflicting_month_totals", "row_conflict", "unique_exceeds_total", "source_count_inconsistent"}:
                error = {"kind": month["reason"], "month": name}
                if error not in errors:
                    errors.append(error)
                continue
            if request_count >= max_requests or stopped:
                break
            subwindows = [sub for sub in month["unclosed_subwindows"] if len(sub["reported_totals"]) == 1 and sub["unique"] < sub["reported_totals"][0]]
            if month["proven_gap_days"]:
                for gap in month["proven_gap_days"]:
                    request_window(gap["date"], gap["date"], name)
                    if stopped or request_count >= max_requests or _collate(receipts, ranges)[1][name]["complete"]:
                        break
            elif subwindows:
                for sub in sorted(subwindows, key=lambda sub: sub["end"]):
                    request_window(sub["start"], sub["end"], name)
                    if stopped or request_count >= max_requests or _collate(receipts, ranges)[1][name]["complete"]:
                        break
            else:
                request_window(window_start, window_end, name)
        if (stopped or request_count >= max_requests or request_count == before_requests
                or all(month['complete'] for month in _collate(receipts, ranges)[1].values())):
            break
    if not stopped and request_count >= max_requests and not all(m["complete"] for m in _collate(receipts, ranges)[1].values()):
        stopped = "request_budget_exhausted"
    return snapshot()
