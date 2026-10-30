import hashlib
import json
import plistlib
import subprocess
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock
from zoneinfo import ZoneInfo

import pytest
import requests
from disclosure_agent import cninfo, schedule


class Response:
    def __init__(self, data=None, raw=None, status=200, headers=None):
        self.content = raw if raw is not None else json.dumps(data).encode()
        self.status_code, self.headers, self.closed = status, headers or {}, False
    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(str(self.status_code))
    def iter_content(self, size):
        yield self.content
    def close(self):
        self.closed = True


COMPANY = {'code': '600887', 'name': '伊利股份'}
TABLE = {'stockList': [{'code': '600887', 'zwjc': '伊利股份', 'orgId': 'gssh0600887'}]}
ROW = {'secCode': '600887', 'orgId': 'gssh0600887', 'announcementId': '12345',
       'announcementTitle': '召开业绩说明会公告', 'announcementTime': 1788278400000,
       'adjunctUrl': 'finalpage/2026-09-02/12345.PDF'}


def source(tmp_path, monkeypatch, responses):
    instance = cninfo.CninfoSource(tmp_path / 'workspace', tmp_path / 'run')
    instance.session.request = Mock(side_effect=[Response(TABLE), *responses])
    instance.session.get = Mock(return_value=Response(raw=b'%PDF-1.7\n' + b'A' * 100))
    monkeypatch.setattr(cninfo, 'PdfReader', lambda stream: SimpleNamespace(pages=[SimpleNamespace(extract_text=lambda **kwargs: '真实页文本')]))
    return instance


def test_valid_zero_and_evidence(tmp_path, monkeypatch):
    obj = source(tmp_path, monkeypatch, [Response({'totalAnnouncement': 0, 'hasMore': False, 'announcements': None})])
    result = obj.acquire(COMPANY, '2026-01-01', '2026-10-30')
    assert result['status'] == 'complete' and result['query_complete'] and not result['items']
    archive = tmp_path / 'run/source/600887'
    assert json.loads((archive / 'query-001.request.json').read_text())['params']['stock'] == '600887,gssh0600887'
    assert (archive / 'query-001.json').exists()
    obj.session.get.assert_not_called()


@pytest.mark.parametrize('payload', [b'<html>blocked</html>', b'{}', b'{"hasMore": false, "totalAnnouncement": "0"}', b'{"hasMore": true, "totalAnnouncement": 0, "announcements": []}'])
def test_abnormal_response_is_not_zero(tmp_path, monkeypatch, payload):
    obj = source(tmp_path, monkeypatch, [Response(raw=payload)])
    result = obj.acquire(COMPANY, '2026-01-01', '2026-10-30')
    assert result['status'] == 'failed' and not result['query_complete'] and result['error']
    assert (tmp_path / 'run/source/600887/query-001.json').read_bytes() == payload


def test_failed_second_page_keeps_successful_pdf(tmp_path, monkeypatch):
    obj = source(tmp_path, monkeypatch, [Response({'totalAnnouncement': 2, 'hasMore': True, 'announcements': [ROW]}), requests.Timeout('second page')])
    result = obj.acquire(COMPANY, '2026-01-01', '2026-10-30')
    assert result['status'] == 'failed' and not result['query_complete']
    item, = result['items']
    assert item['pages'] == ['真实页文本'] and Path(item['pdf_path']).is_file()
    assert item['pdf_sha256'] in item['pdf_path'] and 'Timeout' in result['error']


def test_download_failure_keeps_other_item(tmp_path, monkeypatch):
    obj = source(tmp_path, monkeypatch, [Response({'totalAnnouncement': 2, 'hasMore': False, 'announcements': [ROW, {**ROW, 'announcementId': '12346'}]})])
    obj.session.get.side_effect = [Response(raw=b'%PDF-1.7\n' + b'A' * 100), Response(raw=b'<html>bad</html>')]
    result = obj.acquire(COMPANY, '2026-01-01', '2026-10-30')
    assert result['query_complete'] and result['status'] == 'failed'
    assert [x['id'] for x in result['items']] == ['12345'] and result['failed_items'][0]['id'] == '12346'


