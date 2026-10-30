from __future__ import annotations

import hashlib
import json
import os
import re
import time
from datetime import date, datetime
from pathlib import Path

import jsonschema
import requests

ROOT = Path(__file__).resolve().parents[1]
ENDPOINT = "https://api.siliconflow.cn/v1/chat/completions"
SCHEMA = json.loads((ROOT / "prompts/output.schema.json").read_text())
SYSTEM = (ROOT / "prompts/system.txt").read_text()
PROMPT_HASH = hashlib.sha256((SYSTEM + json.dumps(SCHEMA, sort_keys=True)).encode()).hexdigest()
ACTIVE_KINDS = {"initial", "change", "postponed", "cancelled"}


def credentials() -> str:
    key = os.environ.get("SILICONFLOW_API_KEY", "").strip()
    if key:
        return key
    base = Path(os.environ.get("APPDATA", str(Path.home() / ".config"))) if os.name == "nt" else Path.home() / ".config"
    path = base / "siliconflow/credentials.env"
    if path.is_file():
        for line in path.read_text().splitlines():
            clean = line.strip().removeprefix("export ")
            if clean.startswith("SILICONFLOW_API_KEY="):
                key = clean.split("=", 1)[1].strip().strip("\"").strip("'")
                if key:
                    return key
    raise RuntimeError("未找到硅基流动凭据。请使用用户级配置或SILICONFLOW_API_KEY。")


def compact(text: str) -> str:
    return re.sub(r"\s+", "", text).replace("：", ":")


def _date_in(value: str, quote: str, source_year: int | None = None) -> bool:
    y, m, d = map(int, value.split("-"))
    q = compact(quote)
    if value in q:
        return True
    context_year = source_year
    for match in re.finditer(r"(?:(\d{4})年)?(\d{1,2})月(\d{1,2})日", q):
        year, month, day = match.groups()
        if year is not None:
            context_year = int(year)
        if int(month) == m and int(day) == d and context_year == y:
            return True
    return False


def _time_in(value: str, quote: str) -> bool:
    h, m = map(int, value.split(":"))
    return bool(re.search(rf"(?<!\d)0?{h}:{m:02}(?!\d)", compact(quote)))


def _source_period(text: str) -> str | None:
    labels = {"半年度": "H1", "第一季度": "Q1", "第三季度": "Q3", "前三季度": "Q3", "年度": "FY"}
    found = [year + "-" + labels[period] for year, period in re.findall(r"(\d{4})年?(半年度|第一季度|第三季度|前三季度|年度)", compact(text))]
    return "+".join(dict.fromkeys(found)) if found else None


def _meeting_span(quote: str, kind: str) -> str:
    text = compact(quote)
    anchors = list(re.finditer(r"会议召开时间[:：]?|会议时间[:：]?|召开时间[:：]?|活动时间(?:为)?[:：]?", text))
    if anchors:
        span = text[anchors[-1].end():]
    else:
        planned = re.search(r"(?:计划于|拟于|定于|将于)([^。；;！？!?]+?)(?:举行|召开)[^。；;！？!?]*(?:业绩说明会)", text)
        shifted = re.search(r"(?:业绩说明会|会议)([^。；]*?)(?:顺延至|变更为|调整为|改为|改至)([^。；]*)", text)
        if shifted and not re.search(r"提问|征集|截止|报名", shifted.group(1)):
            span = shifted.group(2)
        else:
            span = planned.group(1) if planned else ""
    span = re.split(r"[。；;！？!?]|提问|征集|截止|报名|发布|披露", span, maxsplit=1)[0]
    if kind in {"change", "postponed"} and re.search(r"原计划|原定|原安排", text) and not re.search(r"变更为|顺延至|调整为|改为|会议召开时间", text):
        return ""
    return span


