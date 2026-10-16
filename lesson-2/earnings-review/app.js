'use strict';

const $ = (id) => document.getElementById(id);
const ACTIVE = new Set(['queued', 'running']);
const STEPS = [
  ['prepare', '读取报告与全文索引', 'program'],
  ['locate', '定位财务证据', 'model'],
  ['extract', '抄录、补证与原文检查', 'model'],
  ['vision', '独立页图核验', 'model'],
  ['external', '同花顺财务数据比对', 'service'],
  ['delivery', '生成核验后的复盘', 'program'],
];
const store = {
  csrf: '', catalog: null, presets: [], jobs: [], budget: null, activeJobId: null,
  selectedReportId: null, presetId: null, job: null, previous: null,
  generation: 0, pollTimer: null, pollingKey: null, starting: false, connectionError: null,
  startIntent: null, reviews: new Map(), reviewKey: '', historyKey: '',
};
const labels = {queued:'等待运行',running:'正在运行',candidate_ready:'核验完成',stopped:'已停止',interrupted:'运行中断'};
const stageLabels = {prepare:'读取报告',locate:'定位证据',extract:'抄录与补证',continue_text:'文本续跑',vision:'独立视觉核验',continue_vision:'视觉续跑',external:'外部比对',delivery:'生成复盘',complete:'运行结束'};
const checkLabels = {pending:'未开始',running:'核验中',matched:'一致',stopped:'未通过',mismatch:'不一致'};
const escapeHtml = (value) => String(value ?? '').replace(/[&<>"']/g, (c) => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const count = (value) => Array.isArray(value) ? value.length : Number.isFinite(Number(value)) ? Number(value) : 0;
const integer = (value) => Number.isFinite(Number(value)) ? Number(value).toLocaleString('zh-CN', {maximumFractionDigits:0}) : '—';
function numberText(value) {
  if (value === null || value === undefined || value === '') return '—';
  const text = String(value);
  if (!/^[-+]?\d+(?:\.\d+)?$/.test(text)) return text;
  const [whole, fraction] = text.split('.');
  return whole.replace(/\B(?=(\d{3})+(?!\d))/g, ',') + (fraction === undefined ? '' : `.${fraction}`);
}
function numeric(value) {
  if (value === null || value === undefined || value === '') return null;
  const n = Number(String(value).replace(/,/g, ''));
  return Number.isFinite(n) ? n : null;
}
function duration(seconds) {
  const n = numeric(seconds);
  if (n === null) return '—';
  if (n < 60) return `${n.toFixed(n < 10 ? 1 : 0)} 秒`;
  return `${Math.floor(n / 60)} 分 ${Math.floor(n % 60)} 秒`;
}
function dateTime(unix) {
  return Number.isFinite(Number(unix)) && unix ? new Date(Number(unix) * 1000).toLocaleString('zh-CN', {month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit',hour12:false}) : '时间未记录';
}
function clockTime(unix) {
  return Number.isFinite(Number(unix)) ? new Date(Number(unix) * 1000).toLocaleTimeString('zh-CN',{hour12:false}) : '—';
}
function modelName(model) { return String(model || '').replace(/^Qwen\//, ''); }
function localUrl(raw) {
  if (!raw) return '';
  try { const url = new URL(String(raw), window.location.origin); return url.origin === window.location.origin ? url.pathname + url.search + url.hash : ''; }
  catch { return ''; }
}
function artifact(jobId, key) { return new URL(`data/${({pdf:"report.pdf",internal:"internal.json",external:"external.json",trace:"trace.json"})[key] || key + ".png"}`, window.location.href).pathname; }
function badge(text, kind = 'neutral') { return `<span class="badge badge-${kind}"><span class="badge-dot" aria-hidden="true"></span>${escapeHtml(text)}</span>`; }
function jobKind(job) { return job.status === 'candidate_ready' ? 'sage' : ACTIVE.has(job.status) ? 'blue' : 'coral'; }
function selectedEntry() { return store.catalog?.entries?.find((entry) => entry.id === store.selectedReportId) || null; }
function sameReport(job, entry) { return Boolean(job && entry && job.report_id === entry.id && job.pdf_sha256 === entry.pdf_sha256); }
function reportJobs() { const entry = selectedEntry(); return store.jobs.filter((job) => sameReport(job, entry)); }
function retainSummary(job) {
  const summary = {id:job.id,report_id:job.report_id,pdf_sha256:job.pdf_sha256,company:job.company,short_name:job.short_name,status:job.status,historical:job.historical,preset_id:job.preset.id,text_model:job.preset.text_model,vision_model:job.preset.vision_model,created_unix:job.created_unix};
  store.jobs = [summary,...store.jobs.filter((item) => item.id !== job.id)].sort((a,b) => b.created_unix - a.created_unix);
}
function showNotice(id, message, kind = '', action = null) {
  const box = $(id);
  box.hidden = !message;
  box.className = `notice ${kind}`.trim();
  box.replaceChildren();
  if (!message) return;
  const span = document.createElement('span'); span.textContent = message; box.append(span);
  if (action) { const button = document.createElement('button'); button.type = 'button'; button.textContent = action.label; button.addEventListener('click', action.run); box.append(button); }
}
async function api(path) {
  const name = path === '/api/state' ? 'state' : /^\/api\/jobs\/[a-z0-9_-]+$/.test(path) ? 'run' : null;
  if (!name) throw new Error('此页面只提供已核验示例；请在本地启动完整产品。');
  const response = await fetch(`data/${name}.json`);
  if (!response.ok) throw new Error('暂时无法读取公开示例。');
  return response.json();
}
function updateControls() {
  $('run-button').disabled = false;
  $('run-label').textContent = '按讲义在本地运行 ↗';
  $('run-caption').textContent = '公开页浏览历史示例，不发起模型请求';
  $('preset-select').disabled = false;
  $('folder-open').disabled = true;
  const preset = store.presets.find((p) => p.id === store.presetId);
  $('preset-description').textContent = preset ? `本地方案：文本 ${modelName(preset.text_model)} · 视觉 ${modelName(preset.vision_model)}。下方示例保留原运行模型。` : '';
}
function renderCatalog() {
  const catalog = store.catalog;
  $('report-count').textContent = integer(catalog?.entries?.length || 0);
  $('folder-label').textContent = catalog?.folder_path || '尚未选择文件夹';
  $('folder-label').title = catalog?.folder_path || '';
  $('company-list').innerHTML = (catalog?.entries || []).map((entry) => `<button type="button" class="company-button ${entry.id === store.selectedReportId ? 'selected' : ''}" data-report-id="${escapeHtml(entry.id)}" aria-current="${entry.id === store.selectedReportId ? 'true' : 'false'}"><span class="company-monogram">${escapeHtml((entry.short_name || entry.company).slice(0,2))}</span><span class="company-copy"><strong>${escapeHtml(entry.short_name || entry.company)}</strong><small>${escapeHtml(entry.thscode)} · ${escapeHtml(entry.period === '2026H1' ? '2026 半年报' : entry.period)}</small></span>${entry.id === store.selectedReportId ? '<span class="company-arrow" aria-hidden="true">↗</span>' : ''}</button>`).join('') || '<p class="sidebar-note">此文件夹暂无可运行的半年报。可以换一个文件夹。</p>';
  const excluded = catalog?.excluded || [];
  $('excluded-wrap').hidden = !excluded.length;
  $('excluded-summary').textContent = `未纳入的文件 (${excluded.length})`;
  $('excluded-list').innerHTML = excluded.map((item) => `<li>${escapeHtml(item.filename)}<br>${escapeHtml(item.reason)}</li>`).join('');
}
function renderSource() {
  const entry = selectedEntry();
  $('company-name').textContent = entry?.short_name || entry?.company || '选择一份半年报';
  $('company-meta').innerHTML = entry ? `<span>${escapeHtml(entry.thscode)}</span><span>${escapeHtml(entry.period === '2026H1' ? '2026 半年报' : entry.period)}</span><span>原始 PDF</span>` : '选择本地报告';
  $('source-description').textContent = entry ? `${entry.filename} · ${integer(entry.pages)} 个物理页 · PDF ${entry.pdf_sha256.slice(0,12)}` : '读取本地 PDF，选择公司后开始。';
  $('source-description').title = entry ? `${entry.company}\nSHA256 ${entry.pdf_sha256}` : '';
  updateControls();
}
function renderBudget() {
  const budget = store.budget;
  $('budget-details').hidden = !budget;
  if (!budget) return;
  $('budget-summary').textContent = `模型调用最多 ${integer(budget.max_requests)} 次 · 已知 Token 准入阈值 ${integer(budget.token_admission)} · 时间准入阈值 ${integer(budget.seconds_admission)} 秒 · 失败反馈最多 ${integer(budget.max_feedback)} 次 · 连续 ${integer(budget.no_progress)} 次无进展时停止。`;
}
function clearJobDisplay() {
  store.job = null; store.previous = null; store.reviews.clear(); store.reviewKey = ''; store.historyKey = '';
  $('run-section').hidden = true; $('review-section').hidden = true; $('history-section').hidden = true;
  $('history-list-section').hidden = true; $('review-section').replaceChildren(); $('history-review').replaceChildren();
  $('empty-state').hidden = !selectedEntry();
  showNotice('job-notice', '');
}
async function selectReport(reportId) {
  if (!(store.catalog?.entries || []).some((entry) => entry.id === reportId)) return;
  clearTimeout(store.pollTimer); store.generation += 1; store.selectedReportId = reportId;
  clearJobDisplay(); renderCatalog(); renderSource();
  const jobs = reportJobs();
  renderHistoryList();
  if (!jobs.length) { schedulePoll(); return; }
  const primary = jobs.find((job) => job.id === store.activeJobId) || jobs[0];
  await selectJob(primary.id);
}
async function selectJob(jobId) {
  const generation = ++store.generation;
  clearTimeout(store.pollTimer); store.job = null; store.previous = null; store.reviewKey = ''; store.historyKey = '';
  $('review-section').hidden = true; $('history-section').hidden = true; $('empty-state').hidden = true;
  $('run-section').hidden = true;
  showNotice('global-notice', '正在读取这次运行的记录…');
  try {
    const job = await api(`/api/jobs/${encodeURIComponent(jobId)}`);
    if (generation !== store.generation || !sameReport(job, selectedEntry())) return;
    store.job = job; store.connectionError = null; retainSummary(job);
    showNotice('global-notice', ''); renderJob(job); renderHistoryList();
    loadPrevious(job, generation);
    schedulePoll();
  } catch (error) {
    if (generation !== store.generation) return;
    showNotice('global-notice', error.message, 'error', {label:'重新读取',run:() => selectJob(jobId)});
    $('empty-state').hidden = false; updateControls();
  }
}
async function loadPrevious(job, generation) {
  const previous = reportJobs().find((item) => item.id !== job.id && item.status === 'candidate_ready' && item.created_unix <= job.created_unix);
  if (!previous || job.review) { $('history-section').hidden = true; return; }
  try {
    const snapshot = await api(`/api/jobs/${encodeURIComponent(previous.id)}`);
    if (generation !== store.generation || store.job?.id !== job.id || !sameReport(snapshot, selectedEntry()) || !snapshot.review) return;
    store.previous = snapshot;
    $('history-context').textContent = `${dateTime(snapshot.created_unix)} · ${snapshot.company} · ${modelName(snapshot.preset.text_model)} / ${modelName(snapshot.preset.vision_model)}。以下属于此前的独立运行，不代表本次运行通过。`;
    $('history-review').innerHTML = reviewHtml(snapshot, true); $('history-section').hidden = false;
  } catch { if (generation === store.generation) $('history-section').hidden = true; }
}
function plannedModels(stageId, job) { return stageId === 'vision' ? [job.preset?.vision_model] : ['locate','extract'].includes(stageId) ? [job.preset?.text_model] : []; }
function stageHtml(stage, index, job) {
  const status = stage.status || 'pending';
  const isModel = stage.kind === 'model';
  const models = Array.isArray(stage.model_ids) ? [...new Set(stage.model_ids.filter(Boolean))] : [];
  const modelDescription = isModel ? (models.length ? models.map(modelName).join(' · ') : `计划 ${plannedModels(stage.id, job).filter(Boolean).map(modelName).join(' · ')}`) : stage.kind === 'service' ? '外部数据服务 · 无模型调用' : '程序处理 · 无模型调用';
  const pending = count(stage.pending_calls), unknown = count(stage.unknown_calls);
  const note = pending ? `${pending} 次待返回` : unknown ? `${unknown} 次用量未知` : '';
  const usageUncertain = pending || unknown || ['pending','unknown'].includes(stage.usage_state);
  const tokenLine = status === 'pending' ? '未开始' : isModel ? `${usageUncertain ? '已知 ' : ''}${integer(stage.tokens || 0)} tokens` : '0 模型 tokens';
  const icons = {completed:'✓',running:'•',stopped:'!',pending:String(index+1).padStart(2,'0')};
  return `<li class="stage-row ${escapeHtml(status)}"><span class="stage-icon" aria-hidden="true">${escapeHtml(icons[status] || icons.pending)}</span><div><div class="stage-label">${escapeHtml(stage.label || STEPS[index][1])}</div><span class="stage-sub">${escapeHtml(modelDescription)}</span></div><div class="stage-values">${escapeHtml(tokenLine)}<small>${escapeHtml(status === 'pending' ? '' : duration(stage.elapsed_seconds))}</small>${note ? `<small class="usage-note">${escapeHtml(note)}</small>` : ''}</div></li>`;
}
function renderCheck(kind, check, job) {
  check = check || {status:'pending'};
  const status = check.status || 'pending';
  const color = status === 'matched' ? 'sage' : status === 'running' ? 'blue' : ['stopped','mismatch'].includes(status) ? 'coral' : 'neutral';
  $(`${kind}-status`).innerHTML = badge(checkLabels[status] || status, color);
  const hasCount = check.matched !== null && check.matched !== undefined && check.total !== null && check.total !== undefined;
  $(`${kind}-count`).innerHTML = hasCount ? `${escapeHtml(integer(check.matched))}<small>/ ${escapeHtml(integer(check.total))}</small>` : '—';
  $(`${kind}-count`).className = `verification-count ${status === 'matched' ? 'is-matched' : ['stopped','mismatch'].includes(status) ? 'is-failed' : ''}`;
  const descriptions = kind === 'internal' ? {
    pending:'尚未执行。文本证据检查通过后，独立读取原始 PDF 页图。',running:'模型正在独立读取页图；文本抄录和外部答案不进入视觉上下文。',matched:'当前最终修订的文字抄录与独立页图核验一致。',stopped:'内部核验尚未通过，当前结果不能进入最终复盘。',mismatch:'文字与独立页图抄录存在差异，查看轨迹中的反馈和续跑。',
  } : {
    pending:'尚未执行。内部核验通过后，查询同花顺财务数据。',running:'正在获取独立财务数据，并按报告原始披露精度比对。',matched:'当前最终修订与同花顺独立财务数据一致。',stopped:'外部核验未完成或未通过，查看本次运行的停止原因。',mismatch:'报告抄录与同花顺存在差异，当前结果尚未通过外部核验。',
  };
  $(`${kind}-description`).textContent = descriptions[status] || '请查看本次运行的核验记录。';
  const link = $(`${kind}-link`); link.hidden = !job.review; link.href = artifact(job.id, kind);
}
function renderJob(job) {
  if (!sameReport(job, selectedEntry())) return;
  $('run-section').hidden = false; $('empty-state').hidden = true;
  $('run-heading').textContent = job.historical ? '课前示例运行记录' : '本次运行';
  $('job-badges').innerHTML = (job.historical ? badge('历史结果','neutral') : '') + badge(labels[job.status] || job.status,jobKind(job));
  $('job-identity').innerHTML = `<span>${escapeHtml(job.short_name || job.company)}</span><span>${escapeHtml(dateTime(job.created_unix))}</span><span>运行 <code>${escapeHtml(job.id)}</code></span><span>PDF ${escapeHtml(job.pdf_sha256.slice(0,12))}</span>`;
  if (store.connectionError) showNotice('job-notice', `连接暂时中断，已保留最后读取的状态。${store.connectionError}`, 'warning');
  else if (['stopped','interrupted'].includes(job.status)) showNotice('job-notice', `${job.status === 'interrupted' ? '本次运行已中断。' : '本次运行已停止。'}${(job.issues || []).join('；') || '未生成通过两层核验的新复盘。'} 原始轨迹与已发生的消耗已保留。`, 'error');
  else if (job.historical) showNotice('job-notice', '这是课前真实运行的留存结果，所有续跑计入下方合计。按讲义在本地运行后，可以生成自己的记录。');
  else showNotice('job-notice','');
  const receivedStages = new Map((job.stages || []).map((stage) => [stage.id,stage]));
  $('stage-list').innerHTML = STEPS.map(([id,label,kind],index) => stageHtml(receivedStages.get(id) || {id,label,kind,status:'pending'},index,job)).join('');
  $('current-operation').textContent = ACTIVE.has(job.status) ? stageLabels[job.current_step] || '正在启动' : job.status === 'candidate_ready' ? '最终证据已封存' : '已结束';
  const usage = job.usage || {}, pending = count(usage.pending_calls), unknown = count(usage.unknown_calls);
  const caveats = [];
  if (pending) caveats.push(`${pending} 次调用的用量待返回`);
  if (unknown) caveats.push(`${unknown} 次调用的用量未知`);
  $('run-totals').innerHTML = `<div class="total-item"><span>${caveats.length ? '已知 TOKENS' : '累计 TOKENS'}</span><strong>${escapeHtml(integer(usage.total_tokens || 0))}</strong><p>输入 ${escapeHtml(integer(usage.prompt_tokens || 0))} · 输出 ${escapeHtml(integer(usage.completion_tokens || 0))}</p></div><div class="total-item"><span>模型调用</span><strong>${escapeHtml(integer(usage.requests || 0))}<small>次</small></strong><p>原运行含续跑与重试</p></div><div class="total-item"><span>示例流程耗时</span><strong style="font-size:17px">${escapeHtml(job.started_unix ? duration(job.elapsed_seconds) : '尚未开始')}</strong><p>补证反馈 ${escapeHtml(integer(job.feedback_count || 0))} 次</p></div>${caveats.length ? `<p class="usage-caveat">${escapeHtml(caveats.join('；'))}，已知合计不代表完整消耗。</p>` : ''}`;
  renderCheck('internal',job.internal,job); renderCheck('external',job.external,job); renderTrace(job);
  const reviewKey = job.review ? `${job.id}:${job.review.seal_sha256}` : '';
  if (reviewKey !== store.reviewKey) { store.reviewKey = reviewKey; $('review-section').innerHTML = job.review ? reviewHtml(job,false) : ''; }
  $('review-section').hidden = !job.review;
  if (job.review) { $('history-section').hidden = true; }
  updateControls();
}
function renderTrace(job) {
  const calls = job.calls || [], events = job.events || [];
  $('trace-summary').textContent = `${calls.length} 次调用 · ${events.length} 条事件`;
  $('trace-download').href = artifact(job.id,'trace');
  $('call-rows').innerHTML = calls.map((call) => {
    const state = call.usage_state || (call.usage ? 'complete' : call.status === 'reserved' ? 'pending' : 'unknown');
    const usage = call.usage;
    const usageText = usage ? integer(usage.total_tokens) : state === 'pending' ? '待返回' : '未知';
    const statusText = call.status === 'completed' ? '已返回' : call.status === 'failed' ? '失败' : call.status === 'reserved' ? '进行中' : call.status;
    return `<tr><td>${escapeHtml(call.id)}</td><td>${escapeHtml(stageLabels[call.stage] || call.stage)}</td><td>${escapeHtml(modelName(call.model))}</td><td>${escapeHtml(usageText)}${usage ? `<small>输入 ${escapeHtml(integer(usage.prompt_tokens))} / 输出 ${escapeHtml(integer(usage.completion_tokens))}</small>` : ''}${state === 'unknown' && usage ? '<small>部分用量未知</small>' : ''}</td><td>${escapeHtml(duration(call.elapsed_seconds))}</td><td>${badge(statusText || '未知',call.status === 'failed' ? 'coral' : call.status === 'reserved' ? 'blue' : 'neutral')}</td></tr>`;
  }).join('') || '<tr><td colspan="6" class="muted">本次尚无模型调用。</td></tr>';
  $('event-list').innerHTML = events.slice(-80).reverse().map((event) => `<li><time>${escapeHtml(clockTime(event.unix))}</time><span>${escapeHtml(event.message || `${stageLabels[event.stage] || event.stage || ''} ${event.kind || ''}`)}</span></li>`).join('') || '<li><time>—</time><span class="muted">尚无运行事件。</span></li>';
}
function changeText(value, unit = '%', prefix = '同比') {
  const n = numeric(value);
  if (n === null) return {html:'<span class="muted">暂无可比变动</span>',kind:''};
  const kind = n > 0 ? 'positive' : n < 0 ? 'negative' : '';
  const sign = n > 0 ? '+' : '';
  return {html:`${escapeHtml(prefix)} ${sign}${escapeHtml(numberText(value))}${escapeHtml(unit || '')}`,kind};
}
function pageButtons(jobId, row) {
  return [...new Set([row.value_page,row.unit_page].filter((page) => Number.isInteger(Number(page)) && Number(page) > 0))].map((page) => `<button type="button" class="evidence-inline" data-evidence-job="${escapeHtml(jobId)}" data-evidence-page="${escapeHtml(page)}">P${escapeHtml(page)} ↗</button>`).join(' ');
}
function reviewHtml(job, history) {
  const review = job.review;
  if (!review || review.company !== job.company) return '';
  store.reviews.set(job.id,{job,review});
  const current = review.current_period === '2026H1' ? '2026 上半年' : review.current_period;
  const prior = review.prior_period === '2025H1' ? '2025 上半年' : review.prior_period;
  const highlights = (review.highlights || []).map((item) => {
    const change = changeText(item.change,item.change_unit,['百分点','个百分点'].includes(item.change_unit) ? '较上年同期' : '同比');
    return `<article class="highlight-card"><span>${escapeHtml(item.label)}</span><div class="highlight-value">${escapeHtml(numberText(item.value))}<small>${escapeHtml(item.unit)}</small></div><p class="highlight-change ${change.kind}">${change.html}</p></article>`;
  }).join('');
  const rows = (review.rows || []).map((row) => {
    const change = changeText(row.yoy_percent,'%','');
    return `<tr><td>${escapeHtml(row.label)}<span class="unit-note">${escapeHtml(row.display_unit)}</span></td><td><strong>${escapeHtml(numberText(row.display_current))}</strong></td><td>${escapeHtml(numberText(row.display_prior))}</td><td class="${change.kind}">${change.html}</td><td>${pageButtons(job.id,row)}</td></tr>`;
  }).join('');
  const derived = (review.derived || []).map((item) => `<span>${escapeHtml(item.label)} ${escapeHtml(numberText(item.current))}${escapeHtml(item.unit)}，上年同期 ${escapeHtml(numberText(item.prior))}${escapeHtml(item.unit)}。</span>`).join(' ');
  const bars = (review.comparison || []).map((item) => {
    const a = numeric(item.current), b = numeric(item.prior), max = Math.max(a || 0,b || 0);
    const permitted = a !== null && b !== null && a >= 0 && b >= 0 && max > 0;
    return `<div class="bar-row"><div class="bar-title"><span>${escapeHtml(item.label)}</span><span>${escapeHtml(numberText(item.current))} / ${escapeHtml(numberText(item.prior))} ${escapeHtml(item.unit)}</span></div>${permitted ? `<div class="bar-track"><div class="bar-fill" style="width:${(a/max*100).toFixed(3)}%"></div></div><div class="bar-track"><div class="bar-fill prior" style="width:${(b/max*100).toFixed(3)}%"></div></div>` : '<p class="bar-warning">按原始数值展示，不使用比例条。</p>'}</div>`;
  }).join('');
  const evidence = (review.evidence || []).map((item) => `<button class="evidence-button" type="button" data-evidence-job="${escapeHtml(job.id)}" data-evidence-page="${escapeHtml(item.page)}"><span>物理页 ${escapeHtml(item.page)}</span><span aria-hidden="true">↗</span></button>`).join('');
  const pdfUrl = localUrl(review.pdf_url) || artifact(job.id,'pdf');
  return `<div class="review-kicker"><span class="eyebrow">${history || job.historical ? 'VERIFIED HISTORICAL REVIEW' : 'VERIFIED EARNINGS REVIEW'}</span><div class="badge-row">${badge('内部核验一致','sage')}${badge('外部核验一致','sage')}</div></div><div class="review-heading"><div><h2>${escapeHtml(review.short_name || job.short_name || job.company)} · 半年报复盘</h2><p>${escapeHtml(current)} · 合并报表 · ${escapeHtml(history || job.historical ? '原运行 ' + dateTime(job.created_unix) : '本次运行')} · 以下数值来自已封存结果</p></div><a class="text-link" href="${escapeHtml(pdfUrl)}" target="_blank" rel="noopener">打开原始 PDF ↗</a></div><div class="highlight-grid">${highlights}</div><div class="review-narrative">${(review.narrative || []).map((sentence) => `<p>${escapeHtml(sentence)}</p>`).join('')}${derived ? `<p>${derived}</p>` : ''}</div><section class="review-card"><div class="review-card-heading"><h3>核心财务数据</h3><span>保留原文证据 · 程序计算同比</span></div><div class="table-scroll" tabindex="0" aria-label="两期财务数据，可横向滚动"><table class="financial-table"><thead><tr><th>指标 / 单位</th><th>${escapeHtml(current)}</th><th>${escapeHtml(prior)}</th><th>同比</th><th>证据页</th></tr></thead><tbody>${rows}</tbody></table></div><p class="table-footnote">金额与每股收益分别保留各自单位；页面为原始 PDF 物理页。点击页码查看原始页图。同比依据原始数值计算，展示数值经过格式化。</p></section><div class="review-bottom-grid">${bars ? `<section class="review-card"><div class="review-card-heading"><h3>两期金额对照</h3></div><div class="comparison-bars"><div class="comparison-legend"><span>${escapeHtml(current)}</span><span>${escapeHtml(prior)}</span></div>${bars}<p class="bar-warning">每行按本指标两期最大值缩放，不用于跨指标比较。</p></div></section>` : ''}<section class="review-card"><div class="review-card-heading"><h3>回到原始证据</h3><span>${escapeHtml(integer((review.evidence || []).length))} 页</span></div><div class="evidence-content"><p>每一页均属于这次运行留存的 PDF。核对表头、单位和原始数字，也可以查看两层核验的完整记录。</p><div class="evidence-buttons">${evidence}</div></div></section></div><div class="review-seal"><span>结果封存 <code>${escapeHtml((review.seal_sha256 || '').slice(0,16))}</code> · PDF ${escapeHtml(job.pdf_sha256.slice(0,12))}</span><div class="review-seal-links"><a class="text-link" href="${escapeHtml(localUrl(review.internal_url) || artifact(job.id,'internal'))}" target="_blank" rel="noopener">内部核验 ↗</a><a class="text-link" href="${escapeHtml(localUrl(review.external_url) || artifact(job.id,'external'))}" target="_blank" rel="noopener">同花顺比对 ↗</a><a class="text-link" href="${escapeHtml(localUrl(review.trace_url) || artifact(job.id,'trace'))}" download>运行轨迹 ↓</a></div></div>${review.requires_human_review ? '<p class="human-review">已完成程序核验，仍需人工确认报表口径、表头及单位关联。数字一致不构成经营原因解释或投资判断。</p>' : ''}`;
}
function renderHistoryList() {
  const jobs = reportJobs();
  $('history-list-section').hidden = jobs.length < 2;
  $('history-list').innerHTML = jobs.map((job) => `<button type="button" class="history-item ${store.job?.id === job.id ? 'selected' : ''}" data-job-id="${escapeHtml(job.id)}"><span>${escapeHtml(dateTime(job.created_unix))}${job.historical ? ' · 历史留存' : ''}<small>${escapeHtml(modelName(job.text_model))} / ${escapeHtml(modelName(job.vision_model))} · ${escapeHtml(job.id)}</small></span>${badge(labels[job.status] || job.status,jobKind(job))}</button>`).join('');
}
function schedulePoll() {}
async function refreshState(initial = false) {
  const data = await api('/api/state');
  store.csrf = data.csrf_token; store.jobs = data.jobs || []; store.budget = data.budget || null; store.activeJobId = data.active_job_id;
  store.presets = data.presets || [];
  renderBudget();
  if (initial) {
    store.catalog = data.catalog;
    store.presetId = store.presets.find((p) => p.id === 'qwen27')?.id || store.presets[0]?.id || null;
    $('preset-select').innerHTML = store.presets.map((preset) => `<option value="${escapeHtml(preset.id)}">${escapeHtml(preset.label)}</option>`).join('');
    if (store.presetId) $('preset-select').value = store.presetId;
    renderCatalog();
    const defaultId = store.catalog.entries.some((entry) => entry.id === data.default_report_id) ? data.default_report_id : store.catalog.entries[0]?.id;
    if (defaultId) await selectReport(defaultId); else { clearJobDisplay(); renderSource(); }
  } else { renderHistoryList(); updateControls(); }
  if (data.credentials?.model === false || data.credentials?.reference === false) showNotice('global-notice','部分运行服务尚未就绪。可以查看已有记录；新运行可能无法完成。','warning');
}
function openEvidence(jobId,page) {
  const record = store.reviews.get(jobId);
  if (!record) return;
  const item = (record.review.evidence || []).find((evidence) => Number(evidence.page) === Number(page));
  const imageUrl = localUrl(item?.image_url) || artifact(jobId,`image-${Number(page)}`);
  const pdfBase = localUrl(item?.pdf_url) || localUrl(record.review.pdf_url) || artifact(jobId,'pdf');
  $('evidence-title').textContent = `原始证据 · 物理页 ${page}`;
  $('evidence-context').textContent = `${record.job.company} · ${record.review.current_period} · PDF ${record.job.pdf_sha256.slice(0,12)} · ${record.job.historical ? '历史运行' : '运行'} ${record.job.id}`;
  $('evidence-pdf').href = `${pdfBase.split('#')[0]}#page=${Number(page)}`;
  $('evidence-image-state').textContent = '正在读取原始页图…';
  const image = $('evidence-image'); image.removeAttribute('src'); image.alt = `${record.job.company} 原始 PDF 物理页 ${page}`;
  image.onload = () => { $('evidence-image-state').textContent = '原始 PDF 渲染页图'; };
  image.onerror = () => { $('evidence-image-state').textContent = '页图暂不可用，可以在 PDF 中打开该页。'; image.removeAttribute('src'); };
  image.src = imageUrl; $('evidence-dialog').showModal();
}
document.addEventListener('click',(event) => {
  const report = event.target.closest('[data-report-id]'); if (report) { selectReport(report.dataset.reportId); return; }
  const job = event.target.closest('[data-job-id]'); if (job) { selectJob(job.dataset.jobId); return; }
  const evidence = event.target.closest('[data-evidence-job]'); if (evidence) { openEvidence(evidence.dataset.evidenceJob,evidence.dataset.evidencePage); return; }
  const close = event.target.closest('[data-close]'); if (close) $(close.dataset.close).close();
});
$('preset-select').addEventListener('change',() => { store.presetId = $('preset-select').value; updateControls(); });
$('run-button').addEventListener('click',() => { window.location.href = '../#step-0'; });
for (const dialog of document.querySelectorAll('dialog')) dialog.addEventListener('click',(event) => { if (event.target === dialog) dialog.close(); });
refreshState(true).catch((error) => showNotice('global-notice',`暂时无法读取公开示例。${error.message}`,'error'));
