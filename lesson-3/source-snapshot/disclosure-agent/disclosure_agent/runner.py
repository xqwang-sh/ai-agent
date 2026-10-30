from __future__ import annotations

from contextlib import contextmanager
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import time
import uuid
from zoneinfo import ZoneInfo

from .cninfo import CninfoSource
from .extract import PROMPT_HASH, call_model, extract_notice, validate_evidence
from .ledger import merge

ROOT = Path(__file__).resolve().parents[1]
BUSINESS_TZ = ZoneInfo("Asia/Shanghai")


def write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + "." + uuid.uuid4().hex + ".tmp")
    temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n")
    os.replace(temporary, path)


def write_text(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + "." + uuid.uuid4().hex + ".tmp")
    temporary.write_text(value)
    os.replace(temporary, path)


def load_publication(workspace: Path) -> tuple[dict, dict]:
    pointer = workspace / "current.json"
    if pointer.exists():
        manifest = json.loads(pointer.read_text())
        run_id = manifest.get("run_id")
        required = {"state.json", "summary.json", "calendar.html"}
        if not isinstance(run_id, str) or not run_id or Path(run_id).name != run_id or run_id in {".", ".."} or set(manifest.get("artifacts", {})) != required:
            raise ValueError("结果提交指针必须绑定同一运行的三项完整产物。")
        for name, info in manifest["artifacts"].items():
            target = (workspace / info["path"]).resolve()
            expected = (workspace / "runs" / run_id / name).resolve()
            if target != expected or not target.is_relative_to((workspace / "runs").resolve()) or hashlib.sha256(target.read_bytes()).hexdigest() != info["sha256"]:
                raise ValueError("已发布结果指纹不匹配：" + name)
        state = json.loads((workspace / manifest["artifacts"]["state.json"]["path"]).read_text())
        summary = json.loads((workspace / manifest["artifacts"]["summary.json"]["path"]).read_text())
        if state.get("last_run_id") != run_id or summary.get("run_id") != run_id:
            raise ValueError("提交指针与产物内部的运行编号不一致。")
        return state, summary
    if any((workspace / name).exists() for name in ["state.json", "summary.json"]) or any((workspace / "runs").glob("*/summary.json")):
        raise ValueError("结果提交指针current.json缺失，请核验历史运行后恢复；便捷副本不能作为恢复依据。")
    return {}, {}


def load_state(workspace: Path) -> dict:
    return load_publication(workspace)[0]


def publish(workspace: Path, run_dir: Path, state: dict, summary: dict) -> dict:
    summary = {**summary, "output_html": str(run_dir / "calendar.html")}
    write_json(run_dir / "state.json", state)
    write_json(run_dir / "summary.json", summary)
    write_text(run_dir / "calendar.html", render_calendar(state, summary, workspace))
    artifacts = {name: {"path": str((run_dir / name).relative_to(workspace)), "sha256": hashlib.sha256((run_dir / name).read_bytes()).hexdigest()} for name in ["state.json", "summary.json", "calendar.html"]}
    write_json(workspace / "current.json", {"run_id": summary["run_id"], "artifacts": artifacts})
    projection_errors = []
    for name in artifacts:
        try:
            write_text(workspace / name, (run_dir / name).read_text())
        except OSError as exc:
            projection_errors.append({"file": name, "error": type(exc).__name__})
    if projection_errors:
        summary = {**summary, "convenience_copy_errors": projection_errors}
    return summary


def load_config(path: Path) -> dict:
    config = json.loads(Path(path).read_text())
    companies = config.get("companies")
    if not isinstance(companies, list) or not 1 <= len(companies) <= 10:
        raise ValueError("配置需要1至10家明确的覆盖公司。")
    if len({c.get("code") for c in companies}) != len(companies):
        raise ValueError("公司代码不能重复。")
    for company in companies:
        if not re.fullmatch(r"\d{6}", company.get("code", "")) or not company.get("name"):
            raise ValueError("公司须有6位代码与名称。")
    if not isinstance(config.get("models"), list) or not 1 <= len(config["models"]) <= 3 or not all(isinstance(m, str) and m for m in config["models"]):
        raise ValueError("显式配置1至3个已核验可用的模型。")
    if config.get("strategy", "fixed") not in {"fixed", "adaptive"}:
        raise ValueError("strategy只能为fixed或adaptive。")
    if config.get("timezone", "Asia/Shanghai") != "Asia/Shanghai":
        raise ValueError("本课程版业务时区为Asia/Shanghai。")
    for field, default, upper in [("lookback_days", 90, 366), ("overlap_days", 7, 30), ("max_model_calls", 20, 60), ("max_planner_steps", 12, 24)]:
        value = config.setdefault(field, default)
        if not isinstance(value, int) or not 1 <= value <= upper:
            raise ValueError("配置值超出本版本界限：" + field)
    if type(config.setdefault("reuse_extractions", True)) is not bool:
        raise ValueError("reuse_extractions须为布尔值。")
    return config


