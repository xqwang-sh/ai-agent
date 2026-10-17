import test from 'node:test';
import assert from 'node:assert/strict';
import { unitScore, resultForTrial, num } from '../assets/lesson-one-workflow.mjs';
import { historicalResult, requirePrevious, executeTool, promptFor, gradeOutput } from '../assets/lesson-one-workflow.mjs';
import { runTrial } from '../netlify/lib/workflow.mjs';
import { history, locator, units, currentLocator, currentUnits, modelFixture, reportText } from './fixtures.mjs';

test('conversion rejects incorrect prior-period values', () => {
  const converted = {
    revenue: { current: 3448.15, prior: 0 },
    operating_cost: { current: 2798.27, prior: 0 },
    operating_profit: { current: 147.44, prior: 0 },
    parent_net_profit: { current: 123.25, prior: 0 },
    basic_eps: { current: 1.35, prior: 0 },
  };
  assert.notEqual(unitScore(converted), '5/5');
});

test('an isolated calculation cannot claim earlier checks passed', () => {
  const result = resultForTrial('yoy-api', { grade: { score: '5/5' } });
  assert.deepEqual(result.caseStates.slice(0, 4), ['pending', 'pending', 'pending', 'pending']);
});

test('missing financial values are not zero', () => {
  for (const value of [null, undefined, '', '   ']) assert.equal(num(value), null);
  assert.equal(num('0'), 0);
});

test('archived outputs and recorded grades remain separate from recomputation', () => {
  assert.equal(history.records['yoy-baseline-api'].recorded_grade.score, '2/5');
  assert.equal(historicalResult(history, 'yoy-baseline-api').grade.score, '2/5');
  assert.equal(historicalResult(history, 'locator-baseline-api').caseStates[2], 'pending');
  assert.match(historicalResult(history, 'unit-api').tokens, /末次/);
  assert.deepEqual(history.records['unit-api'].parsed, units.parsed);
});

test('historical calculation inputs and preceding checks follow 02 to 03/04 and 04 to 05/06', () => {
  assert.deepEqual(units.caseStates.slice(0, 3), locator.caseStates.slice(0, 3));
  for (const id of ['unit-baseline-api','unit-api']) {
    const result = historicalResult(history, id);
    assert.equal(result.input_from.approach, 'locator-thinking-api');
    assert.deepEqual(result.workflowState.raw_values, locator.parsed.values);
  }
  for (const id of ['yoy-baseline-api','yoy-api']) {
    const result = historicalResult(history, id);
    assert.equal(result.input_from.approach, 'unit-api');
    assert.deepEqual(result.workflowState.unit_values, units.parsed);
    assert.deepEqual(result.caseStates.slice(0, 4), units.caseStates.slice(0, 4));
  }
  assert.throws(() => requirePrevious('yoy-api', units), /本轮第04步/);
});

test('failed parent and prior-period corruption stop the next stage', () => {
  const failed = structuredClone(currentLocator); failed.caseStates[1] = 'fail';
  assert.throws(() => requirePrevious('unit-api', failed), /本轮第02步/);
  const corrupt = structuredClone(currentUnits); corrupt.workflowState.unit_values.revenue.prior = 0;
  assert.throws(() => requirePrevious('yoy-api', corrupt), /两期单位检查未通过/);
});

test('live locator variants share the same prompt with no answer page', () => {
  assert.equal(promptFor('locator-baseline-api'), promptFor('locator-thinking-api'));
  assert.doesNotMatch(promptFor('locator-thinking-api'), /填写65|填写 65|第八节|67|千元/);
});

test('a wrong year, unit or continuation page fails table checks', () => {
  for (const change of [{unit:'元'}, {prior_period_header:'2024年上半年'}, {table_pages:[67]}]) {
    assert.equal(gradeOutput('locator-thinking-api', {...locator.parsed, ...change}).table, 'fail');
  }
});

test('tool arguments must match the selected input and original unit', () => {
  const values = locator.workflowState.raw_values;
  assert.match(executeTool('convert_units', {metric:'revenue', ...values.revenue, source_unit:'元'}, values), /tool_error/);
  assert.match(executeTool('convert_units', {metric:'revenue', current:1, prior:2, source_unit:'千元'}, values), /tool_error/);
});

test('two-call tool run totals usage and time, and keeps the key out of records', async () => {
  let clock = 0;
  const result = await runTrial({approach:'unit-api', apiKey:'private-test-key', previous:currentLocator, reportText, fetchImpl:modelFixture('unit-api'), now:() => { clock += 1000; return clock; }});
  assert.equal(result.grade.score, '5/5');
  assert.equal(result.usage.total_tokens, 300);
  assert.equal(result.usage.calls.length, 2);
  assert.ok(result.elapsed_seconds > result.usage.calls[1].elapsed_seconds);
  assert.doesNotMatch(JSON.stringify(result), /private-test-key/);
  assert.deepEqual(result.caseStates.slice(0, 3), ['pass','pass','pass']);
});

test('a correct final answer without required tool calls cannot pass the tool comparison', async () => {
  const result = await runTrial({approach:'unit-api', apiKey:'private-test-key', previous:currentLocator, fetchImpl:modelFixture('unit-api', {noTools:true})});
  assert.equal(result.grade.score, '0/5');
  assert.equal(result.caseStates[3], 'fail');
});

test('missing API usage is reported as incomplete', async () => {
  const result = await runTrial({approach:'unit-api', apiKey:'private-test-key', previous:currentLocator, fetchImpl:modelFixture('unit-api', {omitUsage:true})});
  assert.equal(result.usage.complete, false);
  assert.match(result.tokens, /不完整/);
});

test('invalid key reports HTTP 401 without leaking provider body or key', async () => {
  await assert.rejects(runTrial({approach:'locator-thinking-api', apiKey:'invalid-test-key', reportText, fetchImpl:modelFixture('locator-thinking-api')}), (error) => {
    assert.match(error.message, /HTTP 401/);
    assert.doesNotMatch(error.message, /invalid-test-key/);
    return true;
  });
});

test('the live workflow passes only with its own completed parent results', async () => {
  const locate = await runTrial({approach:'locator-thinking-api', apiKey:'test-key', reportText, fetchImpl:modelFixture('locator-thinking-api')});
  const convert = await runTrial({approach:'unit-api', apiKey:'test-key', previous:locate, fetchImpl:modelFixture('unit-api')});
  const yoy = await runTrial({approach:'yoy-api', apiKey:'test-key', previous:convert, fetchImpl:modelFixture('yoy-api')});
  assert.deepEqual(yoy.caseStates, ['pass','pass','pass','pass','pass']);
});

test('live calculations reject history and the wrong comparison branch before calling a model', async () => {
  let called = false;
  for (const previous of [locator, {...currentLocator, approach:'locator-baseline-api'}]) {
    await assert.rejects(runTrial({approach:'unit-api', apiKey:'test-key', previous, fetchImpl:async () => { called = true; }}), /本轮第02步/);
  }
  assert.throws(() => requirePrevious('yoy-api', {...currentUnits, approach:'unit-baseline-api'}), /本轮第04步/);
  assert.equal(called, false);
});
