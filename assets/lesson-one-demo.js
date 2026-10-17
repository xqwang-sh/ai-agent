import { historicalResult, promptFor, requirePrevious } from './lesson-one-workflow.mjs';

const topTabs = [...document.querySelectorAll('.tabs .tab')];
const panels = [...document.querySelectorAll('.panel')];
function showTab(id, focus = false) {
  topTabs.forEach((tab, index) => {
    const active = tab.dataset.tab === id;
    tab.setAttribute('aria-selected', active); tab.tabIndex = active ? 0 : -1;
    panels[index].hidden = !active;
    if (active && focus) tab.focus();
  });
  history.replaceState(null, '', `#${id}`);
}
topTabs.forEach((tab, index) => {
  tab.addEventListener('click', () => showTab(tab.dataset.tab));
  tab.addEventListener('keydown', (event) => {
    if (!['ArrowRight','ArrowLeft','Home','End'].includes(event.key)) return;
    event.preventDefault();
    const next = event.key === 'Home' ? 0 : event.key === 'End' ? topTabs.length - 1 : (index + (event.key === 'ArrowRight' ? 1 : -1) + topTabs.length) % topTabs.length;
    showTab(topTabs[next].dataset.tab, true);
  });
});
showTab(['product','approaches','evals'].includes(location.hash.slice(1)) ? location.hash.slice(1) : 'product');
document.querySelectorAll('[data-round]').forEach((button) => button.addEventListener('click', () => {
  document.querySelectorAll('[data-round]').forEach((item) => item.setAttribute('aria-selected', item === button));
  document.querySelectorAll('[data-round-detail]').forEach((panel) => { panel.hidden = panel.dataset.roundDetail !== button.dataset.round; });
}));
document.querySelectorAll('[data-jump-evals]').forEach((button) => button.addEventListener('click', () => showTab('evals')));

const rows = [...document.querySelectorAll('[data-approach-row]')];
const cards = [...document.querySelectorAll('[data-eval]')];
const keyInput = document.querySelector('[data-api-key]');
const score = document.querySelector('[data-current-score]');
const note = document.querySelector('[data-current-score-note]');
const receiptText = document.querySelector('[data-receipt]');
const current = new Map();
const parents = {locate:null, unit:null};
let archive, mode = 'history', selected = 'yoy-api', running = null;

function resultFor(id) { return archive ? mode === 'history' ? historicalResult(archive, id) : current.get(id) : null; }
function safeJson(value) { return JSON.stringify(value, null, 2); }
function paintCases(result) {
  cards.forEach((card, index) => {
    const state = result?.caseStates?.[index] || 'pending';
    card.dataset.status = state;
    card.querySelector('.case-status').textContent = result?.caseCounts?.[card.dataset.eval] || ({pass:'通过', fail:'未通过', pending:'待检查'})[state];
    card.querySelector('.case-observation').hidden = true;
  });
}

function paintSelected() {
  const result = resultFor(selected);
  paintCases(result);
  score.textContent = result?.error ? '运行失败' : result?.score || '未运行';
  note.textContent = result ? `${mode === 'history' ? '历史结果':'本次运行'} · ${result.note || result.error || ''}` : '填写个人 Key，先运行02，再用03/04比较换算，最后用05/06比较同比。后续只读取本轮已通过的对应前序结果。';
  receiptText.textContent = result ? safeJson(result) : '本行尚未运行。';
  document.querySelector('[data-mode-caption]').textContent = mode === 'history' ? '历史定位输入：第60–75物理页窗口，并非全文运行。历史链条：02 → 03/04，04 → 05/06。后续行沿用对应前序。工具行仅记录了末次响应 tokens。' : '本次定位输入：report-full-text.txt，完整207页，不预先截取目标页。主线02 → 04 → 06；03/04读取本轮02，05/06读取本轮04。重跑02或04会清空对应后续结果。';
}

