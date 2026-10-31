"""Run-bound company identities for the calendar's local watchlist."""
import hashlib
import json
from pathlib import Path
import re

COMPANY_TABLE_URL = "https://www.cninfo.com.cn/new/data/szse_stock.json"


def directory_for_run(workspace, summary, state):
    workspace = Path(workspace).resolve()
    origin=summary.get('presentation_origin')
    if origin:
        run_id=origin.get('run_id')
        if not isinstance(run_id,str) or Path(run_id).name!=run_id or run_id in {'.','..'}:
            raise ValueError('Invalid presentation identity source')
        original=workspace/'runs'/run_id/'calendar.html'
        raw=original.read_bytes()
        if hashlib.sha256(raw).hexdigest()!=origin.get('calendar_sha256'):
            raise ValueError('Presentation identity source failed integrity verification')
        match=re.search(r'<script id="calendar-data" type="application/json">(.*?)</script>',raw.decode())
        if not match:
            raise ValueError('Presentation identity source has no company directory')
        directory=json.loads(match[1]).get('company_directory')
        if not isinstance(directory,dict) or not isinstance(directory.get('rows'),list):
            raise ValueError('Presentation identity source has no company directory')
        directory['source']['bound_run_id']=summary['run_id']
        return directory
    table = workspace / 'runs' / summary['run_id'] / 'source/company-table.json'
    if table.is_file():
        return company_directory(table, run_id=summary['run_id'])
    queue_path = workspace / 'market-queue.json'
    if summary.get('scope', {}).get('universe') == 'a_share' and queue_path.is_file():
        queue = json.loads(queue_path.read_text())
        source = Path(queue['universe_path']).resolve()
        if not source.is_relative_to(workspace) or hashlib.sha256(source.read_bytes()).hexdigest() != queue['universe_sha256']:
            raise ValueError('Saved A-share company table failed integrity verification')
        directory = company_directory(source)
        directory['source']['bound_run_id'] = summary['run_id']
        directory['source']['basis'] = 'hash-verified retained market source; no fresh company-table query in this run'
        return directory
    if summary.get('scope', {}).get('universe') == 'a_share' and state.get('events'):
        raise ValueError('No verified A-share company table; retaining the previous product')
    return company_directory(events=state.get('events', {}).values(), run_id=summary['run_id'])


def company_directory(path=None, *, run_id=None, events=()):
    if path is None:
        rows = [{"code": event["stock_code"], "name": event["company"],
                 "org_id": "event:" + event["stock_code"]} for event in events]
        return {"rows": rows, "source": {"complete": False, "run_id": run_id}}
    raw = Path(path).read_bytes()
    table = json.loads(raw)
    if not isinstance(table.get("stockList"), list):
        raise ValueError("Company table has no stockList")
    rows = []
    for row in table["stockList"]:
        if row.get("category") != "A股":
            continue
        code, name, identity = row.get("code"), row.get("zwjc"), row.get("orgId")
        if not re.fullmatch(r"\d{6}", code or "") or not name or not identity:
            raise ValueError("Company table contains an incomplete A-share identity")
        rows.append({"code": code, "name": name, "org_id": identity})
    if not rows:
        raise ValueError("Company table contains no A-share identities")
    return {"rows": rows, "source": {"complete": True, "run_id": run_id,
            "url": COMPANY_TABLE_URL, "sha256": hashlib.sha256(raw).hexdigest()}}
