"""Pure notice-to-event reconciliation. No I/O, model calls, or clock reads."""
from copy import deepcopy
import json
import re
from .scope import period_matches, source_period

EVENT_FIELDS = (
    "report_period", "meeting_date", "start_time", "end_time",
    "question_deadline_date", "question_deadline_time", "participation_url", "status",
)
MEETING_FIELDS = ("meeting_date", "start_time", "end_time")
DEADLINE_FIELDS = ("question_deadline_date", "question_deadline_time")
IGNORED_KINDS = {"completed", "collective", "other"}


def _number(value):
    return re.sub(r"[\s：:号临]", "", str(value or "")).replace("－", "-").replace("—", "-")


def _record_version(record, status):
    version = {key: deepcopy(value) for key, value in record.items() if key != "versions"}
    version["version_status"] = status
    return version


def _version_key(record):
    return (record.get("pdf_sha256"), json.dumps(record.get("extraction"), sort_keys=True, ensure_ascii=False))


def _add_version(notice, record, status):
    version = _record_version(record, status)
    if not any(_version_key(existing) == _version_key(version) for existing in notice["versions"]):
        notice["versions"].append(version)


def _issue(record, reason, **details):
    return {"stock_code": record["stock_code"], "source_id": str(record["id"]), "reason": reason, **details}


def _evidence_quote(evidence):
    return (evidence or {}).get('quote','') or ''.join(part['quote'] for part in (evidence or {}).get('parts',[]))


def _claim_text(data):
    return " ".join(
        [_evidence_quote(data.get(field)) for field in
         ("meeting_evidence", "deadline_evidence", "relation_evidence")]
        + list(data.get("review_notes") or [])
    )


def _deadline_text(data, record):
    evidence = data.get('deadline_evidence') or {}
    text = _evidence_quote(evidence)
    context = record.get('source_flags', {}).get('deadline_context') or {}
    if (context.get('source_id') != str(record.get('id'))
            or context.get('pdf_sha256') != record.get('pdf_sha256')
            or context.get('original_evidence') != evidence):
        return text
    parts = evidence.get('parts') or [evidence]
    matching = [index for index, part in enumerate(parts) if part.get('page') == context.get('page')]
    if len(matching) != 1 or not isinstance(context.get('quote'), str) or len(context['quote']) > 800:
        return text
    index = matching[0]
    original = re.sub(r'\s+', '', parts[index].get('quote', ''))
    if not original or original not in re.sub(r'\s+', '', context['quote']):
        return text
    return ''.join(context['quote'] if i == index else part['quote'] for i, part in enumerate(parts))


def _deadline_is_explicit(data, record, event_period):
    text = re.sub(r'\s+', '', _deadline_text(data, record))
    if re.search(r'原通知|原公告|原定|此前|先前|往期|上次|历史|曾经|曾于', text):
        return False
    if re.search(r'(?:回复|答复|回答)(?:投资者)?(?:提问|问题)?的?(?:截止)?(?:时间|时段)|(?:提问|问题)的?(?:回复|答复|回答)(?:时间|截止)', text):
        return False
    declared = source_period(text)
    expected = source_period(event_period) or event_period
    if declared and expected and not set(declared.split('+')).issubset(expected.split('+')):
        return False
    if re.search(r'(提问|征集|问题|报名).*(调整|变更|改为|改至|延期|延长)|(调整|变更|改为|改至|延期|延长).*(提问|征集|问题|报名)', text):
        return True
    if not (re.search(r'前|截止|截至', text) and re.search(r'登录|登陆|访问|进入|选中|提交|发送|填写|完成', text)
            and re.search(r'提问|报名', text)):
        return False
    return bool(re.search(r'本次(?:业绩)?说明会|本次活动|本次会议', text)
                or (declared and re.search(r'业绩(?:网上|线上|网络|电话)?说明会(?:页面|专题|栏目).{0,30}(?:提问|报名)', text)))


def _business(event):
    return {field: deepcopy(event.get(field)) for field in EVENT_FIELDS}


def _visible(event):
    return {**_business(event), "source_ids": event.get("source_ids", []),
            "pending_fields": event.get("pending_fields", {}), "validity": event.get("validity"),
            "review_reasons": sorted(reason for reason in event.get("review_reasons", []) if reason != "company_coverage_incomplete")}


def event_review_reasons(event, issues):
    return sorted({item["reason"] for item in issues if item.get("stock_code") == event.get("stock_code") and (
        item.get("event_id") == event.get("id") or item.get("source_id") in event.get("source_ids", [])
        or item.get("reason") in {"ambiguous_or_missing_original_notice", "incomplete_initial_event", "company_coverage_incomplete"})})