@pytest.mark.parametrize('raw,headers', [(b'%PDF-', {}), (b'A' * 100, {}), (b'%PDF-' + b'A' * 100, {'Content-Length': '99999999'})])
def test_pdf_header_and_size(tmp_path, monkeypatch, raw, headers):
    obj = source(tmp_path, monkeypatch, [Response({'totalAnnouncement': 1, 'hasMore': False, 'announcements': [ROW]})])
    response = Response(raw=raw, headers=headers)
    obj.session.get.return_value = response
    result = obj.acquire(COMPANY, '2026-01-01', '2026-10-30')
    assert result['status'] == 'failed' and not result['items'] and response.closed


def test_pdf_stream_limit(tmp_path, monkeypatch):
    monkeypatch.setattr(cninfo, 'MAX_PDF_BYTES', 80)
    obj = source(tmp_path, monkeypatch, [Response({'totalAnnouncement': 1, 'hasMore': False, 'announcements': [ROW]})])
    assert 'size limit' in obj.acquire(COMPANY, '2026-01-01', '2026-10-30')['failed_items'][0]['error']


def test_identity_mismatch(tmp_path, monkeypatch):
    obj = source(tmp_path, monkeypatch, [])
    assert obj.acquire({'code': '600887', 'name': 'Wrong'}, '2026-01-01', '2026-10-30')['status'] == 'failed'
    assert obj.session.request.call_count == 1


def test_empty_text_is_failure(tmp_path, monkeypatch):
    obj = source(tmp_path, monkeypatch, [Response({'totalAnnouncement': 1, 'hasMore': False, 'announcements': [ROW]})])
    monkeypatch.setattr(cninfo, 'PdfReader', lambda stream: SimpleNamespace(pages=[SimpleNamespace(extract_text=lambda **kwargs: '')]))
    assert obj.acquire(COMPANY, '2026-01-01', '2026-10-30')['failed_items']


def plan(tmp_path, monkeypatch, now):
    workspace, project = tmp_path / 'work', tmp_path / 'project'
    project.mkdir()
    (project / 'run_agent.py').write_text('')
    config = project / 'config.json'
    config.write_text('{}')
    monkeypatch.setattr(schedule, '_now', lambda: now)
    monkeypatch.setattr(schedule.platform, 'system', lambda: 'Darwin')
    monkeypatch.setattr(schedule.Path, 'home', lambda: tmp_path / 'home')
    calls = []
    monkeypatch.setattr(schedule, '_os_command', lambda args: calls.append(args) or {'returncode': 0, 'stdout': 'state = waiting', 'stderr': ''})
    schedule.install(config, workspace, project)
    return workspace, project, config, calls


NOW = datetime(2026, 10, 30, 8, 0, tzinfo=ZoneInfo('Asia/Shanghai'))


def test_launchd_tick_configuration(tmp_path, monkeypatch):
    workspace, project, config, calls = plan(tmp_path, monkeypatch, NOW)
    stored = schedule._load(workspace)
    payload = plistlib.loads(Path(stored['task_path']).read_bytes())
    assert payload['StartInterval'] == 60 and payload['RunAtLoad'] is False
    assert payload['ProgramArguments'][1:3] == [str(project / 'run_agent.py'), 'tick']
    assert Path(payload['ProgramArguments'][0]).is_absolute()
    assert calls[0][:2] == ['launchctl', 'bootstrap']
    assert stored['timezone'] == 'Asia/Shanghai' and stored['platform_verified'] is False


def test_tick_claim_once_and_evidence(tmp_path, monkeypatch):
    workspace, project, config, calls = plan(tmp_path, monkeypatch, NOW)
    assert schedule.test_after(workspace, 90)['mode'] == 'real_os_tick'
    monkeypatch.setattr(schedule, '_now', lambda: NOW + timedelta(seconds=91))
    runner = Mock(return_value=subprocess.CompletedProcess([], 0, '{"run_id":"example-run"}', ''))
    monkeypatch.setattr(schedule.subprocess, 'run', runner)
    record = schedule.tick(config, workspace, project)
    assert record['run_id'] == 'example-run' and record['kind'] == 'test' and record['exit_code'] == 0
    assert Path(record['evidence_path']).is_file() and '--trigger' in runner.call_args.args[0]
    assert schedule.tick(config, workspace, project)['status'] == 'not_due'
    runner.assert_called_once()
    assert schedule._load(workspace)['test_due'] is None and schedule._load(workspace)['enabled']