function renderRows() {
  rows.forEach((row) => {
    const id = row.dataset.approachRow;
    const result = resultFor(id);
    row.dataset.status = running === id ? 'running' : result?.error ? 'error' : result ? 'run' : 'idle';
    row.classList.toggle('selected-row', selected === id);
    row.querySelector('.row-score').textContent = running === id ? '运行中…' : result?.error ? '运行失败' : result?.score || '未运行';
    row.querySelector('.row-tokens').textContent = result?.tokens || '';
    row.querySelector('.row-latency').textContent = result?.latency || '';
    const violations = row.querySelector('.row-violations');
    violations.replaceChildren();
    (result?.violations || []).forEach((value) => {
      const span = document.createElement('span');
      span.className = `violation ${{'✓':'good','×':'bad','待测':'pending'}[value] || 'pending'}`;
      span.textContent = value; violations.append(span);
    });
    const button = row.querySelector('.row-run');
    button.disabled = Boolean(running);
    button.textContent = running === id ? '运行中…' : 'Run ↗';
  });
  document.querySelectorAll('[data-result-mode]').forEach((button) => button.setAttribute('aria-pressed', button.dataset.resultMode === mode));
  document.querySelector('[data-reset-evals]').disabled = Boolean(running);
  paintSelected();
}

function invalidate(approach) {
  if (approach === 'locator-thinking-api') {
    parents.locate = null; parents.unit = null;
    for (const id of [...current.keys()]) if (!id.startsWith('locator')) current.delete(id);
  } else if (approach === 'unit-api') {
    parents.unit = null;
    for (const id of [...current.keys()]) if (id.startsWith('yoy')) current.delete(id);
  }
}

async function waitForJob(jobId) {
  const deadline = Date.now() + 15 * 60 * 1000;
  while (Date.now() < deadline) {
    const response = await fetch(`/api/run-status?job=${encodeURIComponent(jobId)}`, {cache:'no-store'});
    const status = await response.json();
    if (!response.ok || !status.ok) throw new Error(status.error || '暂时无法查询任务。');
    if (status.status === 'complete') return status.result;
    if (status.status === 'error') {
      const failure = new Error(status.error || '运行失败。');
      failure.usage = status.usage; failure.elapsed_seconds = status.elapsed_seconds;
      throw failure;
    }
    note.textContent = status.status === 'running' ? '线上任务正在调用模型与检查器，可稍后查看结果。' : '线上任务已提交，等待开始。';
    await new Promise((resolve) => setTimeout(resolve, 2000));
  }
  throw new Error('超过15分钟仍未收到结果，请保留任务编号后重试。');
}

async function runApproach(id) {
  if (running || !archive) return;
  selected = id; mode = 'current'; renderRows();
  const apiKey = keyInput.value.trim();
  if (!apiKey) { score.textContent = '未运行'; paintCases(null); note.textContent = '请先填写自己的硅基流动 API Key。'; keyInput.focus(); return; }
  let previous = null;
  if (!id.startsWith('locator')) {
    previous = parents[id.startsWith('unit') ? 'locate':'unit'];
    try { requirePrevious(id, previous); }
    catch (error) { score.textContent = '未运行'; paintCases(null); note.textContent = error.message; return; }
  }
  invalidate(id);
  renderProduct();
  current.delete(id); selected = id; mode = 'current'; running = id;
  renderRows(); score.textContent = '运行中…';
  const jobId = crypto.randomUUID();
  note.textContent = '正在提交线上任务。';
  try {
    const response = await fetch('/api/run', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({approach:id, jobId, parentJobId:previous?.job_id, apiKey})});
    if (response.status !== 202) throw new Error('线上服务未接受任务，请稍后重试。');
    const result = await waitForJob(jobId);
    current.set(id, result);
    if (id === 'locator-thinking-api') parents.locate = result;
    else if (id === 'unit-api') parents.unit = result;
    if (id.startsWith('yoy') && result.caseStates?.every((state) => state === 'pass')) renderProduct(result);
  } catch (error) {
    current.set(id, {kind:'current', approach:id, job_id:jobId, error:error.message, usage:error.usage || null, tokens:error.usage ? `${error.usage.total_tokens} tok · 用量不完整` : '', latency:Number.isFinite(error.elapsed_seconds) ? `${error.elapsed_seconds.toFixed(2)}s` : ''});
  } finally { running = null; renderRows(); }
}

function renderProduct(result = null) {
  const state = result?.workflowState;
  const raw = state?.raw_values || archive.records['locator-thinking-api'].parsed.values;
  const yoy = state?.yoy_values || archive.records['yoy-api'].parsed;
  const metrics = ['revenue','operating_cost','operating_profit','parent_net_profit','basic_eps'];
  document.querySelectorAll('.brief-table tbody tr').forEach((row, index) => {
    const cells = row.querySelectorAll('td');
    const metric = metrics[index], divisor = metric === 'basic_eps' ? 1 : 100000;
    for (const [i, period] of ['current','prior'].entries()) cells[i].textContent = `${(Number(raw[metric][period]) / divisor).toLocaleString('en-US', {minimumFractionDigits:2, maximumFractionDigits:2})} ${metric === 'basic_eps' ? '元/股':'亿'}`;
    cells[2].textContent = yoy[metric];
  });
  document.querySelector('[data-product-status]').textContent = result ? '本次五项检查通过 · 待人工复核' : '历史计算样例';
  document.querySelector('.brief-status span:first-child').textContent = result ? '本次结果与前序记录一致' : '历史原始输出与复算记录';
}

