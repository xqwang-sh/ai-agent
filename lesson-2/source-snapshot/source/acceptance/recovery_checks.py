"""Execute the learner's production task-view controller, without a DOM emulator."""
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
from urllib.parse import quote

from .product_checks import (_catalog_entry, _create_payload, _http,
                             _prepare_scenario, _serve, _wait_for, TERMINAL)
from .services import ScriptedServices

STORAGE_KEY = 'earnings-review.task-view.v1'

_NODE_COMMON = r'''
import assert from 'node:assert/strict';
import fs from 'node:fs';
import {pathToFileURL} from 'node:url';
const {createTaskView} = await import(pathToFileURL(process.argv[1]).href);
assert.equal(typeof createTaskView, 'function');
const KEY = 'earnings-review.task-view.v1';
const copy = value => JSON.parse(JSON.stringify(value));
function memory(hint = null) {
  const values = new Map(hint ? [[KEY, JSON.stringify(hint)]] : []);
  return {
    getItem: key => values.has(key) ? values.get(key) : null,
    setItem: (key, value) => values.set(key, String(value)),
    removeItem: key => values.delete(key),
    values,
  };
}
function harness(getJSON, storage = memory()) {
  const views = [];
  const controller = createTaskView({getJSON, storage, present: view => {
    assert.ok(view && typeof view === 'object');
    assert.ok(['loading', 'active', 'last', 'history', 'empty', 'error'].includes(view.mode));
    assert.ok(Number.isInteger(view.generation) && view.generation >= 0);
    assert.ok('selected' in view && 'task' in view && typeof view.message === 'string');
    views.push(copy(view));
  }});
  for (const name of ['restore', 'select', 'refresh']) assert.equal(typeof controller[name], 'function');
  return {controller, views, storage, last: () => views.at(-1)};
}
function hint(entry, taskId) {
  return {report_id: entry.id, source_sha256: entry.pdf_sha256, task_id: taskId};
}
function isTask(h, entry, task, mode) {
  const view = h.last();
  assert.equal(view.selected?.id, entry.id);
  assert.equal(view.selected?.pdf_sha256, entry.pdf_sha256);
  assert.equal(view.task?.task_id, task.task_id);
  assert.equal(view.task?.report_id, entry.id);
  assert.equal(view.task?.source_sha256, entry.pdf_sha256);
  assert.equal(view.task?.preset_id, task.preset_id);
  if (mode) assert.equal(view.mode, mode);
  return view;
}
function checkStorage(storage) {
  for (const [key, value] of storage.values) {
    assert.equal(key, KEY, 'one documented selection-hint key');
    const saved = JSON.parse(value);
    for (const field of Object.keys(saved))
      assert.ok(['report_id', 'source_sha256', 'task_id'].includes(field), 'storage must not copy task state');
  }
}
'''