def validate_evidence(data: dict, pages: list[str], metadata: dict | None = None) -> list[str]:
    errors = ["schema: " + error.message for error in jsonschema.Draft202012Validator(SCHEMA).iter_errors(data)]
    if errors:
        return errors
    header = compact(pages[0]) if pages else ""
    numbers = re.findall(r"(?:公告编号|编号)[:：]?(?:临)?(\d{4})[-－—](\d+)", header)
    claimed = re.fullmatch(r"(?:临)?\s*(\d{4})\s*[-－—]\s*(\d+)", data.get("notice_number") or "")
    if not numbers or not claimed or (int(claimed[1]), int(claimed[2])) != (int(numbers[0][0]), int(numbers[0][1])):
        errors.append("unsupported_notice_number")
    title = (metadata or {}).get("title") or (pages[0].split("重要内容提示", 1)[0] if pages else "")
    source_period = _source_period(title)
    if source_period is None:
        body_period = _source_period("\n".join(pages))
        if body_period and "+" not in body_period:
            source_period = body_period
    if data.get("report_period") != source_period:
        errors.append("unsupported_report_period")
    scope_title = compact((metadata or {}).get("title") or (pages[0].split("本公司", 1)[0] if pages else ""))
    source_kind = "collective" if "集体接待" in scope_title else "completed" if re.search(r"说明会.*召开情况|说明会.*举行情况|说明会.*纪要", scope_title) else "other" if re.search(r"股东大会|股东会|权益分派|分红派息", scope_title) else None
    if source_kind is not None and data["notice_kind"] != source_kind:
        errors.append("source_scope_conflict")
    for key in ["meeting_date", "previous_meeting_date", "question_deadline_date"]:
        if data[key] is not None:
            try:
                date.fromisoformat(data[key])
            except (ValueError, TypeError):
                errors.append("invalid_date:" + key)
    for key in ["start_time", "end_time", "previous_start_time", "previous_end_time", "question_deadline_time"]:
        if data[key] is not None:
            try:
                datetime.strptime(data[key], "%H:%M")
                if not re.fullmatch(r"\d{2}:\d{2}", data[key]):
                    raise ValueError()
            except (ValueError, TypeError):
                errors.append("invalid_time:" + key)
    if errors:
        return errors
    for key in ["meeting_evidence", "previous_meeting_evidence", "deadline_evidence", "relation_evidence"]:
        evidence = data[key]
        if evidence is not None:
            index = evidence["page"] - 1
            if not 0 <= index < len(pages) or compact(evidence["quote"]) not in compact(pages[index]):
                errors.append("ungrounded_quote:" + key)
    kind = data["notice_kind"]
    explicit_years = {int(year) for year in re.findall(r"(?<!\d)(\d{4})年", compact("\n".join(pages)))}
    source_year = next(iter(explicit_years)) if len(explicit_years) == 1 else None
    if kind not in ACTIVE_KINDS:
        for key in ["meeting_date", "start_time", "end_time", "previous_meeting_date", "previous_start_time", "previous_end_time", "question_deadline_date", "question_deadline_time", "participation_url", "meeting_evidence", "previous_meeting_evidence", "deadline_evidence", "relation_evidence"]:
            if data[key] is not None:
                errors.append("non_calendar_field:" + key)
        return errors
    if not data["report_period"] or not data["notice_number"]:
        errors.append("missing_event_identity")
    if kind in {"initial", "change"} and not data["meeting_date"]:
        errors.append("missing_meeting_date")
    for evidence_key, fields in [
        ("meeting_evidence", ["meeting_date", "start_time", "end_time"]),
        ("previous_meeting_evidence", ["previous_meeting_date", "previous_start_time", "previous_end_time"]),
        ("deadline_evidence", ["question_deadline_date", "question_deadline_time"]),
    ]:
        values = [field for field in fields if data[field] is not None]
        if not values:
            continue
        evidence = data[evidence_key]
        if evidence is None:
            errors.append("missing_evidence:" + evidence_key)
            continue
        quote = _meeting_span(evidence["quote"], kind) if evidence_key == "meeting_evidence" else evidence["quote"]
        if evidence_key == "meeting_evidence" and not quote:
            errors.append("unproven_meeting_role")
        for field in values:
            supported = _date_in(data[field], quote, source_year) if "date" in field else _time_in(data[field], quote)
            if not supported:
                errors.append("unsupported_value:" + field)
    for start, end in [("start_time", "end_time"), ("previous_start_time", "previous_end_time")]:
        if data[start] and data[end] and data[start] >= data[end]:
            errors.append("nonpositive_interval:" + start)
    if data["related_notice_number"]:
        relation = data["relation_evidence"]
        if not relation or data["related_notice_number"] not in compact(relation["quote"]):
            errors.append("unsupported_notice_relation")
    if data["participation_url"]:
        url = data["participation_url"]
        if not url.startswith(("http://", "https://")) or compact(url) not in compact("\n".join(pages)):
            errors.append("ungrounded_participation_url")
    return errors


