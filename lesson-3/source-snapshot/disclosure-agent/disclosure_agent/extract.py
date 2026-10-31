from __future__ import annotations

import hashlib
import json
import os
import re
import time
import uuid
from datetime import date, datetime
from pathlib import Path

import jsonschema
import requests
from .scope import source_current_period, is_quarterly_briefing, _briefing_pattern, is_update_title

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
    context_year, context_month, previous_end = source_year, None, None
    for match in re.finditer(r"(?:(\d{4})年)?(?:(\d{1,2})月)?(\d{1,2})日", q):
        year, month, day = match.groups()
        if month is None and (year is not None or previous_end is None or
                              not re.fullmatch(r'[至到~—－–\-]', q[previous_end:match.start()])):
            continue
        if year is not None:
            context_year = int(year)
        if month is not None:
            context_month = int(month)
        if context_month == m and int(day) == d and context_year == y:
            return True
        previous_end = match.end()
    return False


def _time_in(value: str, quote: str) -> bool:
    h, m = map(int, value.split(":"))
    text, phase, previous_end = compact(quote), None, 0
    for match in re.finditer(r"(上午|早上|凌晨|中午|下午|晚上)?(?<!\d)(\d{1,2}):(\d{2})(?!\d)", text):
        qualifier, hour, minute = match.groups()
        bridge = text[previous_end:match.start()]
        phase = qualifier or (phase if re.fullmatch(r"[至到~—－–\-]*", bridge) else None)
        hour, minute = int(hour), int(minute)
        if phase in {"下午", "晚上"} and 1 <= hour <= 11:
            hour += 12
        if 0 <= hour <= 23 and 0 <= minute <= 59 and (hour, minute) == (h, m):
            return True
        previous_end = match.end()
    return False


def _source_period(text: str) -> str | None:
    from .scope import source_period
    return source_period(text)


def source_notice_numbers(header: str) -> list[tuple[str,str]]:
    text = '\n'.join(compact(line) for line in header.splitlines())
    pattern = (r'(?:公告编号|公告编码|编号|(?<!证券)(?<!债券)编码)[:：]?(?:第)?(?:临[-－—]?)?(\d{4})(?:临)?'
               r'(?:[-－—](?:临)?(\d+)|[\[【（(](\d+)[\]】）)]|(\d{3,4}))(?!\d)')
    return [(year, hyphenated or bracketed or joined) for year, hyphenated, bracketed, joined in
            re.findall(pattern, text)]


def evidence_text(evidence: dict, pages: list[str]) -> str | None:
    parts=evidence.get('parts') or [evidence]
    for part in parts:
        index=part['page']-1
        if not 0<=index<len(pages) or compact(part['quote']) not in compact(pages[index]):
            return None
    if 'parts' in evidence:
        first,second=parts
        if second['page']!=first['page']+1 or not compact(pages[first['page']-1]).endswith(compact(first['quote'])) or not compact(pages[second['page']-1]).startswith(compact(second['quote'])):
            return None
    return ''.join(part['quote'] for part in parts)


def _has_grounded_original_relation(data: dict, pages: list[str]) -> bool:
    relation = data.get("relation_evidence")
    number = compact(data.get("related_notice_number") or "").replace("－", "-").replace("—", "-").replace('临','')
    if not relation or not number or not 1 <= relation["page"] <= len(pages):
        return False
    quote = compact(relation["quote"])
    normalized = quote.replace("－", "-").replace("—", "-").replace('临','')
    number_pattern = re.escape(number) + r"(?!\d)"
    named_notice = re.search(r"(?:《[^》]*"+_briefing_pattern()+r"[^》]*(?:公告|通知)[^》]*》|原"+_briefing_pattern()+r"(?:公告|通知))"
                             r"[^。；;]{0,35}(?:公告)?编号[:：]?(?:临)?" + number_pattern, normalized)
    numbered_meeting = re.search(r"(?:公告)?编号[:：]?(?:临)?" + number_pattern
                                + r"[）)]?(?:项下|所述|中的)[^。；;]{0,20}"+_briefing_pattern(), normalized)
    return quote in compact(pages[relation["page"] - 1]) and bool(named_notice or numbered_meeting)


