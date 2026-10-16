import { readFile } from 'node:fs/promises';
import { historicalResult, METRICS } from '../assets/lesson-one-workflow.mjs';

export const history = JSON.parse(await readFile(new URL('../assets/lesson-one-history.json', import.meta.url), 'utf8'));
export const windowText = await readFile(new URL('../netlify/data/report-pages-60-75.txt', import.meta.url), 'utf8');
export const locator = historicalResult(history, 'locator-thinking-api');
export const units = historicalResult(history, 'unit-api');
export const currentLocator = {...locator, kind:'current'};
export const currentUnits = {...units, kind:'current'};
export function memoryStore() {
  const data = new Map();
  return {data, get:async (id) => structuredClone(data.get(id) || null), setJSON:async (id, value) => { data.set(id, structuredClone(value)); }};
}

export function modelFixture(approach, {badPrior = false, noTools = false, omitUsage = false} = {}) {
  let call = 0;
  return async (_url, options) => {
    call += 1;
    const body = JSON.parse(options.body);
    if (options.headers.Authorization === 'Bearer invalid-test-key') return new Response('{}', {status:401});
    const output = structuredClone(history.records[approach].parsed);
    if (badPrior && approach.startsWith('unit')) for (const item of Object.values(output)) item.prior = 0;
    let message = {content:JSON.stringify(output)};
    if (body.tools && call === 1 && !noTools) {
      const name = body.tools[0].function.name;
      const input = approach.startsWith('unit') ? locator.workflowState.raw_values : units.workflowState.unit_values;
      message = {tool_calls:METRICS.map((metric, i) => ({id:`tool-${i}`, type:'function', function:{name, arguments:JSON.stringify({metric, ...input[metric], ...(name === 'convert_units' ? {source_unit:metric === 'basic_eps' ? '元/股':'千元'} : {})})}}))};
    }
    return Response.json({model:body.model, choices:[{message}], ...(omitUsage ? {} : {usage:{prompt_tokens:call * 60, completion_tokens:call * 40, total_tokens:call * 100}})});
  };
}