def _record_activity(previous, event, revised, run_id, as_of):
    old = previous.get("events", {}).get(event["id"])
    activity = deepcopy((old or {}).get("activity"))
    if old is not None and _visible(old) == _visible(event):
        event["activity"] = activity or {"first_seen_at": None, "updated_at": None,
                                          "kind": "legacy", "revision": 0, "run_id": None}
        return
    if set(event.get("source_ids", [])) & revised:
        kind = "extraction_revision"
    elif old is None:
        kind = "new" if previous.get("companies", {}).get(event["stock_code"], {}).get("baseline_complete") else "baseline"
    elif _business(old) == _business(event) and old.get("source_ids") == event.get("source_ids"):
        kind = "review"
    else:
        kind = "updated"
    event["activity"] = {
        "first_seen_at": (activity or {}).get("first_seen_at") if old else as_of,
        "updated_at": as_of, "kind": kind,
        "revision": (activity or {}).get("revision", 0) + (1 if old else 0), "run_id": run_id,
    }


def _initial(record):
    data = record["extraction"]
    event = {field: data.get(field) for field in EVENT_FIELDS}
    event.update({
        "id": f"{record['stock_code']}:{record['id']}",
        "stock_code": record["stock_code"], "company": record["company"],
        "status": "scheduled", "source_ids": [str(record["id"])],
        "source_numbers": [data["notice_number"]] if data.get("notice_number") else [],
        "pending_fields": {}, "history": [],
    })
    return event


def _apply(event, record):
    data = record["extraction"]
    old = _business(event)
    source_id = str(record["id"])
    unchanged = (record.get("source_flags", {}).get("other_fields_unchanged", False)
                 or bool(re.search(r"其他.{0,12}(不变|无变|未变)|其余.{0,12}(不变|无变|未变)", _claim_text(data))))
    explicit_deadline = _deadline_is_explicit(data, record, event.get('report_period'))
    for field in MEETING_FIELDS + DEADLINE_FIELDS + ("participation_url",):
        value = data.get(field)
        if value is None:
            continue
        if value == event.get(field):
            if field in DEADLINE_FIELDS and not unchanged and explicit_deadline:
                event["pending_fields"].pop(field, None)
            continue
        if field in DEADLINE_FIELDS and (unchanged or not explicit_deadline):
            pending = {"source_id": source_id, "old": event.get(field), "candidate": value,
                       "evidence": deepcopy(data.get("deadline_evidence")),
                       "reason": "other_fields_unchanged_conflict" if unchanged else "deadline_change_not_explicit"}
            event["pending_fields"].setdefault(field, []).append(pending)
            continue
        event[field] = value
        event["pending_fields"].pop(field, None)
    kind = data["notice_kind"]
    if kind == "cancelled" or (kind == "postponed" and not data.get("meeting_date")):
        for field in MEETING_FIELDS:
            event[field] = None
        event["status"] = "cancelled" if kind == "cancelled" else "postponed"
    elif data.get("meeting_date"):
        event["status"] = "scheduled"
    if source_id not in event["source_ids"]:
        event["source_ids"].append(source_id)
    if data.get("notice_number") and data["notice_number"] not in event["source_numbers"]:
        event["source_numbers"].append(data["notice_number"])
    new = _business(event)
    if old != new:
        event["history"].append({"source_id": source_id, "publication_date": record["publication_date"],
                                 "before": old, "after": new})


def _rebuild(notices, issues, report_period=None):
    events = {}
    ordered = sorted(notices.values(), key=lambda row: (
        row["publication_date"], row["extraction"]["notice_kind"] != "initial", str(row["id"])))
    for record in ordered:
        data = record["extraction"]
        if data.get("report_period") and not period_matches(data["report_period"], report_period):
            continue
        kind = data["notice_kind"]
        if kind in IGNORED_KINDS:
            continue
        if kind == "initial":
            if not data.get("report_period") or not data.get("meeting_date"):
                issues.append(_issue(record, "incomplete_initial_event"))
                continue
            event = _initial(record)
            events[event["id"]] = event
            continue
        number = _number(data.get("related_notice_number"))
        matches = [event for event in events.values()
                   if event["stock_code"] == record["stock_code"] and number
                   and number in {_number(value) for value in event["source_numbers"]}]
        if not number or not data.get("relation_evidence") or len(matches) != 1:
            issues.append(_issue(record, "ambiguous_or_missing_original_notice", related_notice_number=number))
            continue
        event = matches[0]
        if data.get("report_period") and data["report_period"] != event["report_period"]:
            issues.append(_issue(record, "report_period_conflict", event_id=event["id"]))
            continue
        _apply(event, record)
    return events