def _meeting_span(quote: str, kind: str) -> str:
    text = compact(quote)
    anchors = list(re.finditer(r"会议召开日期和时间[:：]?|会议召开时间[:：]?|会议时间[:：]?|说明会(?:召开)?时间(?:为)?[:：]?|召开时间[:：]?|活动时间(?:为)?[:：]?", text))
    if anchors:
        span = text[anchors[-1].end():]
    else:
        planned = re.search(r"(?:计划于|拟于|定于|将于)([^。；;！？!?]+?)(?:举行|召开|举办|参加)[^。；;！？!?]*"+_briefing_pattern(), text)
        subject_planned = re.search(r"(?:业绩)?说明会(?:计划|拟|定|将)(?:于|在)([^。；;！？!?]+?)(?:举行|召开|举办)",text)
        shifted = re.search(r"(?:"+_briefing_pattern()+r"|会议)([^。；]*?)(?:延期至|顺延至|变更为|调整为|改为|改至)([^。；]*)", text)
        if shifted and not re.search(r"提问|征集|截止|报名", shifted.group(1)):
            span = shifted.group(2)
        else:
            span = subject_planned.group(1) if subject_planned else planned.group(1) if planned else ""
    span = re.split(r"[。；;！？!?]|提问|征集|截止|报名|发布|披露", span, maxsplit=1)[0]
    if kind in {"change", "postponed"} and re.search(r"原计划|原定|原安排", text) and not re.search(r"变更为|延期至|顺延至|调整为|改为|改至|会议召开时间", text):
        return ""
    return span


def validate_evidence(data: dict, pages: list[str], metadata: dict | None = None) -> list[str]:
    errors = ["schema: " + error.message for error in jsonschema.Draft202012Validator(SCHEMA).iter_errors(data)]
    if errors:
        return errors
    first_text_page = next((page for page in pages if page.strip()), '')
    header = first_text_page
    numbers = source_notice_numbers(header)
    claimed = re.fullmatch(r"(?:临)?\s*(\d{4})\s*(?:临)?\s*[-－—]\s*(?:临)?\s*(\d+)", data.get("notice_number") or "")
    if not numbers or not claimed or (int(claimed[1]), int(claimed[2])) != (int(numbers[0][0]), int(numbers[0][1])):
        errors.append("unsupported_notice_number")
    title = (metadata or {}).get("title") or first_text_page.split("重要内容提示", 1)[0]
    current_period = source_current_period(title, pages)
    if data.get("report_period") != current_period:
        errors.append("unsupported_report_period")
    scope_title = compact((metadata or {}).get("title") or first_text_page.split("本公司", 1)[0])
    update_title = is_update_title(scope_title)
    completed = (not update_title and re.search(r"说明会.*召开情况|说明会.*举行情况|说明会.*纪要|说明会.*活动记录", scope_title))
    quarterly_collective = is_quarterly_briefing(scope_title) and '集体' in scope_title
    source_kind = ("completed" if completed else "initial" if quarterly_collective and not update_title
                   else "collective" if "集体接待" in scope_title else "other" if re.search(r"股东大会|股东会|权益分派|分红派息", scope_title) else None)
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
            if evidence_text(evidence,pages) is None:
                errors.append("ungrounded_quote:" + key)
    kind = data["notice_kind"]
    explicit_years = {int(year) for year in re.findall(r"(?<!\d)(\d{4})年", compact("\n".join(pages)))}
    source_year = next(iter(explicit_years)) if len(explicit_years) == 1 else None
    if kind not in ACTIVE_KINDS:
        for key in ["meeting_date", "start_time", "end_time", "previous_meeting_date", "previous_start_time", "previous_end_time", "question_deadline_date", "question_deadline_time", "participation_url", "meeting_evidence", "previous_meeting_evidence", "deadline_evidence", "relation_evidence"]:
            if data[key] is not None:
                errors.append("non_calendar_field:" + key)
        return errors
    linked_unknown_period = (data["report_period"] is None and kind in {"change", "postponed", "cancelled"}
                             and _has_grounded_original_relation(data, pages))
    if (not data["report_period"] and not linked_unknown_period) or not data["notice_number"]:
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
        literal=evidence_text(evidence,pages) or ''
        quote = _meeting_span(literal, kind) if evidence_key == "meeting_evidence" else literal
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
        normalize=lambda value:compact(value).replace('临','').replace('－','-').replace('—','-')
        if not relation or normalize(data["related_notice_number"]) not in normalize(relation["quote"]):
            errors.append("unsupported_notice_relation")
    if data["participation_url"]:
        url = data["participation_url"]
        if not url.startswith(("http://", "https://")) or compact(url) not in compact("\n".join(pages)):
            errors.append("ungrounded_participation_url")
    return errors