rows.forEach((row) => {
  row.addEventListener('click', () => { selected = row.dataset.approachRow; renderRows(); });
  row.querySelector('[data-run-approach]').addEventListener('click', (event) => { event.stopPropagation(); runApproach(row.dataset.approachRow); });
});
document.querySelectorAll('[data-result-mode]').forEach((button) => button.addEventListener('click', () => { mode = button.dataset.resultMode; renderRows(); }));
document.querySelector('[data-reset-evals]').addEventListener('click', () => {
  current.clear(); parents.locate = null; parents.unit = null; mode = 'current'; renderProduct(); renderRows();
});
document.querySelector('[data-clear-key]').addEventListener('click', () => { keyInput.value = ''; });
document.querySelector('[data-download-receipt]').addEventListener('click', () => {
  const result = resultFor(selected);
  if (!result) return;
  const url = URL.createObjectURL(new Blob([safeJson(result)], {type:'application/json'}));
  const link = document.createElement('a'); link.href = url; link.download = `${mode}-${selected}.json`; link.click(); URL.revokeObjectURL(url);
});
fetch('assets/lesson-one-history.json').then((response) => {
  if (!response.ok) throw new Error('历史回执暂时无法读取，请刷新页面。');
  return response.json();
}).then((data) => {
  archive = data;
  document.querySelectorAll('[data-round-detail]').forEach((panel) => {
    const id = panel.dataset.roundDetail, result = historicalResult(archive, id);
    panel.querySelector('.round-metrics strong').textContent = result.score;
    panel.querySelector('.prompt-window .window-columns > div:last-child pre').textContent = `${result.prompt}\n\n${id.startsWith('locator') ? '[历史输入：当时第60–75页窗口由程序追加，并非完整207页]':''}`;
    panel.querySelector('.prompt-window header > span:nth-child(2)').textContent = '历史运行配置复原 · 原输出见 Eval 行记录';
    panel.querySelector('.prompt-window .column-label.new').textContent = '历史提示词配置复原';
    panel.querySelector('.round-result p').textContent = `历史复算：${result.score}`;
    panel.querySelector('.harness-window header > span:nth-child(2)').textContent = '线上运行与检查规则';
    panel.querySelector('.harness-window pre').textContent = id.startsWith('locator')
      ? `本次输入：report-full-text.txt，完整207页\n两组使用同一全文、同一提示词、同一输出字段\nthinking = ${id === 'locator-thinking-api'}\n检查章节、表名、完整表页、两期列头与原单位\n逐项核对五项本期与同期原值\n每次调用记录实际 usage`
      : `${id.startsWith('unit') ? '输入：已通过的定位与十个原值\n检查：金额千元转亿元 ÷100000，EPS不变\n每项同时检查本期与同期' : '输入：已通过的单位换算结果\n公式：(current-prior)/prior*100\n逐项检查五个同比与百分比精度'}\n${id.includes('baseline') ? '本轮不提供工具' : '逐项调用工具，程序检查参数与最终输出'}\n只沿用所选前序记录的真实检查状态\n用量累计所有调用，不只记录末次响应`;
    const live = document.createElement('details');
    const summary = document.createElement('summary'); summary.textContent = '本次线上 Run 使用的提示词';
    const pre = document.createElement('pre');
    const state = id.startsWith('unit') ? historicalResult(archive, 'locator-thinking-api').workflowState : id.startsWith('yoy') ? historicalResult(archive, 'unit-api').workflowState : null;
    pre.textContent = `${promptFor(id, state)}${state ? '\n以上数值仅示范模板；实际Run只用本轮对应前序。':'\n[程序随后完整追加 report-full-text.txt 的第1–207页，不裁剪、不先摘要。]'}`;
    live.append(summary, pre); panel.append(live);
  });
  renderProduct(); renderRows();
}).catch((error) => { score.textContent = '读取失败'; note.textContent = error.message; });
