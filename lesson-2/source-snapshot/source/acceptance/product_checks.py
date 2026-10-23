"""Black-box product checks mixed into acceptance.checks.Acceptance."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import ExitStack
from copy import deepcopy
import hashlib
from html.parser import HTMLParser
import json
import os
from pathlib import Path
import shutil
import subprocess
import threading
import time
from urllib.error import HTTPError
from urllib.parse import quote, urljoin, urlparse
from urllib.request import Request, urlopen
import zipfile

from .fixtures import (COMPANY, PAGES, VALUES, alternate_reference, income_envelope, joint_statement_case,
                       mixed_reference_envelope, observation, reference,
                       script, selection, write_pdf)
from .services import ScriptedServices, run_with_services, transport_request


STAGES = ['prepare', 'locate', 'extract', 'vision', 'external', 'delivery']
TERMINAL = {'candidate_ready', 'stopped', 'interrupted'}


def _load(path):
    return json.loads(Path(path).read_text())


def _sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _http(base_url, path, method='GET', payload=None, origin=True,
          content_type='application/json'):
    data = None if payload is None else json.dumps(payload, ensure_ascii=False).encode()
    headers = {}
    if data is not None:
        headers['Content-Type'] = content_type
    if origin:
        parsed_base = urlparse(base_url)
        headers['Origin'] = parsed_base.scheme + '://' + parsed_base.netloc
    request = Request(urljoin(base_url + '/', path.lstrip('/')), data=data,
                      headers=headers, method=method)
    try:
        with urlopen(request, timeout=10) as response:
            body = response.read()
            status = response.status
    except HTTPError as error:
        body = error.read()
        status = error.code
    if body:
        try:
            value = json.loads(body.decode())
        except (UnicodeDecodeError, json.JSONDecodeError):
            value = body.decode(errors='replace')
    else:
        value = None
    return status, value


def _wait_for(read, predicate, timeout=25):
    deadline = time.monotonic() + timeout
    last = None
    while time.monotonic() < deadline:
        last = read()
        if predicate(last):
            return last
        time.sleep(0.05)
    raise AssertionError(f'timed out waiting for product state; last={last!r}')


def _prepare_scenario(folder, kind='freeze'):
    folder.mkdir(parents=True, exist_ok=True)
    scenario = script(kind)
    pdf = folder / 'synthetic.pdf'
    write_pdf(pdf)
    scenario['pdf_path'] = str(pdf)
    return scenario, pdf


def _serve(subject, scenario, output_root, services):
    services.task_root = Path(output_root) / 'tasks'
    return subject.serve(transport_request(scenario, services), output_root)


def _catalog_entry(base_url):
    status, catalog = _http(base_url, '/api/catalog', origin=False)
    if status != 200:
        raise AssertionError((status, catalog))
    entries = catalog.get('entries') if isinstance(catalog, dict) else None
    if not isinstance(entries, list) or len(entries) != 1:
        raise AssertionError(f'expected one synthetic catalog entry: {catalog!r}')
    entry = entries[0]
    if not isinstance(entry.get('id'), str) or not isinstance(entry.get('pdf_sha256'), str):
        raise AssertionError(f'catalog entry lacks stable identity/hash: {entry!r}')
    return entry


def _create_payload(entry, key):
    return {'report_id': entry['id'], 'preset_id': 'qwen27',
            'idempotency_key': key,
            'expected_source_sha256': entry['pdf_sha256']}


class _AssetReferences(HTMLParser):
    def __init__(self):
        super().__init__()
        self.references = []
        self.ids = set()

    def handle_starttag(self, tag, attrs):
        values = dict(attrs)
        if values.get('id'):
            self.ids.add(values['id'])
        if tag == 'script' and values.get('src'):
            self.references.append(values['src'])
        if tag == 'link' and values.get('href'):
            self.references.append(values['href'])


class ProductChecks:
    """Requires subject, project and output properties from the host TestCase."""

    def assert_journal(self, result, require_all=False, receipts=None):
        events = _load(result['journal_file'])['events']
        self.assertTrue(events, 'real phase work must have a durable journal')
        sequences = [event['sequence'] for event in events]
        self.assertEqual(sequences, sorted(set(sequences)))
        opened, entered = {}, set()
        for event in events:
            stage = event['stage']
            self.assertIn(stage, STAGES)
            self.assertIsInstance(event['at'], (int, float))
            if event['kind'] == 'start':
                self.assertNotIn(stage, opened, event)
                opened[stage] = event['at']
                entered.add(stage)
            else:
                self.assertEqual(event['kind'], 'end')
                self.assertIn(stage, opened, event)
                self.assertGreaterEqual(event['at'], opened.pop(stage))
                self.assertTrue(event.get('outcome'), event)
        self.assertEqual(opened, {}, 'terminal tasks must close every entered phase')
        if require_all:
            self.assertEqual(entered, set(STAGES))
        if receipts:
            for receipt in receipts['model_receipts'] + receipts['reference_receipts']:
                stage = receipt.get('expected_stage', 'external')
                before = receipt['projection']['journal']['events']
                starts = sum(e['stage'] == stage and e['kind'] == 'start' for e in before)
                ends = sum(e['stage'] == stage and e['kind'] == 'end' for e in before)
                self.assertEqual(starts - ends, 1, f'{stage} start must precede every actual request')
            if receipts['model_receipts']:
                before = receipts['model_receipts'][0]['projection']['journal']['events']
                self.assertTrue(any(e['stage'] == 'prepare' and e['kind'] == 'end' for e in before))
                self.assertTrue(any(e['stage'] == 'locate' and e['kind'] == 'start' for e in before))
                self.assertFalse(any(e['stage'] == 'locate' and e['kind'] == 'end' for e in before))
            if receipts['reference_receipts']:
                before = receipts['reference_receipts'][0]['projection']['journal']['events']
                external = [e for e in before if e['stage'] == 'external']
                self.assertTrue(external)
                self.assertEqual(external[-1]['kind'], 'start', 'persist before reference work')

    def test_02_static_product_assets(self):
        web = self.project / 'web'
        index = web / 'index.html'
        css = web / 'style.css'
        javascript = web / 'app.js'
        for path in (index, css, javascript):
            self.assertTrue(path.is_file(), path)
        parser = _AssetReferences()
        parser.feed(index.read_text())
        self.assertTrue(parser.references, 'index.html must reference its real static assets')
        for reference_path in parser.references:
            parsed = urlparse(reference_path)
            self.assertFalse(parsed.scheme or parsed.netloc, reference_path)
            resolved = (web / parsed.path.lstrip('/')).resolve()
            self.assertTrue(resolved.is_relative_to(web.resolve()), reference_path)
            self.assertTrue(resolved.is_file(), reference_path)
        source = javascript.read_text()
        import re
        literal_ids = set(re.findall(r"getElementById\(\s*['\"]([^'\"]+)['\"]\s*\)", source))
        helpers = re.findall(r'function\s+([\w$]+)\s*\(\s*([\w$]+)\s*\)\s*\{\s*return\s+document\.getElementById\(\s*\2\s*\)\s*;?\s*\}', source)
        for helper, _ in helpers:
            literal_ids.update(re.findall(r'(?<![\w$])' + re.escape(helper) + r"\(\s*['\"]([^'\"]+)['\"]\s*\)", source))
        self.assertFalse(literal_ids - parser.ids, f'missing DOM IDs: {literal_ids - parser.ids}')
        for route in ('/api/catalog', '/api/tasks', '/api/history'):
            self.assertIn(route, source)
        styles = css.read_text().replace(' ', '').lower()
        self.assertIn('min-width:0', styles)
        self.assertTrue('overflow-wrap:' in styles or 'word-break:' in styles,
                        'long local evidence paths need an explicit wrap rule')
        node = shutil.which('node')
        self.assertIsNotNone(node, 'Node.js is required for the existing hithink CLI environment')
        checked = subprocess.run([node, '--check', str(javascript)],
                                 capture_output=True, text=True)
        self.assertEqual(checked.returncode, 0, checked.stderr)

    def test_05_joint_scope_columns(self):
        for title in ('合并及公司利润表', '合并及母公司利润表', '合并和公司利润表', '合并和母公司利润表'):
            with self.subTest(title=title):
                pages, value = joint_statement_case(title, 'consolidated')
                self.assertTrue(self.subject.validate(
                    value, pages, [1], expected_company=COMPANY)['passed'])
        for title, columns in (('合并及公司利润表', 'ambiguous'),
                               ('合并及母公司利润表', 'company'),
                               ('公司利润表', 'company'),
                               ('母公司利润表', 'company')):
            with self.subTest(title=title, columns=columns):
                pages, value = joint_statement_case(title, columns)
                result = self.subject.validate(value, pages, [1], expected_company=COMPANY)
                self.assertFalse(result['passed'], result)

    def test_06_mixed_reference_window(self):
        envelope = mixed_reference_envelope()

        def compare(value):
            return self.subject.compare(observation(), observation(), value, PAGES,
                                        expected_thscode='000001.SZ',
                                        expected_company=COMPANY)

        positive = compare(envelope)
        self.assertTrue(positive['external']['passed'], positive)
        self.assertEqual(positive['external']['matched'], 10)
        self.assertEqual(positive['external']['total'], 10)
        items = envelope['data']['item']
        targets = [item for item in items if item['fiscal_period'] == 'Q2'
                   and item['fiscal_year'] in (2026, 2025)]
        self.assertEqual(len(targets), 2)

        missing = deepcopy(envelope)
        missing['data']['item'] = [item for item in missing['data']['item']
                                   if not (item['fiscal_year'] == 2025
                                           and item['fiscal_period'] == 'Q2')]
        duplicate = deepcopy(envelope)
        duplicate['data']['item'].append(deepcopy(targets[0]))
        bads = [('missing target', missing), ('duplicate target', duplicate)]
        for field, value in (('thscode', '999999.SH'), ('currency', 'USD'),
                             ('period', 'annual'), ('period_end_ms', 0)):
            bad = deepcopy(envelope)
            target = next(item for item in bad['data']['item']
                          if item['fiscal_year'] == 2026 and item['fiscal_period'] == 'Q2')
            target[field] = value
            bads.append((field, bad))
        for label, bad in bads:
            with self.subTest(reference=label):
                self.assertFalse(compare(bad)['external']['passed'])

    def test_07_lifetime_pass_survives_candidate_change(self):
        events = [
            {'event': 'gate', 'gate': 'source', 'rules': [], 'candidate': 'a'},
            {'event': 'gate', 'gate': 'internal', 'rules': [], 'candidate': 'a'},
            {'event': 'candidate_changed', 'candidate': 'b'},
            {'event': 'gate', 'gate': 'source', 'rules': [], 'candidate': 'b'},
            {'event': 'gate', 'gate': 'internal',
             'rules': ['value:basic_eps:current', 'value:revenue:current'], 'candidate': 'b'},
            {'event': 'gate', 'gate': 'internal',
             'rules': ['value:basic_eps:current'], 'candidate': 'b'},
        ]
        result = self.subject.progress(events)
        final = result['snapshots'][-1]
        self.assertTrue(result['stopped'], result)
        self.assertTrue(final['ever_passed']['source'])
        self.assertTrue(final['ever_passed']['internal'])
        self.assertEqual(final['no_progress'], 2)
        self.assertEqual(result['counters']['failed_gate_evaluations'], 2)
        self.assertEqual(result['counters']['feedback_emitted'], 1)

    def test_07_raw_json_text_and_vision(self):
        for language in ('json', ''):
            folder = self.output / ('raw-json-positive-' + (language or 'unlabelled'))
            scenario, _ = _prepare_scenario(folder)
            for item in scenario['model_script']:
                encoded = json.dumps(item['response'], ensure_ascii=False)
                item['raw_content'] = f'```{language}\n{encoded}\n```'
            result, receipts = run_with_services(self.subject, scenario, folder / 'run')
            state = _load(result['state_file'])
            self.assertEqual(state['status'], 'candidate_ready', state)
            self.assert_journal(result, require_all=True, receipts=receipts)

        invalid_cases = [
            ('text-prose', 'locate', 'before\n```json\n{"action":"search_fulltext","query":"合并利润表","offset":0}\n```'),
            ('text-multiple', 'locate', '{"action":"search_fulltext","query":"合并利润表","offset":0}\n{"action":"read_pages","pages":[1]}'),
            ('vision-wrong-type', 'vision', '```json\n[]\n```'),
            ('vision-truncated', 'vision', '```json\n{"company":"broken"\n```'),
        ]
        for label, stage, raw in invalid_cases:
            with self.subTest(raw=label):
                case = self.output / ('raw-json-' + label)
                scenario, _ = _prepare_scenario(case)
                if stage == 'locate':
                    prefix = []
                else:
                    prefix = scenario['model_script'][:4]
                invalid = [{'stage': stage, 'response': {}, 'raw_content': raw,
                            'id': f'{label}-{i}',
                            'usage': {'prompt_tokens': 100, 'completion_tokens': 10,
                                      'total_tokens': 110}}
                           for i in range(8)]
                scenario['model_script'] = prefix + invalid
                scenario['reference_script'] = []
                rejected, receipts = run_with_services(
                    self.subject, scenario, case / 'run')
                rejected_state = _load(rejected['state_file'])
                self.assertEqual(rejected_state['status'], 'stopped', rejected_state)
                self.assertFalse(rejected_state.get('review'))
                self.assertEqual(len(receipts['model_receipts']), len(prefix) + 2)
                self.assertEqual(receipts['reference_receipts'], [])
                self.assertEqual(rejected_state['counters']['failed_gate_evaluations'], 0)
                self.assert_journal(rejected, receipts=receipts)
                if stage == 'locate':
                    self.assertEqual(_load(rejected['trace_file']).get('candidates', []), [])
                else:
                    self.assertFalse(rejected_state['current']['internal']['passed'])

    def test_07_candidate_journal_and_unique_archive_members(self):
        folder = self.output / 'candidate-seal'
        scenario, _ = _prepare_scenario(folder)
        invalid = observation()
        invalid['rows'][-1]['unit_quote'] = '没有这段单位'
        prefix = scenario['model_script'][:3]
        tail = [
            {'stage': 'extract', 'response': {'action': 'submit', 'observation': invalid}},
            {'stage': 'extract', 'response': {'action': 'submit', 'observation': observation()}},
            {'stage': 'vision', 'response': observation()},
        ]
        for number, item in enumerate(tail, len(prefix) + 1):
            item.update(id=f'candidate-{number}',
                        usage={'prompt_tokens': 100, 'completion_tokens': 10,
                               'total_tokens': 110})
        scenario['model_script'] = prefix + tail
        scenario['reference_script'] = [reference()]
        result, _ = run_with_services(self.subject, scenario, folder / 'run')
        state = _load(result['state_file'])
        self.assertEqual(state['status'], 'candidate_ready', state)
        candidates = _load(result['trace_file'])['candidates']
        self.assertEqual(len(candidates), 2)
        self.assertEqual([item['sequence'] for item in candidates], [1, 2])
        self.assertEqual(len({item['candidate_id'] for item in candidates}), 2)
        self.assertEqual(len({item['path'] for item in candidates}), 2)
        for item, expected in zip(candidates, (invalid, observation())):
            self.assertEqual(_load(item['path']), expected)
            self.assertEqual(_sha(item['path']), item['sha256'])
        with zipfile.ZipFile(result['sealed_archive']) as archive:
            names = archive.namelist()
            self.assertEqual(len(names), len(set(names)), 'ZIP members must be unique')
            embedded = {hashlib.sha256(archive.read(name)).hexdigest()
                        for name in names if not name.endswith('/')}
        for item in candidates:
            self.assertIn(item['sha256'], embedded)

    def test_05_failed_selection_does_not_advance(self):
        folder = self.output / 'failed-selection-stage'
        scenario, _ = _prepare_scenario(folder)
        bad = selection()
        bad['anchors'][0]['quote'] = 'NOT_PRINTED_ON_PAGE'
        scenario['model_script'] = [
            {'stage': 'locate',
             'response': {'action': 'select_pages', 'selection': bad},
             'id': f'bad-selection-{i}',
             'usage': {'prompt_tokens': 100, 'completion_tokens': 10,
                       'total_tokens': 110}}
            for i in range(6)]
        scenario['reference_script'] = []
        result, _ = run_with_services(self.subject, scenario, folder / 'run')
        state = _load(result['state_file'])
        trace = _load(result['trace_file'])
        journal = _load(result['journal_file'])
        self.assertEqual(state['status'], 'stopped', state)
        self.assertTrue(trace['requests'])
        self.assertEqual({request['stage'] for request in trace['requests']}, {'locate'})
        self.assertEqual(trace.get('candidates', []), [])
        self.assertFalse(any(event['stage'] == 'extract' and event['kind'] == 'start'
                             for event in journal['events']))

    def test_07_http_idempotency_and_active_lock(self):
        for mode in ('same-key', 'different-keys'):
            with self.subTest(mode=mode):
                folder = self.output / ('http-' + mode)
                scenario, _ = _prepare_scenario(folder)
                scenario['model_script'][0]['delay_seconds'] = 1.0
                with ScriptedServices(scenario) as services:
                    with ExitStack() as contexts:
                        products = [contexts.enter_context(_serve(
                            self.subject, scenario, folder / 'run', services)) for _ in range(2)]
                        bases = [product['base_url'] for product in products]
                        self.assertNotEqual(bases[0], bases[1], 'use two real server instances')
                        entries = [_catalog_entry(base) for base in bases]
                        barrier = threading.Barrier(2)

                        def post(item):
                            base, entry, key = item
                            barrier.wait()
                            return _http(base, '/api/tasks', 'POST',
                                         _create_payload(entry, key))

                        keys = ('same', 'same') if mode == 'same-key' else ('a', 'b')
                        with ThreadPoolExecutor(max_workers=2) as pool:
                            responses = list(pool.map(post, zip(bases, entries, keys)))
                        if mode == 'same-key':
                            self.assertEqual([status for status, _ in responses], [202, 202])
                            ids = {body['task_id'] for _, body in responses}
                            self.assertEqual(len(ids), 1)
                            task_id = ids.pop()
                        else:
                            self.assertEqual(sorted(status for status, _ in responses), [202, 409])
                            accepted = next(body for status, body in responses if status == 202)
                            refused = next(body for status, body in responses if status == 409)
                            self.assertEqual(refused['error'], 'active_task_exists')
                            task_id = accepted['task_id']
                        task_dir = folder / 'run' / 'tasks' / task_id
                        self.assertTrue(task_dir.is_dir(), task_dir)
                        terminal = _wait_for(lambda: _http(bases[0], f'/api/tasks/{quote(task_id)}',
                                                          origin=False)[1],
                                             lambda state: state.get('status') in TERMINAL)
                        self.assertEqual(terminal['status'], 'candidate_ready', terminal)
                        self.assertEqual([path.name for path in (folder / 'run' / 'tasks').iterdir()
                                          if path.is_dir() and not path.name.startswith('.')], [task_id])
                        execution = _load(task_dir / 'execution.json')
                        self.assertIsInstance(execution['pid'], int)
                        self.assertNotEqual(execution['pid'], os.getpid())
                        program = (task_dir / 'program').resolve()
                        self.assertTrue(Path(execution['entrypoint']).resolve().is_relative_to(program))
                        app_modules = {k: v for k, v in execution['loaded_modules'].items()
                                       if k == 'app' or k.startswith('app.')}
                        self.assertTrue(app_modules)
                        self.assertTrue(all(Path(path).resolve().is_relative_to(program)
                                            for path in app_modules.values()))
                        self.assertEqual(len(services.model_receipts), 5)
                self.assertFalse(services.errors, services.errors)

    def test_03_catalog_hash_drift_rejected(self):
        folder = self.output / 'http-source-drift'
        scenario, pdf = _prepare_scenario(folder)
        scenario['model_script'][0]['delay_seconds'] = 1.0
        with ScriptedServices(scenario) as services:
            with _serve(self.subject, scenario, folder / 'run', services) as product:
                base = product['base_url']
                entry = _catalog_entry(base)
                with pdf.open('ab') as handle:
                    handle.write(b'\n% acceptance source drift\n')
                status, body = _http(base, '/api/tasks', 'POST',
                                     _create_payload(entry, 'drift'))
                self.assertEqual(status, 409, body)
                self.assertEqual(body['error'], 'source_changed')
                self.assertEqual(services.model_receipts, [])
                task_root = folder / 'run' / 'tasks'
                self.assertEqual([path for path in task_root.iterdir() if path.is_dir()]
                                 if task_root.exists() else [], [])

    def test_03_copied_pdf_hash_is_checked(self):
        folder = self.output / 'copied-source-drift'
        scenario, pdf = _prepare_scenario(folder)
        scenario['expected_source_sha256'] = _sha(pdf)

        def corrupt(task_dir):
            copies = [path for path in Path(task_dir).rglob('*.pdf')
                      if 'program' not in path.relative_to(task_dir).parts]
            self.assertEqual(len(copies), 1, copies)
            with copies[0].open('ab') as handle:
                handle.write(b'\n% acceptance copied source drift\n')

        result, receipts = run_with_services(self.subject, scenario, folder / 'run', corrupt)
        state = _load(result['state_file'])
        self.assertEqual(state['status'], 'stopped', state)
        self.assertFalse(state.get('review'))
        self.assertEqual(receipts['model_receipts'], [])
        self.assertEqual(receipts['reference_receipts'], [])

    def test_07_mixed_reference_and_immutable_evaluations(self):
        folder = self.output / 'mixed-reference-retention'
        scenario, _ = _prepare_scenario(folder, 'external_revision')
        envelope = mixed_reference_envelope()
        targets = {item['fiscal_year']: item for item in
                   income_envelope(alternate_reference())['data']['item']}
        envelope['data']['item'] = [deepcopy(targets[item['fiscal_year']])
            if item['fiscal_period'] == 'Q2' and item['fiscal_year'] in targets else item
            for item in envelope['data']['item']]
        first, second = deepcopy(envelope), deepcopy(envelope)
        second['meta']['requestId'] = 'synthetic-reference-next-version'
        second['data']['timestamp'] += 1000
        scenario['reference_script'] = [first, second]
        result, receipts = run_with_services(self.subject, scenario, folder / 'run')
        state = _load(result['state_file'])
        self.assertEqual(state['status'], 'candidate_ready', state)
        evaluations = _load(result['trace_file'])['external_evaluations']
        self.assertEqual(len(evaluations), 2)
        self.assertEqual([event['matched'] for event in evaluations], [8, 10])
        returned = [receipt['response'] for receipt in receipts['reference_receipts']]
        self.assertIn(len(returned), (1, 2), 'cache or version the frozen private reference')
        observed = next(receipt['projection'] for receipt in receipts['model_receipts']
                        if receipt['projection'].get('trace', {}).get('external_evaluations'))
        first_evaluation = observed['trace']['external_evaluations'][0]
        for field in ('sequence', 'candidate_id', 'candidate_sha256', 'reference_path',
                      'reference_sha256', 'passed', 'matched', 'total', 'comparisons'):
            self.assertEqual(evaluations[0][field], first_evaluation[field],
                             'earlier comparison must remain immutable after the next response')
        first_version = next(item for item in observed['reference_versions']
                             if item['path'] == first_evaluation['reference_path'])
        self.assertEqual(first_version['content'], first)
        self.assertEqual(first_version['sha256'], evaluations[0]['reference_sha256'])
        for event in evaluations:
            self.assertIn(_load(event['reference_path']), returned)
            self.assertEqual(_sha(event['reference_path']), event['reference_sha256'])
        with zipfile.ZipFile(result['sealed_archive']) as archive:
            embedded = {hashlib.sha256(archive.read(name)).hexdigest()
                        for name in archive.namelist() if not name.endswith('/')}
        for event in evaluations:
            self.assertIn(event['reference_sha256'], embedded)
        self.assert_journal(result, require_all=True, receipts=receipts)

    def test_07_live_projection_history_review_and_evidence(self):
        folder = self.output / 'http-live'
        scenario, _ = _prepare_scenario(folder)
        scenario['model_script'][1]['delay_seconds'] = 1.5
        run_root = folder / 'run'
        with ScriptedServices(scenario) as services:
            with _serve(self.subject, scenario, run_root, services) as product:
                base = product['base_url']
                entry = _catalog_entry(base)
                before = len(services.model_receipts)
                status, denied = _http(base, '/api/tasks', 'POST',
                                       _create_payload(entry, 'no-origin'), origin=False)
                self.assertIn(status, (400, 403), denied)
                self.assertEqual(len(services.model_receipts), before)
                status, denied = _http(base, '/api/tasks', 'POST',
                                       _create_payload(entry, 'wrong-content-type'),
                                       content_type='text/plain')
                self.assertIn(status, (400, 415), denied)
                self.assertEqual(len(services.model_receipts), before)
                status, created = _http(base, '/api/tasks', 'POST',
                                        _create_payload(entry, 'live'))
                self.assertEqual(status, 202, created)
                task_id = created['task_id']

                def read_state():
                    code, value = _http(base, f'/api/tasks/{quote(task_id)}', origin=False)
                    self.assertEqual(code, 200, value)
                    return value

                live = _wait_for(read_state,
                                 lambda value: value.get('usage', {}).get('total_tokens') == 110
                                 and value.get('usage', {}).get('pending', 0) >= 1)
                self.assertEqual(live['task_id'], task_id)
                self.assertEqual([stage['name'] for stage in live['stages']], STAGES)
                locate = next(stage for stage in live['stages'] if stage['name'] == 'locate')
                self.assertEqual(locate['model_tokens'], 110)
                self.assertGreaterEqual(locate['pending'], 1)
                self.assertGreaterEqual(locate['requests'], 2)
                self.assertIn('internal', live['current'])
                self.assertIn('external', live['current'])
                calls_during_live = len(services.model_receipts)
                read_state()
                self.assertEqual(len(services.model_receipts), calls_during_live,
                                 'refresh must remain read-only')

                terminal = _wait_for(read_state,
                                     lambda value: value.get('status') in TERMINAL)
                self.assertEqual(terminal['status'], 'candidate_ready', terminal)
                self.assertEqual(terminal['usage']['pending'], 0)
                self.assertEqual(terminal['usage']['unknown'], 0)
                self.assertEqual(sum(stage['model_tokens'] for stage in terminal['stages']),
                                 terminal['usage']['total_tokens'])
                for stage in terminal['stages']:
                    for field in ('status', 'model', 'requests', 'model_tokens',
                                  'pending', 'unknown', 'elapsed_seconds'):
                        self.assertIn(field, stage)
                    self.assertEqual(stage['status'], 'done', stage)
                    if stage['name'] in ('prepare', 'external', 'delivery'):
                        self.assertEqual(stage['requests'], 0, stage)
                        self.assertEqual(stage['model_tokens'], 0, stage)
                elapsed = [stage['elapsed_seconds'] for stage in terminal['stages']]
                time.sleep(0.2)
                self.assertEqual(elapsed,
                                 [stage['elapsed_seconds'] for stage in read_state()['stages']],
                                 'terminal elapsed time must not keep growing')

                metrics = terminal['review']['metrics']
                self.assertEqual(len(metrics), 5)
                expected_display = [('0.01', '0.01'), ('0.01', '0.01'),
                                    ('0.00', '0.00'), ('0.00', '0.00'), ('0.83', '0.75')]
                for metric, raw_values, display in zip(metrics, VALUES, expected_display):
                    for field in ('metric', 'current', 'prior', 'unit', 'display_unit',
                                  'source_unit', 'current_raw', 'prior_raw'):
                        self.assertIn(field, metric)
                    self.assertEqual((metric['current_raw'], metric['prior_raw']), raw_values)
                    self.assertEqual((metric['current'], metric['prior']), display)
                    if metric['metric'] == 'basic_eps':
                        self.assertEqual(metric['unit'], '元/股')
                        self.assertEqual(metric['display_unit'], '元/股')
                        self.assertEqual(metric['source_unit'], '元/股')
                    else:
                        self.assertEqual(metric['unit'], '亿元')
                        self.assertEqual(metric['display_unit'], '亿元')
                        self.assertEqual(metric['source_unit'], '万元')
                        self.assertRegex(str(metric['current']), r'^-?\d+\.\d{2}$')
                        self.assertRegex(str(metric['prior']), r'^-?\d+\.\d{2}$')

                evidence = terminal['evidence']
                self.assertTrue(evidence)
                for name, value in evidence.items():
                    self.assertIsInstance(value, str, (name, value))
                    target = urljoin(base + '/', value)
                    parsed = urlparse(target)
                    self.assertEqual((parsed.scheme, parsed.netloc),
                                     urlparse(base)[:2], (name, value))
                    self.assertNotIn('..', parsed.path)
                    self.assertNotIn('file:', value)
                first = urljoin(base + '/', next(iter(evidence.values())))
                with urlopen(first, timeout=10) as response:
                    self.assertEqual(response.status, 200)
                    self.assertTrue(response.read(1))
                traversal, _ = _http(
                    base,
                    f'/api/tasks/{quote(task_id)}/evidence/%2e%2e%2fstate.json',
                    origin=False)
                self.assertIn(traversal, (400, 403, 404))

                self.assert_journal({'journal_file': run_root / 'tasks' / task_id / 'stage-journal.json'},
                                    require_all=True, receipts={
                                        'model_receipts': services.model_receipts,
                                        'reference_receipts': services.reference_receipts})
        self.assertFalse(services.errors, services.errors)

        restart = deepcopy(scenario)
        for item in restart['model_script']:
            item.pop('delay_seconds', None)
        with ScriptedServices(restart) as services2:
            with _serve(self.subject, restart, run_root, services2) as product:
                base = product['base_url']
                status, history = _http(base, '/api/history', origin=False)
                self.assertEqual(status, 200, history)
                self.assertIn(task_id, {item['task_id'] for item in history['tasks']})
                status, restored = _http(base, f'/api/tasks/{quote(task_id)}', origin=False)
                self.assertEqual(status, 200, restored)
                self.assertEqual(restored['status'], 'candidate_ready')
                self.assertEqual(restored['task_id'], task_id)
                self.assertEqual(services2.model_receipts, [])
                self.assertEqual(services2.reference_receipts, [])