def build_request_payload(model: str, messages: list[dict], *, max_tokens: int = 2048) -> dict:
    return {"model": model, "messages": messages, "temperature": 0, "top_p": 1, "max_tokens": max_tokens,
            "enable_thinking": False, "response_format": {"type": "json_object"}, "stream": False}


def build_extraction_messages(item: dict) -> list[dict]:
    text = "\n\n".join(f"[PAGE {i}]\n{page}" for i, page in enumerate(item["pages"], 1))
    user = json.dumps({key: item[key] for key in ["id", "stock_code", "publication_date", "title"]}, ensure_ascii=False)
    user += "\n输出Schema：\n" + json.dumps(SCHEMA, ensure_ascii=False) + "\n完整逐页原文：\n" + text
    return [{"role": "system", "content": SYSTEM}, {"role": "user", "content": user}]


def compatible_extraction_contexts(item, models):
    path = ROOT / 'prompts/revalidation-compatibility.json'
    if not path.is_file():
        return {}
    manifest = json.loads(path.read_text())
    schema = json.dumps(SCHEMA, sort_keys=True)
    if (manifest.get('current_prompt_sha256') != PROMPT_HASH or
            manifest.get('schema_sha256') != hashlib.sha256(schema.encode()).hexdigest()):
        return {}
    previous = (ROOT / 'prompts' / manifest['previous_system_file']).read_text()
    previous_hash = hashlib.sha256((previous + schema).encode()).hexdigest()
    if previous_hash != manifest['previous_prompt_sha256']:
        return {}
    fingerprint = hashlib.sha256((previous_hash + json.dumps(models)).encode()).hexdigest()
    messages = build_extraction_messages(item)
    messages[0] = {'role': 'system', 'content': previous}
    return {fingerprint: messages}


