import test from 'node:test';
import assert from 'node:assert/strict';
import { randomUUID } from 'node:crypto';
import { runJob } from '../netlify/lib/jobs.mjs';
import { runTrial } from '../netlify/lib/workflow.mjs';
import { history, memoryStore, modelFixture, windowText } from './fixtures.mjs';

function setup() {
  const store = memoryStore();
  let modelCalls = 0;
  const dependencies = {store, history, loadWindow:async () => windowText, execute:async (args) => {
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
  assert.equal(item.result.input_source, 'report_window');
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