_NODE_UNIT = _NODE_COMMON + r'''
const A = {id: 'report-a', pdf_sha256: 'a'.repeat(64), company: 'Same label', filename: 'same.pdf'};
const B = {id: 'report-b', pdf_sha256: 'b'.repeat(64), company: 'Same label', filename: 'same.pdf'};
const active = {task_id: 'task-a', report_id: A.id, source_sha256: A.pdf_sha256,
  preset_id: 'qwen9', status: 'running', created_at: 2, updated_at: 9,
  company: A.company, filename: A.filename, current_stage: 'extract',
  stages: [], usage: {requests: 2, total_tokens: 110, pending: 1, unknown: 0},
  current: {}, review: null, evidence: {}};
const ended = {...active, task_id: 'task-b', report_id: B.id, source_sha256: B.pdf_sha256,
  status: 'stopped', created_at: 3, updated_at: 10};
const calls = [];
function fixture(tasks = [active], entries = [A, B], taskOverride = {}) {
  return async (url, options = {}) => {
    assert.equal((options.method || 'GET').toUpperCase(), 'GET');
    const path = new URL(url, 'http://127.0.0.1').pathname;
    calls.push(path);
    if (path === '/api/catalog') return copy({entries});
    if (path === '/api/history') return copy({tasks});
    const task = tasks.find(item => path === '/api/tasks/' + item.task_id);
    assert.ok(task, 'unexpected recovery request: ' + path);
    return copy(taskOverride[task.task_id] || task);
  };
}
let h = harness(fixture(), memory(hint(A, active.task_id)));
await h.controller.restore();
isTask(h, A, active, 'active');
assert.equal(h.views[0].mode, 'loading');
checkStorage(h.storage);
// A newly constructed production controller is a reload, not a copied JS state.
h = harness(fixture(), h.storage);
await h.controller.restore();
isTask(h, A, active, 'active');
await h.controller.select(B.id);
assert.equal(h.last().selected?.id, B.id);
assert.equal(h.last().task, null, 'same company/filename does not bind A to B');
await h.controller.select(A.id);
isTask(h, A, active, 'active');
await h.controller.refresh();
isTask(h, A, active, 'active');

h = harness(fixture());
await h.controller.restore();
isTask(h, A, active, 'active');
h = harness(fixture([]));
await h.controller.restore();
assert.equal(h.last().selected, null);
assert.equal(h.last().task, null);

h = harness(fixture(), memory(hint(A, 'missing-task')));
await h.controller.restore();
isTask(h, A, active, 'active');
const staleA = {...A, pdf_sha256: 'c'.repeat(64)};
h = harness(fixture([active], [staleA, B]), memory(hint(A, active.task_id)));
await h.controller.restore();
assert.equal(h.last().task, null, 'changed PDF cannot recover old task');
h = harness(fixture([active], [B]), memory(hint(A, active.task_id)));
await h.controller.restore();
assert.equal(h.last().task, null, 'removed report cannot recover by label');

const terminal = {...active, status: 'candidate_ready', review: {metrics: [{metric: 'synthetic'}]}};
h = harness(fixture([terminal]), memory(hint(A, terminal.task_id)));
await h.controller.restore();
isTask(h, A, terminal, 'last');
assert.notEqual(h.last().mode, 'active');
// A normal POST outside this read-only controller has now created a newer run.
// Re-selecting the same report must not keep a remembered terminal task pinned.
let serverTasks = [terminal];
h = harness((url, options) => fixture(serverTasks)(url, options),
            memory(hint(A, terminal.task_id)));
await h.controller.restore();
isTask(h, A, terminal, 'last');
const nextActive = {...active, task_id: 'task-next', created_at: 4, updated_at: 12};
serverTasks = [terminal, nextActive];
await h.controller.select(A.id);
isTask(h, A, nextActive, 'active');
await h.controller.refresh();
isTask(h, A, nextActive, 'active');
// The task GET must agree with history's immutable identity and frozen preset.
for (const changed of [{report_id: B.id}, {source_sha256: B.pdf_sha256},
                       {preset_id: 'qwen27'}, {task_id: 'other-task'}]) {
  h = harness(fixture([active], [A, B], {[active.task_id]: {...active, ...changed}}),
              memory(hint(A, active.task_id)));
  await h.controller.restore();
  assert.equal(h.last().task, null, 'inconsistent task GET must not attach');
}
h = harness(async (url, options) => {
  if (new URL(url, 'http://127.0.0.1').pathname === '/api/history') throw new Error('history unavailable');
  return fixture()(url, options);
}, memory(hint(A, active.task_id)));
await h.controller.restore();
assert.equal(h.last().mode, 'error', 'history failure is not an empty successful result');
assert.equal(h.last().task, null);

// Hold A's actual task response until B has become the selected view.
let releaseA, reachedA;
const held = new Promise(resolve => { releaseA = resolve; });
const reached = new Promise(resolve => { reachedA = resolve; });
const normal = fixture([active, ended]);
h = harness(async (url, options) => {
  if (new URL(url, 'http://127.0.0.1').pathname === '/api/tasks/task-a') {
    reachedA(); await held;
  }
  return normal(url, options);
});
const old = h.controller.select(A.id);
await Promise.race([reached, new Promise((_, reject) => setTimeout(() => reject(new Error('A task GET not reached')), 1500))]);
await h.controller.select(B.id);
isTask(h, B, ended, 'last');
const generation = h.last().generation;
const published = h.views.length;
releaseA();
await old;
isTask(h, B, ended, 'last');
assert.equal(h.last().generation, generation, 'late A cannot publish a new view');
assert.ok(h.views.slice(published).every(view => view.selected?.id === B.id), 'late A must never render');
checkStorage(h.storage);
assert.ok(calls.length > 10, 'exercise real production recovery, not a static asset check');
console.log(JSON.stringify({ok: true, cases: 'reload/select/identity/preset/error/terminal/new-active/race', requests: calls.length}));
'''

_NODE_HTTP = _NODE_COMMON + r'''
const input = JSON.parse(fs.readFileSync(0, 'utf8'));
const base = new URL(input.base_url);
assert.equal(base.hostname, '127.0.0.1');
const calls = [];
async function getJSON(path, options = {}) {
  assert.equal((options.method || 'GET').toUpperCase(), 'GET', 'recovery is GET-only');
  const target = new URL(path, base);
  assert.equal(target.origin, base.origin);
  assert.ok(target.pathname === '/api/catalog' || target.pathname === '/api/history' ||
            target.pathname.startsWith('/api/tasks/'), 'unexpected recovery route');
  calls.push(target.pathname);
  const response = await fetch(target, {method: 'GET'});
  assert.equal(response.status, 200);
  return response.json();
}
const store = memory(hint(input.entry, input.task.task_id));
let h = harness(getJSON, store);
await h.controller.restore();
const expectedMode = input.active ? 'active' : 'last';
isTask(h, input.entry, input.task, expectedMode);
await h.controller.refresh();
isTask(h, input.entry, input.task, expectedMode);
// Selection and JavaScript controller state are reconstructed from storage + GETs.
h = harness(getJSON, store);
await h.controller.restore();
let view = isTask(h, input.entry, input.task, expectedMode);
await h.controller.select('');
assert.equal(h.last().selected, null);
assert.equal(h.last().task, null);
await h.controller.select(input.entry.id);
view = isTask(h, input.entry, input.task, expectedMode);
if (input.active) {
  assert.equal(view.task.current_stage, input.task.current_stage);
  assert.equal(view.task.usage.total_tokens, input.task.usage.total_tokens);
  assert.ok(view.task.usage.pending >= 1);
}
checkStorage(store);
console.log(JSON.stringify({ok: true, task_id: view.task.task_id, mode: view.mode,
                           requests: calls, storage: Object.fromEntries(store.values)}));
'''