def merge(previous: dict, records: list[dict], coverage: dict, run_id: str, as_of: str, *, report_period=None) -> tuple[dict, list, list]:
    """Rebuild chronological events, preserving failed companies and immutable versions.

    Coverage is keyed by stock code. A source hash conflict never replaces the
    accepted record. Same-source extraction revisions may replace it and are
    labelled distinctly from newly observed disclosure changes.
    """
    state = deepcopy(previous)
    for key in ("events", "notices", "companies"):
        state.setdefault(key, {})
    issues = []
    for incoming in records:
        record = deepcopy(incoming)
        record["id"] = str(record["id"])
        record.pop("pages", None)
        notice_id = record["id"]
        old = state["notices"].get(notice_id)
        if old is None:
            record["versions"] = []
            state["notices"][notice_id] = record
        elif old.get("pdf_sha256") != record.get("pdf_sha256"):
            _add_version(old, record, "source_conflict")
        elif old.get("extraction") != record.get("extraction"):
            record["versions"] = deepcopy(old.get("versions", []))
            _add_version(record, old, "extraction_revision")
            record["pending_extraction_revision"] = True
            state["notices"][notice_id] = record
        else:
            for key in ("source_flags", "model", "extractor_fingerprint", "extraction_run_id", "model_receipts",
                        "compatible_prompt_revalidation", "revalidated_by_fingerprint", "revalidation_run_id",
                        "revalidated_from_receipt", "unknown_provider_receipts"):
                if key in record:
                    old[key] = deepcopy(record[key])
    for notice in state["notices"].values():
        if notice["extraction"].get("report_period") and not period_matches(notice["extraction"]["report_period"], report_period):
            continue
        for version in notice.get("versions", []):
            if version.get("version_status") == "source_conflict":
                issues.append(_issue(notice, "source_hash_changed", candidate_sha256=version.get("pdf_sha256")))
    revised = {notice_id for notice_id, notice in state["notices"].items()
               if notice.get("pending_extraction_revision", False)}
    rebuilt = _rebuild(state["notices"], issues, report_period)
    failed_codes = {code for code, item in coverage.items()
                    if item.get("status") == "failed" or not item.get("query_complete", False)
                    or not item.get("processing_complete", False)}
    for code in failed_codes:
        rebuilt = {key: event for key, event in rebuilt.items() if event["stock_code"] != code}
        rebuilt.update({key: deepcopy(event) for key, event in previous.get("events", {}).items()
                        if event["stock_code"] == code and period_matches(event.get("report_period"), report_period)})
        issues.append({"stock_code": code, "source_id": None, "reason": "company_coverage_incomplete"})
    changes = []
    for event_id, event in rebuilt.items():
        old = previous.get("events", {}).get(event_id)
        before, after = _business(old) if old else None, _business(event)
        if before != after:
            source_ids = set(event["source_ids"]) | set((old or {}).get("source_ids", []))
            changes.append({"event_id": event_id, "stock_code": event["stock_code"],
                            "kind": "extraction_revision" if source_ids & revised else "new" if old is None else "updated",
                            "before": before, "after": after, "source_ids": event["source_ids"][:]})
    for event_id, old in previous.get("events", {}).items():
        if not period_matches(old.get("report_period"), report_period):
            continue
        if event_id not in rebuilt:
            changes.append({"event_id": event_id, "stock_code": old["stock_code"],
                            "kind": "extraction_revision", "before": _business(old), "after": None,
                            "source_ids": old["source_ids"][:]})
    for event in rebuilt.values():
        if event["stock_code"] in failed_codes:
            continue
        event["review_reasons"] = event_review_reasons(event, issues)
        _record_activity(previous, event, revised, run_id, as_of)
    for notice in state["notices"].values():
        if notice["stock_code"] not in failed_codes:
            notice.pop("pending_extraction_revision", None)
    state["events"] = rebuilt
    for event in rebuilt.values():
        for field, pending_values in event["pending_fields"].items():
            for pending in pending_values:
                issues.append({"stock_code": event["stock_code"], "source_id": pending["source_id"],
                               "reason": pending["reason"], "field": field, "event_id": event["id"]})
    issue_codes = {issue["stock_code"] for issue in issues}
    for code, item in coverage.items():
        company = deepcopy(state["companies"].get(code, {}))
        company.update({"coverage": deepcopy(item), "last_run": run_id})
        if code not in failed_codes and code not in issue_codes and item.get("status") == "complete":
            company["last_success"] = as_of
            company["status"] = "complete"
        else:
            company["status"] = "failed" if code in failed_codes else "needs_review"
        state["companies"][code] = company
    return state, changes, issues