def test_business_time_and_claim(tmp_path, monkeypatch):
    workspace, project, config, calls = plan(tmp_path, monkeypatch, NOW)
    runner = Mock(return_value=subprocess.CompletedProcess([], 0, '{}', ''))
    monkeypatch.setattr(schedule.subprocess, 'run', runner)
    monkeypatch.setattr(schedule, '_now', lambda: NOW.replace(minute=29))
    assert schedule.tick(config, workspace, project)['status'] == 'not_due'
    monkeypatch.setattr(schedule, '_now', lambda: NOW.replace(minute=30))
    assert schedule.tick(config, workspace, project)['kind'] == 'business'
    assert schedule.tick(config, workspace, project)['status'] == 'already_claimed'
    runner.assert_called_once()


def test_pause_resume_failure_continues_future_schedule(tmp_path, monkeypatch):
    workspace, project, config, calls = plan(tmp_path, monkeypatch, NOW)
    assert not schedule.pause(workspace)['enabled']
    assert schedule.tick(config, workspace, project)['status'] == 'paused'
    assert schedule.resume(workspace)['enabled']
    schedule.test_after(workspace, 1)
    monkeypatch.setattr(schedule, '_now', lambda: NOW + timedelta(seconds=2))
    monkeypatch.setattr(schedule.subprocess, 'run', Mock(return_value=subprocess.CompletedProcess([], 2, '', '')))
    assert schedule.tick(config, workspace, project)['status'] == 'failed'
    assert schedule._load(workspace)['enabled'] and schedule._load(workspace)['test_due'] is None


def test_overlap_does_not_launch(tmp_path, monkeypatch):
    workspace, project, config, calls = plan(tmp_path, monkeypatch, NOW)
    runner = Mock()
    monkeypatch.setattr(schedule.subprocess, 'run', runner)
    with schedule._lock(workspace) as locked:
        assert locked and schedule.tick(config, workspace, project)['status'] == 'skipped_overlap'
    runner.assert_not_called()


def test_windows_xml_is_unverified(tmp_path, monkeypatch):
    project = tmp_path / 'project'
    project.mkdir()
    (project / 'run_agent.py').write_text('')
    config = project / 'config.json'
    config.write_text('{}')
    monkeypatch.setattr(schedule.platform, 'system', lambda: 'Windows')
    monkeypatch.setattr(schedule, '_now', lambda: NOW)
    commands = []
    monkeypatch.setattr(schedule, '_os_command', lambda args: commands.append(args) or {'returncode': 0, 'stdout': '', 'stderr': ''})
    result = schedule.install(config, tmp_path / 'work', project)
    xml = Path(result['task_path']).read_text(encoding='utf-16')
    assert '<CalendarTrigger>' in xml and '<Interval>PT1M</Interval>' in xml and 'tick' in xml
    assert result['platform_verified'] is False and 'not been verified' in result['limitation']
    assert commands[0][:2] == ['schtasks', '/Create']


def test_interruption_after_claim_does_not_lose_due_test(tmp_path, monkeypatch):
    workspace, project, config, calls = plan(tmp_path, monkeypatch, NOW)
    schedule.test_after(workspace, 1)
    monkeypatch.setattr(schedule, '_now', lambda: NOW + timedelta(seconds=2))
    original_write = schedule._write
    crashed = False
    def fail_claim(path, data):
        nonlocal crashed
        if path.name == 'claim.json' and not crashed:
            crashed = True
            raise SystemExit('injected crash after claim transition')
        return original_write(path, data)
    monkeypatch.setattr(schedule, '_write', fail_claim)
    runner = Mock(return_value=subprocess.CompletedProcess([], 0, '{"run_id":"retried","status":"complete"}', ''))
    monkeypatch.setattr(schedule.subprocess, 'run', runner)
    with pytest.raises(SystemExit):
        schedule.tick(config, workspace, project)
    result = schedule.tick(config, workspace, project)
    assert result['run_id'] == 'retried' and result['status'] == 'complete'
    runner.assert_called_once()