def _write_receipt(path: Path, value: dict) -> None:
    temporary = path.with_name(path.name + "." + uuid.uuid4().hex[:12] + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")
    os.replace(temporary, path)


def call_model(model: str, messages: list[dict], output_dir: Path, *, max_tokens: int = 2048) -> tuple[dict | None, dict]:
    output_dir.mkdir(parents=True, exist_ok=True)
    started = time.monotonic()
    payload = build_request_payload(model, messages, max_tokens=max_tokens)
    path = output_dir / (datetime.now().strftime("%Y%m%dT%H%M%S%f") + "-" + uuid.uuid4().hex[:12] + ".json")
    receipt = {"model": model, "endpoint": ENDPOINT, "started_at": datetime.now().astimezone().isoformat(),
               "status": "started", "usage": None, "request": payload,
               "request_fingerprint": hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True).encode()).hexdigest()}
    parsed, key = None, ""

    def redact(value):
        if isinstance(value, str):
            return value.replace(key, "[REDACTED]") if key else value
        if isinstance(value, dict):
            return {redact(k): redact(v) for k, v in value.items()}
        if isinstance(value, list):
            return [redact(v) for v in value]
        return value

    def persist(value):
        _write_receipt(path, redact(value))

    try:
        key = credentials()
        persist(receipt)
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
        choices=body.get('choices')
        if not isinstance(choices,list) or not choices or not isinstance(choices[0],dict):
            raise ValueError('Provider choices must contain a JSON object')
        choice = choices[0]
        receipt["finish_reason"] = choice.get("finish_reason")
        if choice.get("finish_reason") != "stop":
            raise ValueError("incomplete_model_output:" + str(choice.get("finish_reason")))
        parsed = json.loads(choice["message"]["content"])
        if not isinstance(parsed, dict):
            raise ValueError("Model output must be a JSON object")
    except (requests.RequestException, ValueError, KeyError, IndexError, TypeError, RuntimeError) as exc:
        receipt["error"] = type(exc).__name__ + ": " + str(exc)
        receipt["retryable"] = isinstance(exc, (requests.Timeout, requests.ConnectionError)) or receipt.get("http_status") in {408, 429, 500, 502, 503, 504}
    receipt["status"] = "finished"
    receipt["finished_at"] = datetime.now().astimezone().isoformat()
    receipt["elapsed_seconds"] = round(time.monotonic() - started, 3)
    safe_receipt = redact(receipt)
    if safe_receipt != receipt:
        receipt = safe_receipt
        receipt["redacted_secret"] = True
    parsed = redact(parsed)
    persist(receipt)
    receipt["receipt_path"] = str(path)
    return parsed, receipt


def _correction_signatures(item, model, errors):
    source_hash = item.get('pdf_sha256') or hashlib.sha256(json.dumps(item['pages'], ensure_ascii=False).encode()).hexdigest()
    atoms = {error.split(':', 1)[0] if error.startswith('schema:') else error for error in errors}
    return {hashlib.sha256(json.dumps([source_hash, model, atom], ensure_ascii=False).encode()).hexdigest()
            for atom in atoms}


def _used_corrections(item, model, receipts):
    used = set()
    for receipt in receipts:
        if receipt.get('model') != model:
            continue
        for message in receipt.get('request', {}).get('messages', [])[2:]:
            content = message.get('content', '')
            if message.get('role') != 'user' or not content.startswith('程序校验未通过：'):
                continue
            try:
                errors, _ = json.JSONDecoder().raw_decode(content.split('：', 1)[1])
                if isinstance(errors, list) and all(isinstance(error, str) for error in errors):
                    used.update(_correction_signatures(item, model, errors))
            except (ValueError, TypeError):
                continue
    return used


def _correction_messages(item, model, data, errors, base):
    instruction = ('。请对照上面的完整原文修正完整JSON。连续引文必须包含字段用途；会议句要包含举行或召开说明会，'
                   '下午时刻转为24小时。不得猜测、跳过正文或拼接原文。真实相邻页截止仅可逐物理页使用parts。')
    if is_quarterly_briefing(item.get('title', '')) and '集体' in item.get('title', ''):
        instruction += ('本公告明确本公司当前三季报业绩说明会，采用集体组织方式也属于initial；'
                        'collective仅用于范围外的泛集体接待活动。请提取当前本公司的会议、提问和参与安排。')
    signatures = json.dumps(sorted(_correction_signatures(item, model, errors)))
    return base + [{'role': 'assistant', 'content': json.dumps(data, ensure_ascii=False)},
                   {'role': 'user', 'content': '程序校验未通过：' + json.dumps(errors, ensure_ascii=False)
                    + instruction + '\n纠正问题签名：' + signatures}]


