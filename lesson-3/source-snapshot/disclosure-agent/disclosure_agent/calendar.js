'use strict';
const data = JSON.parse(document.getElementById('calendar-data').textContent);
const byId = new Map(data.events.map(event => [event.id, event]));
const $ = id => document.getElementById(id);
const esc = value => String(value ?? '').replace(/[&<>"']/g, char => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[char]));
const validDay = day => /^\d{4}-\d{2}-\d{2}$/.test(day || '') && !Number.isNaN(Date.parse(day + 'T00:00:00+08:00'));
const dateKey = at => new Intl.DateTimeFormat('sv-SE', {timeZone:'Asia/Shanghai',year:'numeric',month:'2-digit',day:'2-digit'}).format(at);
const now = () => data.frozen ? new Date(data.as_of) : new Date();
const today = () => dateKey(now());
const dayLabel = day => validDay(day) ? `${Number(day.slice(5,7))}月${Number(day.slice(8))}日` : '日期待确认';
const fullDay = day => validDay(day) ? `${day.slice(0,4)}年${dayLabel(day)}` : '日期待确认';
const words = data.frozen ? '当日' : '今日';
let selectedDay = today(), month = selectedDay.slice(0,7), view = 'calendar';

function isReview(event) { return Object.keys(event.pending).length > 0 || event.validity === 'needs_review' || event.review_reasons.length > 0; }
function updatedToday(event) {
  const activity=event.activity;
  if (!activity.updated_at || dateKey(new Date(activity.updated_at)) !== today()) return false;
  if (activity.kind !== 'baseline') return activity.kind !== 'legacy';
  return event.sources.some(source => source.date === dateKey(new Date(activity.first_seen_at)));
}
function activityLabel(event) {
  const kind=event.activity.kind, prefix=updatedToday(event) ? words : '';
  if (kind==='extraction_revision') return prefix + '提取校正';
  if (kind==='review') return prefix + '复核更新';
  if (kind==='updated') return prefix + '安排更新';
  if (kind==='new' || updatedToday(event)) return prefix + '收录';
  return '历史建档';
}
function tags(event) {
  let html=`<span class="tag${updatedToday(event)?' fresh':''}">${esc(activityLabel(event))}</span>`;
  if (isReview(event)) html+='<span class="tag review">有字段待复核</span>';
  if (event.status==='cancelled') html+='<span class="tag cancelled">已取消</span>';
  else if (event.status==='postponed') html+='<span class="tag review">延期，日期待定</span>';
  else if (validDay(event.meeting_date) && event.meeting_date<today()) html+='<span class="tag">日期已过</span>';
  else if (event.end_time && new Date(event.meeting_date+'T'+event.end_time+':00+08:00')<now()) html+='<span class="tag">时段已过</span>';
  return html;
}
function filteredEvents() {
  const company=$('company-filter').value, query=$('event-search').value.trim().toLowerCase();
  return data.events.filter(event => (!company || event.stock_code===company) && (!query || `${event.company} ${event.stock_code} ${event.period} ${event.report_period}`.toLowerCase().includes(query)));
}
function entries(events) {
  return events.flatMap(event => {
    if (event.status!=='scheduled') return [];
    const rows=[];
    if (validDay(event.meeting_date)) rows.push({day:event.meeting_date,kind:'meeting',event,time:event.start_time || '时刻未注明',review:isReview(event)||event.reminder_blocked});
    if (validDay(event.question_deadline_date) && !Object.keys(event.pending).some(field=>field.startsWith('question_deadline')) && event.validity!=='needs_review') {
      rows.push({day:event.question_deadline_date,kind:'deadline',event,time:event.question_deadline_time || '时刻未注明',review:false});
    }
    return rows;
  }).sort((a,b)=>(a.day+' '+a.time).localeCompare(b.day+' '+b.time));
}
function futureItems(events=data.events) {
  return events.flatMap(event=>event.reminders.map(item=>({...item,event}))).filter(item=>new Date(item.start)>now()).sort((a,b)=>new Date(a.start)-new Date(b.start));
}
function meetingText(event) {
  if (event.status==='cancelled') return '已取消，原安排不再有效';
  if (event.status==='postponed') return '已延期，等待新日期';
  return `${fullDay(event.meeting_date)} ${event.start_time || '时刻未注明'}${event.end_time?'–'+event.end_time:''}`;
}
function showView(next) {
  view=next;
  document.querySelectorAll('[data-view]').forEach(button=>button.setAttribute('aria-pressed',String(button.dataset.view===view)));
  $('calendar-view').hidden=view!=='calendar'; $('list-view').hidden=view==='calendar'; render();
}
function selectDay(day) { selectedDay=day; month=day.slice(0,7); showView('calendar'); }
function drawCalendar(events) {
  const all=entries(events), visible=all.filter(item=>item.day.startsWith(month));
  $('month-label').textContent=`${month.slice(0,4)}年${Number(month.slice(5))}月`;
  $('month-count').textContent=`${visible.filter(item=>item.kind==='meeting').length}场会议 · ${visible.filter(item=>item.kind==='deadline').length}项截止`;
  const first=new Date(month+'-01T00:00:00Z'), offset=(first.getUTCDay()+6)%7;
  first.setUTCDate(1-offset);
  let html='';
  for(let i=0;i<42;i++) {
    const at=new Date(first); at.setUTCDate(first.getUTCDate()+i); const day=at.toISOString().slice(0,10);
    const items=all.filter(item=>item.day===day), fresh=items.some(item=>updatedToday(item.event));
    const classes=['day',day.startsWith(month)?'':'outside',day===selectedDay?'selected':'',day===today()?'today':'',items.some(item=>item.kind==='meeting')?'has-meeting':items.some(item=>item.kind==='deadline')?'has-deadline':'',fresh?'is-fresh':'',items.some(item=>item.review)?'has-review':''].filter(Boolean).join(' ');
    const label=`${fullDay(day)}，${items.length?items.map(item=>`${item.event.company}${item.kind==='meeting'?'会议':item.event.deadline_label}`).join('，'):'暂无安排'}${fresh?'，'+words+'收录或更新':''}`;
    html+=`<button class="${classes}" data-day="${day}" aria-label="${esc(label)}" aria-pressed="${day===selectedDay}"><span class="day-top"><span class="day-number">${Number(day.slice(8))}</span>${fresh?'<i class="fresh-dot" aria-hidden="true"></i>':''}</span>${items.slice(0,2).map(item=>`<span class="calendar-chip ${item.kind==='deadline'?'deadline':updatedToday(item.event)?'fresh':''} ${item.review?'review':''}">${esc(item.event.company)}${item.kind==='deadline'?' · '+esc(item.event.deadline_label):''}</span>`).join('')}${items.length>2?`<span class="more-events">另${items.length-2}项</span>`:''}</button>`;
  }
  $('month-grid').innerHTML=html;
  $('selected-date').textContent=dayLabel(selectedDay)+' · '+['日','一','二','三','四','五','六'][new Date(selectedDay+'T00:00:00Z').getUTCDay()];
  const selected=all.filter(item=>item.day===selectedDay);
  $('day-events').innerHTML=selected.length?selected.map(item=>`<button class="event-button" data-open="${esc(item.event.id)}"><strong>${esc(item.event.company)} <span class="small">${esc(item.event.stock_code)}</span></strong><span class="period">${esc(item.event.period)}业绩说明会</span><span class="when">${esc(item.time)}${item.kind==='meeting'&&item.event.end_time?'–'+esc(item.event.end_time):''}</span><span class="entry-kind">${item.kind==='deadline'?esc(item.event.deadline_label):'会议安排'}</span><div>${tags(item.event)}</div><span class="open-detail">查看摘要与参与方式 ↗</span></button>`).join(''):'<p class="empty">这一天暂无匹配的会议或截止安排。可选择其他标记日期，或跳到下次会议。</p>';
  $('next-meeting').disabled=!futureItems(events).some(item=>item.kind==='meeting');
}
function drawList(events) {
  const config={updates:[`${words}收录与更新`,'首次回看的旧公告标为历史建档；模型提取校正单独标明，不当作公司新改期。'],all:['全部事件','未来与历史安排都保留。改期沿用同一事件，取消或待定安排仍可回看原公告。'],review:['需要复核的事件','先核对原值、候选和公告原文。冲突字段不生成提醒，明确的其他字段仍可使用。']};
  $('list-title').textContent=(config[view]||config.all)[0]; $('list-description').textContent=(config[view]||config.all)[1];
  const rows=events.filter(event=>view==='updates'?updatedToday(event):view==='review'?isReview(event):true).sort((a,b)=>String(b.meeting_date||'').localeCompare(a.meeting_date||''));
  $('event-list').innerHTML=rows.length?rows.map(event=>`<button class="record-card" data-open="${esc(event.id)}"><h3>${esc(event.company)} <span class="small">${esc(event.stock_code)}</span></h3><p>${esc(event.period)}业绩说明会</p><p class="record-date">${esc(meetingText(event))}</p><p>${esc(event.deadline_label)} · ${event.pending.question_deadline_date||event.pending.question_deadline_time?'有冲突，需复核':`${esc(event.question_deadline_date||'未注明')} ${esc(event.question_deadline_time||'')}`}</p>${tags(event)}<p class="muted">查看摘要、参与入口与${event.sources.length}份原公告 ↗</p></button>`).join(''):'<p class="empty">当前没有匹配的事件。可以调整公司或搜索条件。</p>';
}
function render() {
  $('freshness-note').textContent=data.frozen?`展示数据冻结于 ${data.as_of.slice(0,10)} ${data.as_of.slice(11,16)}。当日颜色以该业务日期判断，可翻月回看；不是当前实时结果。`:`后台最近检查 ${data.as_of.slice(0,10)} ${data.as_of.slice(11,16)}。${data.as_of.slice(0,10)!==today()?'数据尚未更新到今天，请检查后台任务。':'收录和变更分别记录，重复查询不刷新事件日期。'}打开或刷新页面可查看最近生成的结果。`;
  const events=filteredEvents(), updates=data.events.filter(updatedToday).length, reviews=data.events.filter(isReview).length;
  $('updates-tab').textContent=`${words}更新 ${updates}`; $('review-tab').textContent=`待复核 ${reviews}`;
  $('go-today').textContent=data.frozen?'示例当天':'今天';
  $('fresh-legend').innerHTML=`<i class="key fresh"></i>${words}收录/更新`;
  drawCalendar(events); if(view!=='calendar') drawList(events);
}
function openEvent(id) {
  const event=byId.get(id); if(!event)return;
  const pendingDeadline=event.pending.question_deadline_date || event.pending.question_deadline_time;
  const latest=event.sources.at(-1), future=futureItems([event]);
  let summary=event.status==='scheduled'?`${event.company}拟于${meetingText(event)}举行${event.period}业绩说明会。`: `${event.company}${event.period}业绩说明会${event.status==='cancelled'?'已取消':'延期，等待新安排'}。`;
  if (event.validity==='needs_review' || Object.keys(event.pending).some(field=>['meeting_date','start_time','end_time'].includes(field))) summary='会议时间尚待核验。以下保留当前候选与来源，确认前不生成参会提醒。';
  const deadline=pendingDeadline?'存在冲突，暂不采用为确定截止时间':`${event.question_deadline_date||'公告未注明'} ${event.question_deadline_time||''}`;
  const reasons={source_hash_changed:'同一公告的原文件指纹发生变化，需核验新旧版本。',ambiguous_or_missing_original_notice:'发现尚未可靠关联的变更公告，旧安排暂不生成提醒。',report_period_conflict:'变更公告的报告期与原事件不一致，需核对关联。',incomplete_initial_event:'同公司有不完整通知，需补齐并确认是否影响现有安排。',company_coverage_incomplete:'本轮公司查询或处理不完整，保留旧安排，暂不新增提醒。'};
  const reviewWarning=event.review_reasons.filter(reason=>reasons[reason]).map(reason=>`<p class="detail-warning">${esc(reasons[reason])}</p>`).join('');
  const pending=Object.entries(event.pending).map(([field,values])=>values.map(value=>{
    return `<div class="detail-warning"><strong>${field.startsWith('question_deadline')?esc(event.deadline_label):'事件字段'}待复核</strong><p>新旧公告表述有冲突，当前不生成该字段提醒。</p><div class="compare"><div><span>原通知保留值</span><strong>${esc(value.old||'未注明')}</strong></div><div><span>变更公告候选</span><strong>${esc(value.candidate||'未注明')}</strong></div></div><blockquote>${esc(value.evidence?.quote||'请核对原公告')}</blockquote><p class="small">PDF第${esc(value.evidence?.page||'?')}页 · 请在下方“公告原文”核对原通知与变更公告。</p></div>`;
  }).join('')).join('');
  const history=event.history.map(item=>`<div class="history-item"><span>${esc(item.publication_date||'')} · 已应用的明确变更</span><p>${esc(item.before.meeting_date||'日期待定')} ${esc(item.before.start_time||'')} → ${esc(item.after.meeting_date||'日期待定')} ${esc(item.after.start_time||'')}</p></div>`).join('');
  const sources=[...new Map(event.sources.filter(source=>source.url).map(source=>[source.url,source])).values()].map(source=>`<a class="original-link" href="${esc(source.url)}" target="_blank" rel="noopener">${esc(source.title)} ↗</a>`).join('') || '<p class="small muted">原公告链接暂不可用。</p>';
  const participation=event.participation_url?`<a href="${esc(event.participation_url)}" target="_blank" rel="noopener">打开公告提供的参与入口 ↗</a>`:'公告未提取到可确认的参与网址，请查阅原公告。';
  const meetingQuote=event.sources.flatMap(source=>source.evidence).filter(quote=>quote.label==='会议时间').at(-1);
  let participationQuote=meetingQuote && /电话|直播|网络互动/.test(meetingQuote.quote)?`<blockquote>${esc(meetingQuote.quote)}</blockquote><p class="small">会议形式见上述原文。具体报名、登录与提问步骤请在公告中确认。</p>`:'<p class="small">通过公告提供的网址查看参与说明；网址本身不代表已完成报名。具体登录与提问步骤请核对原公告。</p>';
  const joining=latest?.participation || [];
  if(joining.length) participationQuote=`<p class="small">以下为公告中的参与说明，PDF第${esc(joining[0].page)}页。</p><blockquote>${esc(joining[0].quote.length>320?joining[0].quote.slice(0,320)+'…':joining[0].quote)}</blockquote><details><summary>展开完整参与步骤与页码</summary>${joining.map(quote=>`<p class="small">PDF第${esc(quote.page)}页</p><blockquote>${esc(quote.quote)}</blockquote>`).join('')}</details>`;
  const activity=event.activity, updated=activity.updated_at?`${activity.updated_at.slice(0,10)} ${activity.updated_at.slice(11,16)} · ${activityLabel(event)}`:'历史记录，原收录时间未记录';
  $('event-dialog-content').innerHTML=`<p class="eyebrow">业绩说明会 · 事件摘要</p><h2 id="event-dialog-title">${esc(event.company)}</h2><p class="detail-code">${esc(event.stock_code)} · ${esc(event.period)}</p><div>${tags(event)}</div><p class="detail-summary">${esc(summary)}</p><dl class="detail-fields"><dt>会议时间</dt><dd>${esc(meetingText(event))}<br><span class="small">北京时间</span></dd><dt>${esc(event.deadline_label)}</dt><dd>${esc(deadline)}</dd><dt>最新公告</dt><dd>${esc(latest?.date||'未记录')}</dd><dt>智能体更新</dt><dd>${esc(updated)}</dd></dl><div class="detail-actions">${future.length?`<button class="primary" data-download-event="${esc(id)}">添加到我的日历</button>`:'<span class="small muted">当前无可添加的未来提醒</span>'}</div>${future.length?'<p class="small muted reminder-note">导入个人日历后，默认提前1天、30分钟提醒。文件是当前快照，改期后需核对旧提醒。</p><p id="event-download-status" class="small" role="status"></p>':''}${reviewWarning}${event.reminder_blocked&&!reviewWarning?'<p class="detail-warning">会议时刻缺失、来源未完整核验或安排已失效，暂不生成会议提醒。</p>':''}<h3>如何参与</h3><p>${participation}</p>${participationQuote}${pending}${history?`<h3>安排变更</h3>${history}`:''}<h3>公告原文</h3><div class="original-links">${sources}</div>`;
  $('event-dialog').showModal();
}
function download(items, filename) {
  if(!items.length)return;
  const first=items[0].ics, header=first.slice(0,first.indexOf('BEGIN:VEVENT'));
  const content=header+items.flatMap(item=>item.ics.match(/BEGIN:VEVENT\r\n[\s\S]*?\r\nEND:VEVENT\r\n/g)||[]).join('')+'END:VCALENDAR\r\n';
  const url=URL.createObjectURL(new Blob([content],{type:'text/calendar;charset=utf-8'}));
  const link=document.createElement('a'); link.href=url;link.download=filename;document.body.append(link);link.click();link.remove();setTimeout(()=>URL.revokeObjectURL(url),1000);
  $('event-download-status').textContent=`已生成${items.length}项日程，请导入并核对提醒。`;
  const status=$('action-status');status.textContent='已生成日历文件。导入后核对时间；后续改期需检查旧提醒。';setTimeout(()=>status.textContent='',6000);
}
function drawDataStatus() {
  const status=data.status==='complete'?'检查完成':data.status==='needs_review'?'有字段待复核':'本轮检查不完整';
  $('data-status').textContent=`数据状态与原公告 · ${status} · ${data.source_count}份来源`;
  $('data-details-content').innerHTML=`<div class="data-columns"><div><h3>最近一次后台检查</h3><p>业务时间：${esc(data.as_of.replace('T',' ').slice(0,19))}</p><p>运行编号：${esc(data.run_id||'未记录')}</p><p>${data.trigger==='scheduler'?'系统定时启动':'手动启动'} · 本轮${data.model_calls}次模型调用，${data.cache_count}份提取复用</p><p>此处是后台检查时间，和每条事件的收录/更新时间分别记录。</p></div><div><h3>公司与来源覆盖</h3>${Object.entries(data.coverage).map(([code,coverage])=>`<p>${esc(code)} · ${coverage.query_complete&&coverage.processing_complete?'约定查询及处理完成':'检查不完整，保留旧结果'}<br><span class="small">${esc(coverage.query?.start_date||'')} 至 ${esc(coverage.query?.end_date||'')} · ${esc(coverage.announcement_count||0)}份候选</span></p>`).join('')}<p class="small">覆盖限定公司、关键词和日期窗口，不等于全部披露的完整召回。</p></div></div>${data.sources.map(source=>`<div class="source-line">${source.url?`<a href="${esc(source.url)}" target="_blank" rel="noopener">${esc(source.title)} ↗</a>`:esc(source.title)}<span>${esc(source.date)} · ID ${esc(source.id)}</span></div>`).join('')}`;
}

for(const event of [...new Map(data.events.map(event=>[event.stock_code,event])).values()]) {
  const option=document.createElement('option');option.value=event.stock_code;option.textContent=event.company; $('company-filter').append(option);
}
$('data-context').textContent=`跟踪${new Set(data.events.map(event=>event.stock_code)).size}家公司 · ${data.events.length}场会议 · ${data.source_count}份原公告`;

document.querySelectorAll('[data-view]').forEach(button=>button.addEventListener('click',()=>showView(button.dataset.view)));
$('event-search').addEventListener('input',render);$('company-filter').addEventListener('change',render);
for(const [id,delta] of [['previous-month',-1],['next-month',1]]) $(id).addEventListener('click',()=>{const day=new Date(month+'-01T00:00:00Z');day.setUTCMonth(day.getUTCMonth()+delta);month=day.toISOString().slice(0,7);selectedDay=entries(filteredEvents()).find(item=>item.day.startsWith(month))?.day || month+'-01';render();});
$('go-today').addEventListener('click',()=>selectDay(today()));
$('next-meeting').addEventListener('click',()=>{const next=futureItems(filteredEvents()).find(item=>item.kind==='meeting');if(next)selectDay(next.start.slice(0,10));});
$('month-grid').addEventListener('click',event=>{const button=event.target.closest('[data-day]');if(button)selectDay(button.dataset.day);});
document.addEventListener('click',event=>{
  const opener=event.target.closest('[data-open]');if(opener)openEvent(opener.dataset.open);
  const close=event.target.closest('[data-close]');if(close)close.closest('dialog').close();
  const exportButton=event.target.closest('[data-download-event]');if(exportButton)download(futureItems([byId.get(exportButton.dataset.downloadEvent)]),'announcement-'+exportButton.dataset.downloadEvent.replace(':','-')+'.ics');
});
document.querySelectorAll('dialog').forEach(dialog=>dialog.addEventListener('click',event=>{if(event.target===dialog){const rect=dialog.getBoundingClientRect();if(event.clientX<rect.left||event.clientX>rect.right||event.clientY<rect.top||event.clientY>rect.bottom)dialog.close();}}));
setInterval(()=>{if(!document.querySelector('dialog[open]'))render();},60000);
drawDataStatus();render();
