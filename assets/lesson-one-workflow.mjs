export const MODEL = 'Qwen/Qwen3.5-4B';
export const REPORT_INPUT = Object.freeze({
  file:'report-full-text.txt', pages:207,
  sha256:'74cf20b1bb94bd8ec93aaeaa2374b977104638802427529f1ad2878ca2e7a6a5',
  source_pdf_sha256:'2648a8c4ebf637da4eeb79e58791c1faf457daa687914e325ff37d1b9676a48c',
});
export const APPROACHES = ['locator-baseline-api', 'locator-thinking-api', 'unit-baseline-api', 'unit-api', 'yoy-baseline-api', 'yoy-api'];
export const METRICS = ['revenue', 'operating_cost', 'operating_profit', 'parent_net_profit', 'basic_eps'];
const EXPECTED = {
  revenue: {current:344815421, prior:371280948, change:'-7.13%'},
  operating_cost: {current:279826859, prior:304415089, change:'-8.08%'},
  operating_profit: {current:14743578, prior:18719509, change:'-21.24%'},
  parent_net_profit: {current:12325408, prior:15510533, change:'-20.54%'},
  basic_eps: {current:1.35, prior:1.71, change:'-21.05%'},
};
const CASES = ['section-location', 'table-location', 'value-extraction', 'unit', 'change'];
export const LOCATOR_PROMPT = `下面是比亚迪2026年半年度报告的完整207页文本，每页以“=== 第 N 页 ===”开头，页码为PDF物理页。
请根据原文定位合并利润表及其续页，抄录2026H1与2025H1的五项原值。区分合并与母公司，附注号与数值，基本与稀释EPS。不要换算或计算同比，不根据常识补齐。
只返回JSON：section_name、section_start_page、table_name、table_pages、current_period_header、prior_period_header、unit、values。
section_name与section_start_page来自实际章节标题，table_pages为包含目标表及续表的物理页整数数组。两期列头与金额单位照原文填写，不清楚就填null。
values恰好包含revenue、operating_cost、operating_profit、parent_net_profit、basic_eps，分别为营业收入、营业成本、营业利润、归母净利润、基本每股收益。每项包含current、prior两期原值。EPS保持原文的元/股。`;
const PARAMETERS = {type:'object', properties:{metric:{type:'string', enum:METRICS}, current:{type:'number'}, prior:{type:'number'}}, required:['metric','current','prior']};