class RecoveryChecks:
    """Requires the same project/output/subject properties as ProductChecks."""

    def _recovery_node(self, script, name, payload=None, timeout=10):
        node = shutil.which('node')
        self.assertIsNotNone(node, 'Node.js is required for public frontend behavior checks')
        module = self.project / 'web' / 'task-view.mjs'
        self.assertTrue(module.is_file(), 'implement the production web/task-view.mjs controller')
        result = subprocess.run([node, '--input-type=module', '-e', script, str(module)],
                                input=json.dumps(payload or {}), text=True,
                                capture_output=True, timeout=timeout, cwd=self.project)
        record = {'returncode': result.returncode, 'stdout': result.stdout,
                  'stderr': result.stderr, 'production_module': str(module)}
        self.output.mkdir(parents=True, exist_ok=True)
        report = self.output / (name + '.json')
        report.write_text(json.dumps(record, ensure_ascii=False, indent=2) + '\n')
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        summary = json.loads(result.stdout.strip().splitlines()[-1])
        self.assertTrue(summary['ok'])
        return summary

    def test_02_frontend_restoration(self):
        self._recovery_node(_NODE_UNIT, 'frontend-restoration')

    def test_07_http_frontend_restore(self):
        self.output.mkdir(parents=True, exist_ok=True)
        folder = Path(tempfile.mkdtemp(prefix='http-frontend-restore-', dir=self.output))
        scenario, _ = _prepare_scenario(folder)
        scenario['model_script'][1]['delay_seconds'] = 8
        run_root = folder / 'run'
        with ScriptedServices(scenario) as services:
            with _serve(self.subject, scenario, run_root, services) as product:
                base = product['base_url']
                entry = _catalog_entry(base)
                status, created = _http(base, '/api/tasks', 'POST',
                                        _create_payload(entry, 'frontend-restore'))
                self.assertEqual(status, 202, created)
                task_id = created['task_id']

                def read_task():
                    code, value = _http(base, f'/api/tasks/{quote(task_id)}', origin=False)
                    self.assertEqual(code, 200, value)
                    return value

                live = _wait_for(read_task, lambda value:
                                 value.get('usage', {}).get('total_tokens') == 110 and
                                 value.get('usage', {}).get('pending', 0) >= 1)
                status, history = _http(base, '/api/history', origin=False)
                self.assertEqual(status, 200, history)
                listed = next(item for item in history['tasks'] if item['task_id'] == task_id)
                expected = {'report_id': entry['id'], 'source_sha256': entry['pdf_sha256'],
                            'preset_id': 'qwen27'}
                for name, value in expected.items():
                    self.assertEqual(live.get(name), value, name)
                    self.assertEqual(listed.get(name), value, name)
                for name in ('created_at', 'updated_at'):
                    self.assertIsInstance(live.get(name), (int, float))
                    self.assertIsInstance(listed.get(name), (int, float))
                self.assertEqual(listed['created_at'], live['created_at'])
                self.assertGreaterEqual(listed['updated_at'], live['updated_at'],
                                        'later history GET may observe a newer persisted update')
                _wait_for(lambda: len(services.model_receipts), lambda count: count >= 2)
                before = (len(services.model_receipts), len(services.reference_receipts))
                self._recovery_node(_NODE_HTTP, 'http-frontend-active',
                                    {'base_url': base, 'entry': entry, 'task': live,
                                     'active': True}, timeout=6)
                self.assertEqual((len(services.model_receipts), len(services.reference_receipts)),
                                 before, 'reload/reselect must not create another request')
                task_dirs = [path.name for path in (run_root / 'tasks').iterdir()
                             if path.is_dir() and not path.name.startswith('.')]
                self.assertEqual(task_dirs, [task_id], 'restoration must not create a worker')
                terminal = _wait_for(read_task, lambda value: value.get('status') in TERMINAL)
                self.assertEqual(terminal['status'], 'candidate_ready', terminal)
        self.assertFalse(services.errors, services.errors)
        restart = dict(scenario, model_script=[], reference_script=[])
        with ScriptedServices(restart) as services:
            with _serve(self.subject, restart, run_root, services) as product:
                base = product['base_url']
                self._recovery_node(_NODE_HTTP, 'http-frontend-restart',
                                    {'base_url': base, 'entry': entry, 'task': terminal,
                                     'active': False})
                self.assertEqual(services.model_receipts, [])
                self.assertEqual(services.reference_receipts, [])
                self.assertFalse(services.errors, services.errors)