def extract_notice(item: dict, models: list[str], run_dir: Path, *, max_calls: int | None = None, recovered_attempts=(), max_transient_attempts=4) -> dict:
    pages = item["pages"]
    text = "\n\n".join(f"[PAGE {i}]\n{page}" for i, page in enumerate(pages, 1))
    if not text.strip() or sum(len(page) for page in pages) > 80000:
        return {"status": "failed", "data": None, "model": None, "attempts": [], "usage": {"known_total_tokens": 0, "calls_with_unknown_usage": 0}, "errors": ["PDF文字为空或超出本版本完整处理上限，需复核；未截断原文。"]}
    attempts = []
    usage = {"known_total_tokens": 0, "calls_with_unknown_usage": 0}
    all_errors = []
    queue = list(models)
    call_limit = max_calls if max_calls is not None else len(models) * 2
    retried = set()
    feedback_messages = {}
    base_messages = build_extraction_messages(item)
    reused=list(recovered_attempts)
    if reused:
        last=reused[-1];model=last['model']
        prior_data=None;prior_errors=[last.get('error','unreadable_prior_response')];content_receipt=last
        for saved in ([last] if last.get('retryable') else reversed(reused)):
            if saved.get('model') != model:
                continue
            try:
                if saved.get('error') or saved.get('response',{}).get('model')!=model or saved['response']['choices'][0].get('finish_reason')!='stop':
                    continue
                prior_data=json.loads(saved['response']['choices'][0]['message']['content'])
                prior_errors=validate_evidence(prior_data,pages,item)
                content_receipt=saved
                break
            except (ValueError,KeyError,IndexError,TypeError):
                continue
        all_errors.extend(prior_errors)
        queue=queue[queue.index(model)+1:] if model in queue else queue
        if not queue:
            current = _correction_signatures(item, model, prior_errors)
            previous = _correction_signatures(item, model, content_receipt.get('validation_errors') or prior_errors)
            unused = current - _used_corrections(item, model, reused)
            content_attempts = sum(receipt['model'] == model and not receipt.get('retryable') for receipt in reused)
            new_rule_errors = unused - previous
            if prior_data is not None and unused and (content_attempts < 2 or new_rule_errors):
                feedback_messages[model] = _correction_messages(item, model, prior_data, prior_errors, base_messages)
                queue=[model];retried.add(model)
            elif last.get('retryable') and sum(receipt['model']==model and bool(receipt.get('retryable')) for receipt in reused)<max_transient_attempts:
                queue=[model];retried.add(model)
                feedback_messages[model]=base_messages + last.get('request',{}).get('messages',[])[2:]
    while queue and len(attempts) < call_limit:
        model = queue.pop(0)
        data, receipt = call_model(model, feedback_messages.get(model, base_messages), run_dir / "model-calls" / item["id"])
        errors = validate_evidence(data, pages, item) if data is not None else [receipt.get("error", "empty_response")]
        receipt["validation_errors"] = errors
        _write_receipt(Path(receipt["receipt_path"]), receipt)
        attempts.append(receipt)
        reported = receipt.get("usage")
        if isinstance(reported, dict) and isinstance(reported.get("total_tokens"), int):
            usage["known_total_tokens"] += reported["total_tokens"]
        else:
            usage["calls_with_unknown_usage"] += 1
        all_errors.extend(errors)
        if not errors:
            return {"status": "accepted", "data": data, "model": model, "attempts": attempts, "reused_attempts":reused,"usage": usage, "errors": []}
        if receipt.get("retryable") and model not in retried:
            retried.add(model)
            queue.insert(0, model)
            time.sleep(1)
        elif data is not None and not queue and model not in retried and len(attempts) < call_limit:
            retried.add(model)
            feedback_messages[model] = _correction_messages(item, model, data, errors, base_messages)
            queue.append(model)
    return {"status": "failed", "data": None, "model": None, "attempts": attempts, "reused_attempts":reused,
            "last_retryable":bool((attempts or reused) and (attempts or reused)[-1].get('retryable')),"usage": usage, "errors": all_errors}