def call_model(model: str, messages: list[dict], output_dir: Path, *, max_tokens: int = 2048) -> tuple[dict | None, dict]:
    output_dir.mkdir(parents=True, exist_ok=True)
    started = time.monotonic()
    receipt = {"model": model, "endpoint": ENDPOINT, "started_at": datetime.now().astimezone().isoformat(), "usage": None}
    payload = {"model": model, "messages": messages, "temperature": 0, "top_p": 1, "max_tokens": max_tokens, "enable_thinking": False, "response_format": {"type": "json_object"}, "stream": False}
    parsed = None
    key = ""
    try:
        key = credentials()
        response = requests.post(ENDPOINT, headers={"Authorization": "Bearer " + key}, json=payload, timeout=(15, 90))
        receipt.update(http_status=response.status_code, trace_id=response.headers.get("x-siliconcloud-trace-id"))
        receipt["raw_response"] = response.text
        body = response.json()
        if not isinstance(body, dict):
            raise ValueError("Provider response must be a JSON object")
        receipt["response"] = body
        receipt["usage"] = body.get("usage")
        receipt["reported_model"] = body.get("model")
        response.raise_for_status()
        if body.get("model") != model:
            raise ValueError("Provider did not confirm the requested model ID")
        choice = body["choices"][0]
        receipt["finish_reason"] = choice.get("finish_reason")
        if choice.get("finish_reason") != "stop":
            raise ValueError("incomplete_model_output:" + str(choice.get("finish_reason")))
        parsed = json.loads(choice["message"]["content"])
        if not isinstance(parsed, dict):
            raise ValueError("Model output must be a JSON object")
    except (requests.RequestException, ValueError, KeyError, IndexError, RuntimeError) as exc:
        receipt["error"] = type(exc).__name__ + ": " + str(exc)
        receipt["retryable"] = isinstance(exc, (requests.Timeout, requests.ConnectionError)) or receipt.get("http_status") in {408, 429, 500, 502, 503, 504}
    receipt["elapsed_seconds"] = round(time.monotonic() - started, 3)
    receipt["request_fingerprint"] = hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True).encode()).hexdigest()
    path = output_dir / (datetime.now().strftime("%Y%m%dT%H%M%S%f") + ".json")
    def redact(value):
        if isinstance(value, str):
            return value.replace(key, "[REDACTED]") if key else value
        if isinstance(value, dict):
            return {redact(k): redact(v) for k, v in value.items()}
        if isinstance(value, list):
            return [redact(v) for v in value]
        return value

    safe_receipt = redact(receipt)
    if safe_receipt != receipt:
        receipt = safe_receipt
        receipt["redacted_secret"] = True
    parsed = redact(parsed)
    path.write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + "\n")
    receipt["receipt_path"] = str(path)
    return parsed, receipt


def extract_notice(item: dict, models: list[str], run_dir: Path, *, max_calls: int | None = None) -> dict:
    pages = item["pages"]
    text = "\n\n".join(f"[PAGE {i}]\n{page}" for i, page in enumerate(pages, 1))
    if not text.strip() or sum(len(page) for page in pages) > 80000:
        return {"status": "failed", "data": None, "model": None, "attempts": [], "usage": {"known_total_tokens": 0, "calls_with_unknown_usage": 0}, "errors": ["PDF文字为空或超出本版本完整处理上限，需复核；未截断原文。"]}
    user = json.dumps({"id": item["id"], "stock_code": item["stock_code"], "publication_date": item["publication_date"], "title": item["title"]}, ensure_ascii=False) + "\n输出Schema：\n" + json.dumps(SCHEMA, ensure_ascii=False) + "\n完整逐页原文：\n" + text
    attempts = []
    usage = {"known_total_tokens": 0, "calls_with_unknown_usage": 0}
    all_errors = []
    queue = list(models)
    call_limit = max_calls if max_calls is not None else len(models) * 2
    retried = set()
    while queue and len(attempts) < call_limit:
        model = queue.pop(0)
        data, receipt = call_model(model, [{"role": "system", "content": SYSTEM}, {"role": "user", "content": user}], run_dir / "model-calls" / item["id"])
        errors = validate_evidence(data, pages, item) if data is not None else [receipt.get("error", "empty_response")]
        receipt["validation_errors"] = errors
        Path(receipt["receipt_path"]).write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + "\n")
        attempts.append(receipt)
        reported = receipt.get("usage")
        if isinstance(reported, dict) and isinstance(reported.get("total_tokens"), int):
            usage["known_total_tokens"] += reported["total_tokens"]
        else:
            usage["calls_with_unknown_usage"] += 1
        all_errors.extend(errors)
        if not errors:
            return {"status": "accepted", "data": data, "model": model, "attempts": attempts, "usage": usage, "errors": []}
        if receipt.get("retryable") and model not in retried:
            retried.add(model)
            queue.insert(0, model)
            time.sleep(1)
    return {"status": "failed", "data": None, "model": None, "attempts": attempts, "usage": usage, "errors": all_errors}