@pytest.mark.parametrize('business_status', ['needs_review', 'incomplete'])
def test_business_outcome_is_distinct_from_execution(tmp_path, monkeypatch, business_status):
    workspace, project, config, calls = plan(tmp_path, monkeypatch, NOW)
    schedule.test_after(workspace, 1)
    monkeypatch.setattr(schedule, '_now', lambda: NOW + timedelta(seconds=2))
    monkeypatch.setattr(schedule.subprocess, 'run', Mock(return_value=subprocess.CompletedProcess(
        [], 2, json.dumps({'run_id': 'review-run', 'status': business_status}), '')))
    result = schedule.tick(config, workspace, project)
    assert result['status'] == 'complete' and result['execution_status'] == 'complete'
    assert result['business_status'] == business_status and result['run_id'] == 'review-run'
    assert result['exit_code'] == 2


def test_pause_during_running_child_preserves_single_execution(tmp_path, monkeypatch):
    workspace, project, config, calls = plan(tmp_path, monkeypatch, NOW)
    schedule.test_after(workspace, 1)
    monkeypatch.setattr(schedule, '_now', lambda: NOW + timedelta(seconds=2))
    def child(*args, **kwargs):
        assert schedule.pause(workspace)['enabled'] is False
        assert schedule.tick(config, workspace, project)['status'] == 'skipped_overlap'
        return subprocess.CompletedProcess([], 0, '{"run_id":"active","status":"complete"}', '')
    monkeypatch.setattr(schedule.subprocess, 'run', child)
    assert schedule.tick(config, workspace, project)['status'] == 'complete'
    assert schedule._load(workspace)['enabled'] is False


def test_crash_after_child_publish_recovers_result_without_rerun(tmp_path, monkeypatch):
    workspace, project, config, calls = plan(tmp_path, monkeypatch, NOW)
    schedule.test_after(workspace, 1)
    monkeypatch.setattr(schedule, '_now', lambda: NOW + timedelta(seconds=2))
    original_write = schedule._write
    crashed = False
    def fail_result(path, data):
        nonlocal crashed
        if path.name == 'result.json' and not crashed:
            crashed = True
            raise SystemExit('injected crash after completed child')
        return original_write(path, data)
    monkeypatch.setattr(schedule, '_write', fail_result)
    def child(*args, **kwargs):
        run_dir = workspace / 'runs' / 'published-run'
        run_dir.mkdir(parents=True)
        summary = {'run_id':'published-run', 'status':'needs_review', 'trigger':'scheduler',
                   'schedule_claim_id': schedule._load(workspace)['pending_claim']['id']}
        summary = write_test_publication(workspace, run_dir, summary)
        return subprocess.CompletedProcess([], 2, json.dumps(summary), '')
    runner = Mock(side_effect=child)
    monkeypatch.setattr(schedule.subprocess, 'run', runner)
    with pytest.raises(SystemExit):
        schedule.tick(config, workspace, project)
    result = schedule.tick(config, workspace, project)
    assert result['status'] == 'complete' and result['run_id'] == 'published-run'
    assert result['business_status'] == 'needs_review' and result['recovered'] is True
    runner.assert_called_once()


def test_result_written_before_plan_update_prevents_duplicate(tmp_path, monkeypatch):
    workspace, project, config, calls = plan(tmp_path, monkeypatch, NOW)
    schedule.test_after(workspace, 1)
    monkeypatch.setattr(schedule, '_now', lambda: NOW + timedelta(seconds=2))
    original_write = schedule._write
    crashed = False
    def fail_final_plan(path, data):
        nonlocal crashed
        if path.name == 'last_execution.json' and not crashed:
            crashed = True
            raise SystemExit('crash after durable result before completed slot')
        return original_write(path, data)
    monkeypatch.setattr(schedule, '_write', fail_final_plan)
    runner = Mock(return_value=subprocess.CompletedProcess([], 0, '{"run_id":"finished","status":"complete"}', ''))
    monkeypatch.setattr(schedule.subprocess, 'run', runner)
    with pytest.raises(SystemExit):
        schedule.tick(config, workspace, project)
    result = schedule.tick(config, workspace, project)
    assert result['run_id'] == 'finished' and result['recovered'] is True
    runner.assert_called_once()
    assert schedule._load(workspace)['test_due'] is None