@contextmanager
def run_lock(workspace: Path):
    handle = (workspace / "run.lock").open("a+b")
    locked = False
    try:
        if os.name == "nt":
            import msvcrt
            handle.write(b"0")
            handle.flush()
            handle.seek(0)
            try:
                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
                locked = True
            except OSError:
                pass
        else:
            import fcntl
            try:
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                locked = True
            except BlockingIOError:
                pass
        yield locked
    finally:
        if locked:
            if os.name == "nt":
                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        handle.close()


def _program_hash() -> str:
    paths = [ROOT / "run_agent.py"] + sorted(p for p in (ROOT / "disclosure_agent").iterdir() if p.suffix in {".py", ".js", ".css"}) + sorted((ROOT / "prompts").glob("*"))
    values = {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths if p.is_file()}
    return hashlib.sha256(json.dumps(values, sort_keys=True).encode()).hexdigest()


def _fixture_sources(path: Path, config: dict, workspace: Path) -> tuple[dict, str]:
    from pypdf import PdfReader

    data = json.loads(path.read_text())
    as_of = datetime.fromisoformat(data["as_of"])
    if as_of.tzinfo is None:
        raise ValueError("历史重放必须包含明确时区。")
    results = {}
    for company in config["companies"]:
        code = company["code"]
        failed = code in data.get("failed_companies", [])
        items = []
        for source in data.get("items", []):
            if source["stock_code"] != code:
                continue
            if source["publication_date"] > as_of.date().isoformat():
                raise ValueError("重放包含截止日之后发布的公告。")
            pdf = (path.parent / source["pdf_path"]).resolve()
            raw = pdf.read_bytes()
            digest = hashlib.sha256(raw).hexdigest()
            if source.get("pdf_sha256") and source["pdf_sha256"] != digest:
                raise ValueError("重放PDF指纹不匹配。")
            pages = [page.extract_text(extraction_mode="layout") or "" for page in PdfReader(pdf).pages]
            items.append({**source, "pdf_sha256": digest, "pdf_path": str(pdf), "pages": pages})
        results[code] = {"company": company, "status": "failed" if failed else "complete", "query_complete": not failed, "items": [] if failed else items, "failed_items": [], "error": "明确标注的课堂故障注入" if failed else None, "query": {"mode": "historical_replay"}}
    return results, as_of.isoformat()


def render_calendar(state: dict, summary: dict, workspace: Path) -> str:
    from .presentation import render_product
    return render_product(state, summary)


def run(config_path: Path, workspace: Path, trigger: str = "manual", fixture: Path | None = None, claim_id: str | None = None) -> dict:
    config = load_config(config_path)
    workspace = Path(workspace).resolve()
    workspace.mkdir(parents=True, exist_ok=True)
    with run_lock(workspace) as locked:
        if not locked:
            return {"status": "skipped_overlap", "run_id": None}
        return _run(config, workspace, trigger, fixture, claim_id)