export function num(value) {
  if (typeof value === 'number') return Number.isFinite(value) ? value : null;
  if (typeof value !== 'string' || !value.trim()) return null;
  const text = value.trim().replace(/，/g, ',');
  if (!/^[+-]?(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?$/.test(text)) return null;
  const number = Number(text.replace(/,/g, ''));
  return Number.isFinite(number) ? number : null;
}

export function parseJson(text) {
  try { return JSON.parse(String(text || '').trim().replace(/^```(?:json)?\s*|\s*```$/g, '')); }
  catch { return {}; }
}

export function stateValues(state, field) {
  const result = {};
  for (const key of METRICS) {
    const item = state?.[field]?.[key];
    if (num(item?.current) === null || num(item?.prior) === null) throw new Error(`上一步缺少 ${key} 的两期有效数值，请先运行前一步。`);
    result[key] = {current:num(item.current), prior:num(item.prior)};
  }
  return result;
}

function pairChecks(output, converted) {
  let current = 0, prior = 0, pairs = 0;
  const perMetric = {};
  for (const metric of METRICS) {
    const divisor = converted && metric !== 'basic_eps' ? 100000 : 1;
    const tolerance = divisor === 1 ? 0.000001 : 0.005;
    const item = output?.[metric];
    const match = (period) => num(item?.[period]) !== null && Math.abs(num(item[period]) - EXPECTED[metric][period] / divisor) < tolerance;
    const c = match('current'), p = match('prior');
    current += Number(c); prior += Number(p); pairs += Number(c && p);
    perMetric[metric] = {current:c ? 'pass':'fail', prior:p ? 'pass':'fail'};
  }
  return {current:`${current}/5`, prior:`${prior}/5`, score:`${pairs}/5`, per_metric:perMetric};
}

export function unitScore(output) { return pairChecks(output, true).score; }

export function gradeOutput(approach, output) {
  if (approach.startsWith('locator')) {
    const location = output?.location || output || {};
    const pages = Array.isArray(location.table_pages) ? location.table_pages : [];
    const header = (field, year) => String(location[field] || '').replace(/\s/g, '').includes(year);
    const section = String(location.section_name || '').includes('财务报告') && num(location.section_start_page) === 65;
    const table = String(location.table_name || '').includes('合并利润表') && pages.length === 2 && pages.includes(67) && pages.includes(68) && header('current_period_header', '2026') && header('prior_period_header', '2025') && location.unit === '千元';
    return {...pairChecks(output?.values, false), section:section ? 'pass':'fail', table:table ? 'pass':'fail', returned_pages:pages};
  }
  if (approach.startsWith('unit')) return pairChecks(output, true);
  const perMetric = Object.fromEntries(METRICS.map((metric) => [metric, String(output?.[metric] || '').trim() === EXPECTED[metric].change ? 'pass':'fail']));
  return {score:`${Object.values(perMetric).filter((value) => value === 'pass').length}/5`, per_metric:perMetric};
}

export function resultForTrial(approach, receipt, previous = null) {
  const grade = receipt.grade || {};
  const states = ['pending','pending','pending','pending','pending'];
  const counts = {};
  const n = approach.startsWith('unit') ? 3 : approach.startsWith('yoy') ? 4 : 0;
  for (let i = 0; i < n; i += 1) {
    const inherited = previous?.caseStates?.[i];
    const sameView = receipt.kind === 'history' && previous?.kind === 'history' || previous?.kind === 'current';
    states[i] = inherited === 'pass' && sameView ? 'pass' : 'pending';
    if (states[i] !== 'pending') counts[CASES[i]] = previous.caseCounts[CASES[i]];
  }
  let score;
  if (approach.startsWith('locator')) {
    states[0] = grade.section === 'pass' ? 'pass':'fail';
    states[1] = grade.table === 'pass' ? 'pass':'fail';
    states[2] = grade.current === '5/5' && grade.prior === '5/5' ? 'pass':'fail';
    counts[CASES[0]] = states[0] === 'pass' ? '1/1':'0/1';
    counts[CASES[1]] = states[1] === 'pass' ? '1/1':'0/1';
    counts[CASES[2]] = `${grade.current || '0/5'}+${grade.prior || '0/5'}`;
    score = `定位 ${Number(states[0] === 'pass') + Number(states[1] === 'pass')}/2 · 数字 ${grade.current || '0/5'}+${grade.prior || '0/5'}`;
  } else {
    const index = approach.startsWith('unit') ? 3 : 4;
    states[index] = grade.score === '5/5' ? 'pass':'fail';
    counts[CASES[index]] = index === 3 ? `${grade.current || '0/5'}+${grade.prior || '0/5'}` : grade.score || '0/5';
    score = `${approach.includes('baseline') ? '无工具':'工具'} · ${grade.score || '0/5'}`;
  }
  return {score, caseStates:states, caseCounts:counts, violations:states.map((state) => ({pass:'✓', fail:'×', pending:'待测'})[state])};
}

export function historicalResult(history, approach) {
  const record = history.records[approach];
  if (!record) throw new Error('找不到历史记录。');
  const parentId = approach.startsWith('unit') ? 'locator-thinking-api' : approach.startsWith('yoy') ? 'unit-api' : null;
  const parent = parentId ? historicalResult(history, parentId) : null;
  const grade = gradeOutput(approach, record.parsed);
  const workflowState = parent ? {...parent.workflowState} : {raw_values:record.parsed.values || {}, raw_unit:record.parsed.unit};
  if (approach.startsWith('unit')) workflowState.unit_values = record.parsed;
  if (approach.startsWith('yoy')) workflowState.yoy_values = record.parsed;
  workflowState.source_step = approach;
  const result = {
    ...resultForTrial(approach, {grade, kind:'history'}, parent), kind:'history', approach, grade,
    model:record.model, parsed:record.parsed, raw_output:record.raw_output, workflowState,
    input_from:parent ? {approach:parentId, receipt_sha256:parent.receipt_sha256} : null,
    tokens:Number.isInteger(record.usage?.total_tokens) ? `${record.usage.total_tokens.toLocaleString()} tok${record.usage_scope === 'last_response' ? ' · 末次':''}` : '未记录',
    latency:`${record.elapsed_seconds.toFixed(2)}s`, elapsed_seconds:record.elapsed_seconds,
    prompt:record.prompt, prompt_note:record.prompt_note, recorded_at:record.recorded_at,
    recorded_grade:record.recorded_grade, receipt_sha256:record.receipt_sha256,
    usage:record.usage, usage_scope:record.usage_scope,
    input_report:{file:'report-pages-60-75.txt', physical_pages:[60,75], sha256:history.window_sha256},
    note:`历史定位输入为第60–75物理页窗口，并非全文运行。${parent ? `输入与前序检查沿用历史第 ${approach.startsWith('unit') ? '02':'04'} 步。` : ''}历史原始输出按修正规则复算，原评分另行保留。`,
  };
  if (approach === 'locator-baseline-api' && !record.parsed.values) {
    result.caseStates[2] = 'pending'; result.violations[2] = '待测';
    result.caseCounts['value-extraction'] = '原任务未要求';
    result.score = `定位 ${Number(grade.section === 'pass') + Number(grade.table === 'pass')}/2`;
    result.note = '历史定位输入为第60–75物理页窗口。此历史任务未要求提取数字，也未要求章节起始页，原评分却检查了该页码；不能据此单独比较 thinking，也不能当成全文运行结果。';
  }
  return result;
}

export function requirePrevious(approach, previous) {
  if (approach.startsWith('locator')) return null;
  const isUnit = approach.startsWith('unit');
  const count = isUnit ? 3 : 4;
  const validParent = previous?.kind === 'current' && previous.approach === (isUnit ? 'locator-thinking-api':'unit-api');
  if (!validParent || previous?.caseStates?.length < count || !previous?.caseStates?.slice(0, count).every((state) => state === 'pass')) throw new Error(isUnit ? '请先运行本轮第02步并通过定位与十个原值检查。' : '请先运行本轮第04步并通过两期单位检查。');
  const raw = stateValues(previous.workflowState, 'raw_values');
  if (pairChecks(raw, false).score !== '5/5' || previous.workflowState.raw_unit !== '千元') throw new Error('前序原值或单位不符合本案例，当前步骤停止。');
  if (!isUnit && unitScore(stateValues(previous.workflowState, 'unit_values')) !== '5/5') throw new Error('前序两期单位检查未通过，当前步骤停止。');
  return previous.workflowState;
}

export function toolDefinition(name) {
  const parameters = structuredClone(PARAMETERS);
  if (name === 'convert_units') { parameters.properties.source_unit = {type:'string'}; parameters.required.push('source_unit'); }
  return [{type:'function', function:{name, description:name === 'convert_units' ? '千元金额除以100000转为亿元，保留两位小数；EPS保持元/股。' : '计算(current-prior)/prior*100，保留两位小数，返回带%的字符串。', parameters}}];
}

export function executeTool(name, args, values) {
  const item = values[args.metric];
  if (!item || num(args.current) !== num(item.current) || num(args.prior) !== num(item.prior)) return 'tool_error: 参数与本次已检查的输入不一致';
  if (name === 'convert_units') {
    if (args.source_unit !== (args.metric === 'basic_eps' ? '元/股':'千元')) return 'tool_error: 原单位不一致';
    const divisor = args.metric === 'basic_eps' ? 1 : 100000;
    return JSON.stringify({current:Number((num(item.current) / divisor).toFixed(2)), prior:Number((num(item.prior) / divisor).toFixed(2))});
  }
  if (name !== 'calculate_yoy' || num(item.prior) === 0) return 'tool_error: 工具或分母无效';
  return `${((num(item.current) - num(item.prior)) / num(item.prior) * 100).toFixed(2)}%`;
}

export function promptFor(approach, state) {
  if (approach.startsWith('locator')) return LOCATOR_PROMPT;
  const unit = approach.startsWith('unit');
  const values = stateValues(state, unit ? 'raw_values':'unit_values');
  const tool = unit ? 'convert_units':'calculate_yoy';
  const task = unit ? '金额原单位为千元，转成亿元并保留两位小数。basic_eps为元/股，保持原值。输出相同的五项current/prior结构。' : '金额已统一为亿元，EPS为元/股。按(current-prior)/prior*100计算五项同比，保留两位小数与%，输出五个指标对应的字符串。';
  const instruction = approach.includes('baseline') ? '直接输出JSON，不调用工具。' : `五项分别调用${tool}，等待工具返回后，输出完整JSON。不要自行替代工具计算。`;
  return `${task}\n${instruction}\n输入：${JSON.stringify(values)}`;
}