def test_unfinished_claim_recovers_on_next_day(tmp_path, monkeypatch):
    workspace, project, config, calls = plan(tmp_path, monkeypatch, NOW)
    monkeypatch.setattr(schedule, '_now', lambda: NOW.replace(minute=30))
    runner = Mock(side_effect=[SystemExit('parent terminated'), subprocess.CompletedProcess([], 0, '{"run_id":"next-day","status":"complete"}', '')])
    monkeypatch.setattr(schedule.subprocess, 'run', runner)
    with pytest.raises(SystemExit):
        schedule.tick(config, workspace, project)
    monkeypatch.setattr(schedule, '_now', lambda: NOW + timedelta(days=1))
    result = schedule.tick(config, workspace, project)
    assert result['scheduled_for'] == NOW.replace(minute=30).isoformat()
    assert result['run_id'] == 'next-day' and result['status'] == 'complete'


def test_runner_overlap_is_pending_and_retried(tmp_path, monkeypatch):
    workspace, project, config, calls = plan(tmp_path, monkeypatch, NOW)
    schedule.test_after(workspace, 1)
    monkeypatch.setattr(schedule, '_now', lambda: NOW + timedelta(seconds=2))
    runner = Mock(side_effect=[subprocess.CompletedProcess([], 2, '{"status":"skipped_overlap","run_id":null}', ''),
                               subprocess.CompletedProcess([], 0, '{"status":"complete","run_id":"eventually"}', '')])
    monkeypatch.setattr(schedule.subprocess, 'run', runner)
    first = schedule.tick(config, workspace, project)
    assert first['execution_status'] == 'not_started'
    assert schedule._load(workspace)['test_due'] is not None
    second = schedule.tick(config, workspace, project)
    assert second['run_id'] == 'eventually'
    assert 'pass_fds' in runner.call_args.kwargs


def test_terminal_failure_is_not_reported_as_completed_execution(tmp_path, monkeypatch):
    workspace, project, config, calls = plan(tmp_path, monkeypatch, NOW)
    monkeypatch.setattr(schedule, '_now', lambda: NOW.replace(minute=30))
    runner = Mock(return_value=subprocess.CompletedProcess([], 1, '{"status":"failed","error":"run failed"}', ''))
    monkeypatch.setattr(schedule.subprocess, 'run', runner)
    assert schedule.tick(config, workspace, project)['execution_status'] == 'failed'
    repeat = schedule.tick(config, workspace, project)
    assert repeat['status'] == 'already_claimed' and repeat['execution_status'] == 'failed'
    runner.assert_called_once()


def write_test_publication(workspace, run_dir, summary):
    summary = {**summary, 'output_html': str(run_dir / 'calendar.html')}
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / 'summary.json').write_text(json.dumps(summary))
    (run_dir / 'state.json').write_text(json.dumps({'last_run_id': summary['run_id']}))
    (run_dir / 'calendar.html').write_text('committed calendar')
    artifacts = {name: {'path': str((run_dir / name).relative_to(workspace)),
                        'sha256': hashlib.sha256((run_dir / name).read_bytes()).hexdigest()}
                 for name in ['state.json', 'summary.json', 'calendar.html']}
    (workspace / 'current.json').write_text(json.dumps({'run_id': summary['run_id'], 'artifacts': artifacts}))
    return summary


def publish_for_claim(workspace, summary_claim, archived_claim):
    run_dir = workspace / 'runs' / 'other-scheduled-run'
    run_dir.mkdir(parents=True)
    summary = {'run_id': 'other-scheduled-run', 'status': 'complete', 'trigger': 'scheduler',
               'schedule_claim_id': summary_claim}
    summary = write_test_publication(workspace, run_dir, summary)
    if archived_claim != summary_claim:
        (run_dir / 'summary.json').write_text(json.dumps({**summary, 'schedule_claim_id': archived_claim}))