def _run(config: dict, workspace: Path, trigger: str, fixture: Path | None, claim_id: str | None = None) -> dict:
    start_clock = time.monotonic()
    started_at = datetime.now(timezone.utc).isoformat()
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S") + "-" + uuid.uuid4().hex[:8]
    run_dir = workspace / "runs" / run_id
    run_dir.mkdir(parents=True)
    previous = load_state(workspace)
    mode = "historical_replay" if fixture else "live"
    if previous and previous.get("mode") != mode:
        raise ValueError("实时与历史重放必须使用不同工作区。")
    as_of = datetime.now(BUSINESS_TZ).isoformat()
    before_hash = _program_hash()
    fingerprint = hashlib.sha256((PROMPT_HASH + json.dumps(config["models"])).encode()).hexdigest()
    write_json(run_dir / "start.json", {"run_id": run_id, "mode": mode, "trigger": trigger, "schedule_claim_id": claim_id, "started_at": started_at, "program_sha256": before_hash, "prompt_sha256": PROMPT_HASH, "config": config})
    source = CninfoSource(workspace, run_dir)
    fixture_data = None
    if fixture:
        fixture_data, as_of = _fixture_sources(Path(fixture).resolve(), config, workspace)
    acquired, coverage, pending, records, attempts = {}, {}, {}, [], []
    planner_receipts, planner_errors, trace = [], [], []
    extraction_errors = []
    invalidated_sources = set()
    cached_ids = []

    def query(company):
        code = company["code"]
        last = previous.get("companies", {}).get(code, {}).get("last_success")
        start = datetime.fromisoformat(last) - timedelta(days=config["overlap_days"]) if last else datetime.fromisoformat(as_of) - timedelta(days=config["lookback_days"])
        result = fixture_data[code] if fixture_data else source.acquire(company, start.date().isoformat(), datetime.fromisoformat(as_of).date().isoformat())
        acquired[code] = result
        coverage[code] = {"status": result["status"], "query_complete": result["query_complete"], "processing_complete": not result["failed_items"], "query": result["query"], "error": result.get("error"), "failed_items": result["failed_items"], "announcement_count": len(result["items"])}
        for item in result["items"]:
            pending[item["id"]] = item
        if result["query_complete"]:
            from pypdf import PdfReader
            for source_id, old in previous.get("notices", {}).items():
                if old["stock_code"] != code or source_id in pending:
                    continue
                try:
                    pdf = Path(old["pdf_path"])
                    if hashlib.sha256(pdf.read_bytes()).hexdigest() != old["pdf_sha256"]:
                        raise ValueError("归档PDF指纹不匹配")
                    item = {field: old.get(field) for field in ["id", "stock_code", "company", "org_id", "title", "publication_date", "pdf_url", "url", "pdf_sha256", "pdf_path"]}
                    item["pages"] = [page.extract_text(extraction_mode="layout") or "" for page in PdfReader(pdf).pages]
                    pending[source_id] = item
                except Exception as exc:
                    coverage[code]["processing_complete"] = False
                    invalidated_sources.add(source_id)
                    extraction_errors.append({"stock_code": code, "source_id": source_id, "reason": "archived_source_unavailable", "error": type(exc).__name__})
        trace.append({"action": "query_company", "id": code, "status": result["status"], "notice_ids": [x["id"] for x in result["items"]]})

    def process(source_id):
        item = pending.pop(source_id)
        old = previous.get("notices", {}).get(source_id)
        cached_errors = validate_evidence(old["extraction"], item["pages"], item) if old and old.get("extraction") else []
        receipts = (old or {}).get("model_receipts", [])
        receipts_intact = bool(receipts) and all(Path(r["path"]).is_file() and hashlib.sha256(Path(r["path"]).read_bytes()).hexdigest() == r["sha256"] for r in receipts)
        if old and (cached_errors or not receipts_intact or old.get("pdf_sha256") != item["pdf_sha256"] or old.get("extractor_fingerprint") != fingerprint):
            invalidated_sources.add(source_id)
        if config["reuse_extractions"] and old and old.get("pdf_sha256") == item["pdf_sha256"] and old.get("extractor_fingerprint") == fingerprint and not cached_errors and receipts_intact:
            cached_ids.append(source_id)
            trace.append({"action": "extract_notice", "id": source_id, "status": "cached_revalidated"})
            return
        remaining = config["max_model_calls"] - len(attempts)
        if remaining <= 0:
            extraction_errors.append({"stock_code": item["stock_code"], "source_id": source_id, "reason": "model_budget_exhausted"})
            coverage[item["stock_code"]]["processing_complete"] = False
            return
        result = extract_notice(item, config["models"][:remaining], run_dir, max_calls=remaining)
        attempts.extend(result["attempts"])
        trace.append({"action": "extract_notice", "id": source_id, "status": result["status"], "model": result["model"], "validation_failures": result["errors"]})
        if result["status"] != "accepted":
            coverage[item["stock_code"]]["processing_complete"] = False
            extraction_errors.append({"stock_code": item["stock_code"], "source_id": source_id, "reason": "extraction_failed", "errors": result["errors"]})
            return
        record = {key: value for key, value in item.items() if key != "pages"}
        raw = re.sub(r"\s+", "", "\n".join(item["pages"]))
        model_receipts = [{"path": r["receipt_path"], "sha256": hashlib.sha256(Path(r["receipt_path"]).read_bytes()).hexdigest()} for r in result["attempts"]]
        record.update(extraction=result["data"], model=result["model"], extractor_fingerprint=fingerprint, extraction_run_id=run_id, model_receipts=model_receipts, revision_reason="extraction_revision" if old else "new_source", source_flags={"other_fields_unchanged": bool(re.search(r"其他.{0,12}(不变|无变|未变)|其余.{0,12}(不变|无变|未变)", raw))})
        records.append(record)

    if config.get("strategy", "fixed") == "fixed":
        for company in config["companies"]:
            query(company)
        for source_id in sorted(pending, key=lambda key: (pending[key]["publication_date"], key)):
            process(source_id)
    else:
        for step in range(config["max_planner_steps"]):
            unqueried = [c for c in config["companies"] if c["code"] not in acquired]
            allowed = [{"action": "query_company", "id": c["code"]} for c in unqueried] + [{"action": "extract_notice", "id": i} for i in pending]
            if not allowed:
                allowed = [{"action": "finish", "id": None}]
            state = {"available_actions": allowed, "unqueried_companies": unqueried, "pending_announcements": [{"id": i["id"], "title": i["title"], "stock_code": i["stock_code"]} for i in pending.values()], "completed_tools": trace, "rejected_actions": planner_errors}
            instructions = "你为投研团队选择下一步工具。只返回JSON对象{action,id}，必须从available_actions中原样选择一个。列表中没有finish就不能结束。extract_notice表示读取并提取一份待处理公告，它不是查询公司的同义词。根据待办选择顺序，不能自创公司、ID或URL。此前被拒的动作不能重复。"
            action, receipt = call_model(config.get("planner_model", config["models"][0]), [{"role": "system", "content": instructions}, {"role": "user", "content": json.dumps(state, ensure_ascii=False)}], run_dir / "planner-calls", max_tokens=512)
            planner_receipts.append(receipt)
            name, identity = (action or {}).get("action"), str((action or {}).get("id", ""))
            if name == "query_company" and identity in {c["code"] for c in unqueried}:
                query(next(c for c in unqueried if c["code"] == identity))
            elif name == "extract_notice" and identity in pending:
                process(identity)
            elif name == "finish" and not unqueried and not pending:
                break
            else:
                planner_errors.append({"reason": "invalid_or_premature_tool", "action": action, "error": receipt.get("error")})
                if len(planner_errors) >= 2:
                    break
        if pending:
            planner_errors.append({"reason": "planner_left_unprocessed_notices", "ids": list(pending)})
            for item in pending.values():
                coverage[item["stock_code"]]["processing_complete"] = False
        for company in config["companies"]:
            if company["code"] not in coverage:
                coverage[company["code"]] = {"status": "failed", "query_complete": False, "processing_complete": False, "error": "planner_did_not_query_company"}
    for event in previous.get("events", {}).values():
        if invalidated_sources.intersection(event["source_ids"]):
            event["validity"] = "needs_review"
    state, changes, issues = merge(previous, records, coverage, run_id, as_of)
    for change in changes:
        if change["kind"] == "new" and not previous.get("companies", {}).get(change["stock_code"], {}).get("baseline_complete"):
            change["kind"] = "baseline"
    for code, item in coverage.items():
        if item.get("query_complete") and item.get("processing_complete"):
            state["companies"][code]["baseline_complete"] = True
    issues.extend(extraction_errors)
    issues.extend(planner_errors)
    state["mode"] = mode
    state["last_run_id"] = run_id
    if _program_hash() != before_hash:
        raise RuntimeError("运行期间程序或提示词发生修改，本次不发布新状态。")
    receipts = attempts + planner_receipts
    known_tokens = sum(r["usage"]["total_tokens"] for r in receipts if isinstance(r.get("usage"), dict) and isinstance(r["usage"].get("total_tokens"), int))
    unknown_usage = sum(not isinstance(r.get("usage"), dict) or not isinstance(r["usage"].get("total_tokens"), int) for r in receipts)
    all_covered = all(c.get("status") == "complete" and c.get("query_complete") and c.get("processing_complete") for c in coverage.values())
    status = "complete" if all_covered and not issues else "needs_review" if all_covered else "incomplete"
    summary = {"run_id": run_id, "status": status, "mode": mode, "strategy": config.get("strategy", "fixed"), "trigger": trigger, "schedule_claim_id": claim_id, "as_of": as_of, "started_at": started_at, "finished_at": datetime.now(timezone.utc).isoformat(), "elapsed_seconds": round(time.monotonic() - start_clock, 3), "program_sha256": before_hash, "prompt_sha256": PROMPT_HASH, "model_calls": len(attempts), "planner_calls": len(planner_receipts), "cached_notice_ids": cached_ids, "usage": {"known_total_tokens": known_tokens, "calls_with_unknown_usage": unknown_usage}, "coverage": coverage, "changes": changes, "issues": issues, "event_count": len(state["events"]), "trace": trace, "output_html": str(workspace / "calendar.html")}
    write_json(run_dir / "processed-records.json", {"records": records})
    return publish(workspace, run_dir, state, summary)
