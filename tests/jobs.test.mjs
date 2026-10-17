import test from 'node:test';
import assert from 'node:assert/strict';
import { randomUUID } from 'node:crypto';
import { runJob } from '../netlify/lib/jobs.mjs';
import { runTrial } from '../netlify/lib/workflow.mjs';
import { history, memoryStore, modelFixture, reportText, currentLocator } from './fixtures.mjs';

function setup() {
  const store = memoryStore();
  let modelCalls = 0;
  const dependencies = {store, loadReport:async () => reportText, execute:async (args) => {
    modelCalls += 1;
    return runTrial({...args, fetchImpl:modelFixture(args.approach)});
  }};
  return {store, dependencies, calls:() => modelCalls};
}

test('missing key, failed prerequisites and forged client state spend no model calls', async () => {
  const {store, dependencies, calls} = setup();
  for (const extra of [{apiKey:''}, {approach:'unit-api', workflowState:history.records['unit-api'].workflow_state}]) {
    const body = {jobId:randomUUID(), approach:'locator-thinking-api', apiKey:'test-key', inputSource:'current', ...extra};
    await runJob(body, dependencies);
    assert.equal((await store.get(body.jobId)).status, 'error');
  }
  assert.equal(calls(), 0);
});

test('a submitted live job runs once and does not persist a personal key', async () => {
  const {store, dependencies, calls} = setup();
  const body = {jobId:randomUUID(), approach:'locator-thinking-api', apiKey:'do-not-store-key'};
  await runJob(body, dependencies);
  await runJob(body, dependencies);
  const item = await store.get(body.jobId);
  assert.equal(item.status, 'complete');
  assert.equal(item.result.input_source, 'report_full_text');
  assert.equal(calls(), 1);
  assert.doesNotMatch(JSON.stringify([...store.data.values()]), /do-not-store-key/);
});

test('legacy history-input requests cannot run calculations without a current parent', async () => {
  const {store, dependencies, calls} = setup();
  const jobId = randomUUID();
  await runJob({jobId, approach:'unit-api', apiKey:'test-key', inputSource:'history'}, dependencies);
  assert.equal((await store.get(jobId)).status, 'error');
  assert.equal(calls(), 0);
});

test('current runs load a server parent rather than financial state supplied by the browser', async () => {
  const {store, dependencies} = setup();
  const locateId = randomUUID();
  await runJob({jobId:locateId, approach:'locator-thinking-api', apiKey:'test-key', inputSource:'current'}, dependencies);
  const unitId = randomUUID();
  await runJob({jobId:unitId, parentJobId:locateId, approach:'unit-api', apiKey:'test-key', inputSource:'current', workflowState:{raw_values:{}}}, dependencies);
  const unit = await store.get(unitId);
  assert.equal(unit.status, 'complete');
  assert.equal(unit.result.parent_job_id, locateId);
  assert.deepEqual(unit.result.caseStates.slice(0, 4), ['pass','pass','pass','pass']);
});

test('wrong report version blocks reuse before any model request', async () => {
  const {store, dependencies, calls} = setup();
  const parentId = randomUUID();
  await store.setJSON(parentId, {status:'complete', result:{window_sha256:'other-version'}});
  const jobId = randomUUID();
  await runJob({jobId, parentJobId:parentId, approach:'unit-api', apiKey:'test-key', inputSource:'current'}, dependencies);
  assert.equal((await store.get(jobId)).status, 'error');
  assert.equal(calls(), 0);
});

test('the deployed input sends all 207 pages to the model without slicing', async () => {
  const {store, dependencies} = setup();
  let modelInput;
  dependencies.execute = (args) => runTrial({...args, fetchImpl:async (url, options) => {
    modelInput = JSON.parse(options.body).messages[0].content;
    return modelFixture(args.approach)(url, options);
  }});
  const jobId = randomUUID();
  await runJob({jobId, approach:'locator-thinking-api', apiKey:'test-key'}, dependencies);
  assert.equal((await store.get(jobId)).status, 'complete');
  const pages = [...modelInput.matchAll(/^=== 第 (\d+) 页 ===$/gm)].map(match => Number(match[1]));
  assert.deepEqual(pages, Array.from({length:207}, (_, index) => index + 1));
  assert.ok(modelInput.endsWith(reportText), 'the complete source text must be appended verbatim');
});

test('an old window run cannot become a parent for a full-report run', async () => {
  for (const fingerprint of [{window_sha256:history.window_sha256}, {report_sha256:history.window_sha256}]) {
    const {store, dependencies, calls} = setup();
    const parentId = randomUUID();
    await store.setJSON(parentId, {status:'complete', result:{...currentLocator, ...fingerprint}});
    const jobId = randomUUID();
    await runJob({jobId, parentJobId:parentId, approach:'unit-api', apiKey:'test-key'}, dependencies);
    assert.equal((await store.get(jobId)).status, 'error');
    assert.equal(calls(), 0);
  }
});

test('an incomplete report stops before spending a model call', async () => {
  const {store, dependencies, calls} = setup();
  dependencies.loadReport = async () => reportText.slice(0, 1000);
  const jobId = randomUUID();
  await runJob({jobId, approach:'locator-thinking-api', apiKey:'test-key'}, dependencies);
  const item = await store.get(jobId);
  assert.equal(item.status, 'error');
  assert.match(item.error, /全文指纹不一致/);
  assert.equal(calls(), 0);
});