@pytest.mark.parametrize('summary_claim,archived_claim', [
    (None, None), ('other-claim', 'other-claim'), ('pending-claim', 'other-claim'),
    ('other-claim', 'pending-claim')])
def test_recovery_rejects_run_not_bound_to_pending_claim(tmp_path, summary_claim, archived_claim):
    workspace = tmp_path / 'work'
    publish_for_claim(workspace, summary_claim, archived_claim)
    claim = {'id': 'pending-claim', 'run_ids_before': []}
    assert schedule._published_run(workspace, claim) is None


def test_recovery_accepts_only_matching_current_and_archived_claim(tmp_path):
    workspace = tmp_path / 'work'
    publish_for_claim(workspace, 'pending-claim', 'pending-claim')
    recovered = schedule._published_run(workspace, {'id': 'pending-claim', 'run_ids_before': []})
    assert recovered['run_id'] == 'other-scheduled-run'
    assert recovered['schedule_claim_id'] == 'pending-claim'


def test_tick_passes_exact_claim_id_to_business_child(tmp_path, monkeypatch):
    workspace, project, config, calls = plan(tmp_path, monkeypatch, NOW)
    schedule.test_after(workspace, 1)
    monkeypatch.setattr(schedule, '_now', lambda: NOW + timedelta(seconds=2))
    runner = Mock(return_value=subprocess.CompletedProcess([], 0, '{"status":"complete","run_id":"bound-run"}', ''))
    monkeypatch.setattr(schedule.subprocess, 'run', runner)
    result = schedule.tick(config, workspace, project)
    command = runner.call_args.args[0]
    assert command[command.index('--claim-id') + 1] == f"test:{(NOW + timedelta(seconds=1)).isoformat()}"
    assert result['schedule_claim_id'] == command[command.index('--claim-id') + 1]


def test_recovery_rejects_matching_claim_without_commit_pointer(tmp_path):
    workspace = tmp_path / 'work'
    publish_for_claim(workspace, 'pending-claim', 'pending-claim')
    (workspace / 'current.json').unlink()
    assert schedule._published_run(workspace, {'id': 'pending-claim', 'run_ids_before': []}) is None


def test_failed_child_does_not_claim_an_unrelated_new_run_directory(tmp_path, monkeypatch):
    workspace, project, config, calls = plan(tmp_path, monkeypatch, NOW)
    schedule.test_after(workspace, 1)
    monkeypatch.setattr(schedule, '_now', lambda: NOW + timedelta(seconds=2))
    def child(*args, **kwargs):
        unrelated = workspace / 'runs' / 'unrelated-manual-run'
        unrelated.mkdir(parents=True)
        (unrelated / 'start.json').write_text(json.dumps({'trigger': 'manual', 'schedule_claim_id': None}))
        return subprocess.CompletedProcess([], 1, '{"status":"failed"}', '')
    monkeypatch.setattr(schedule.subprocess, 'run', child)
    result = schedule.tick(config, workspace, project)
    assert result['status'] == 'failed' and result['run_id'] is None
    assert 'run_dir' not in result


def test_daily_schedule_includes_saturday_disclosures(tmp_path,monkeypatch):
    workspace,project,config,calls=plan(tmp_path,monkeypatch,NOW)
    stored=schedule._load(workspace)
    assert stored['weekdays']==list(range(7))
    saturday=NOW+timedelta(days=(5-NOW.weekday())%7)
    monkeypatch.setattr(schedule,'_now',lambda:saturday.replace(hour=8,minute=30))
    runner=Mock(return_value=subprocess.CompletedProcess([],0,'{}',''))
    monkeypatch.setattr(schedule.subprocess,'run',runner)
    assert schedule.tick(config,workspace,project)['kind']=='business'
    runner.assert_called_once()


def test_business_schedule_rejects_invalid_days_and_times():
    for config in [{'schedule_weekdays':[0,0]},{'schedule_weekdays':[True]},{'schedule_weekdays':[]},
                   {'schedule_weekdays':[7]},{'schedule_time':'8:30'},{'schedule_time':'25:00'}]:
        with pytest.raises(ValueError):schedule.business_settings(config)
