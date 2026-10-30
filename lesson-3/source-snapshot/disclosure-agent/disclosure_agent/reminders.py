"""Verified calendar components and RFC 5545 import files. No delivery side effects."""
from datetime import datetime, timezone
import hashlib
import re
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo

from .ledger import event_review_reasons

TZ = ZoneInfo("Asia/Shanghai")
BLOCKING_REASONS = {"company_coverage_incomplete", "ambiguous_or_missing_original_notice", "incomplete_initial_event", "report_period_conflict", "source_hash_changed"}


def safe_url(value):
    value = str(value or "")
    try:
        parsed = urlsplit(value)
    except ValueError:
        return ""
    return value if parsed.scheme in {"http", "https"} and parsed.netloc and not any(c.isspace() or ord(c) < 32 for c in value) else ""


def _instant(day, clock):
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", day or "") or not re.fullmatch(r"\d{2}:\d{2}", clock or ""):
        return None
    try:
        return datetime.fromisoformat(day + "T" + clock).replace(tzinfo=TZ)
    except ValueError:
        return None


def reminder_items(event, notices, issues=()):
    """Each component is independently eligible; a deadline conflict leaves the meeting usable."""
    if event.get("status") != "scheduled" or event.get("validity") == "needs_review":
        return []
    source_ids = event.get("source_ids", [])
    if not source_ids or any(identity not in notices for identity in source_ids):
        return []
    if any(version.get("version_status") == "source_conflict" for sid in source_ids
           for version in notices.get(sid, {}).get("versions", [])):
        return []
    if BLOCKING_REASONS.intersection(event.get("review_reasons", []) + event_review_reasons(event, issues)):
        return []
    sources = [notices[sid] for sid in source_ids if sid in notices]
    latest = sources[-1] if sources else {}
    url = safe_url(latest.get("pdf_url") or latest.get("url"))
    participation = safe_url(event.get("participation_url"))
    title = event.get("company", "") + " · " + (event.get("report_period") or "报告期未注明") + "业绩说明会"
    description = "时间按北京时间解释。\n" + ("公告提供的参与入口：" + participation + "\n" if participation else "参与方式请核对原公告。\n") + ("原公告：" + url if url else "")
    pending = event.get("pending_fields", {})
    components = []
    for kind, fields, label in [
        ("meeting", ("meeting_date", "start_time", "end_time"), title),
        ("deadline", ("question_deadline_date", "question_deadline_time"), title + " · 提问/报名截止"),
    ]:
        if set(fields) & set(pending):
            continue
        start = _instant(event.get(fields[0]), event.get(fields[1]))
        if not start:
            continue
        end = _instant(event.get("meeting_date"), event.get("end_time")) if kind == "meeting" else None
        if end is not None and end <= start:
            continue
        uid = hashlib.sha256(event["id"].encode()).hexdigest()[:32] + "." + kind + "@disclosure-agent.local"
        components.append({"event_id": event["id"], "kind": kind, "uid": uid,
                           "title": label, "start": start.isoformat(), "end": end.isoformat() if end else None,
                           "url": url, "description": description,
                           "sequence": int(event.get("activity", {}).get("revision", len(event.get("history", []))))})
    return components


def _text(value):
    return str(value).replace("\\", "\\\\").replace("\r\n", "\n").replace("\r", "\n").replace("\n", "\\n").replace(";", "\\;").replace(",", "\\,")


def _utc(value):
    at = datetime.fromisoformat(value)
    if at.tzinfo is None:
        at = at.replace(tzinfo=TZ)
    return at.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _fold(line):
    result, current = [], ""
    for char in line:
        if len((current + char).encode("utf-8")) > 75:
            result.append(current)
            current = " "
        current += char
    return "\r\n".join(result + [current])


def render_ics(items, timestamp):
    lines = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//Disclosure Agent//CNINFO Calendar//ZH", "CALSCALE:GREGORIAN", "X-WR-CALNAME:公告事件提醒"]
    for item in items:
        lines += ["BEGIN:VEVENT", "UID:" + item["uid"], "DTSTAMP:" + _utc(timestamp),
                  "SEQUENCE:" + str(item["sequence"]), "DTSTART:" + _utc(item["start"])]
        if item.get("end"):
            lines.append("DTEND:" + _utc(item["end"]))
        lines += ["SUMMARY:" + _text(item["title"]), "DESCRIPTION:" + _text(item["description"]), "STATUS:CONFIRMED"]
        if item.get("url"):
            lines.append("URL:" + item["url"])
        for trigger in ("-P1D", "-PT30M"):
            lines += ["BEGIN:VALARM", "ACTION:DISPLAY", "TRIGGER:" + trigger,
                      "DESCRIPTION:" + _text(item["title"]), "END:VALARM"]
        lines.append("END:VEVENT")
    return "\r\n".join(_fold(line) for line in lines + ["END:VCALENDAR"]) + "\r\n"
