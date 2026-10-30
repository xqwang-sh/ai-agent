"""Render the event workbench from an already published business result."""
from datetime import datetime
from html import escape
import json
from zoneinfo import ZoneInfo

TZ = ZoneInfo("Asia/Shanghai")
PERIODS = {"H1": "半年度", "Q1": "第一季度", "Q3": "第三季度", "FY": "年度"}
FIELDS = {"meeting_date": "会议日期", "start_time": "开始时间", "end_time": "结束时间", "question_deadline_date": "提问截止日期", "question_deadline_time": "提问截止时刻"}
STATUS = {"complete": "检查完成", "needs_review": "有信息待复核", "incomplete": "本轮检查不完整", "failed": "检查失败"}

CSS = """
:root{--cream:#eff0e4;--paper:#fafaf2;--ink:#202328;--muted:#71756c;--line:#d8d9cd;--blue:#7899c4;--coral:#bb5b4e;--sage:#668f6c;font-family:-apple-system,BlinkMacSystemFont,'PingFang SC','Microsoft YaHei',sans-serif;color:var(--ink);background:var(--cream)}*{box-sizing:border-box}body{margin:0;font-size:14px;line-height:1.8}button,input,a,summary{font:inherit;outline-offset:4px}a{color:#4c719b;text-underline-offset:3px}button{cursor:pointer}h1,h2,h3,p{margin:0}h1{font:500 34px/1.35 Georgia,'Songti SC',serif}h2{font-size:20px}h3{font-size:16px}button{color:inherit}main{max-width:1220px;margin:auto;padding:35px 30px 55px}.topbar{display:flex;justify-content:space-between;align-items:center;gap:20px;border-bottom:1px solid var(--line);padding-bottom:24px}.brandline{font-size:11px;letter-spacing:1.6px;color:var(--muted);margin-bottom:10px}.subtitle{color:var(--muted);margin-top:10px;font-size:13px}.pill{display:inline-block;border-radius:30px;padding:6px 12px;font-size:12px;white-space:nowrap;background:#e0e9db;color:#4f7250}.pill.review{background:#eee0d6;color:#98604f}.top-actions{display:flex;align-items:center;gap:15px;flex-wrap:wrap;font-size:12px}.sample-note{padding:10px 14px;margin-top:18px;background:#e2e9ed;color:#56708b;border-radius:6px;font-size:12px}.metrics{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:14px;margin:24px 0}.metric{background:var(--paper);padding:17px 20px;border:1px solid var(--line);border-radius:9px}.metric span{display:block;color:var(--muted);font-size:12px}.metric strong{font:500 35px/1.45 Georgia,serif}.metric small{color:var(--muted);font-size:11px;margin-left:9px}.main-tabs{display:flex;gap:22px;border-bottom:1px solid var(--line);margin-bottom:23px}.main-tabs button{border:0;border-bottom:3px solid transparent;padding:10px 0;background:transparent;color:var(--muted);font-size:14px}.main-tabs button[aria-selected=true]{border-color:var(--sage);color:var(--ink);font-weight:600}.panel[hidden],.event-card[hidden]{display:none!important}.workspace{display:grid;grid-template-columns:minmax(0,1fr) 285px;gap:22px}.toolbar{display:flex;flex-wrap:wrap;justify-content:space-between;gap:12px;margin-bottom:15px}.filter-group{display:flex;flex-wrap:wrap;gap:6px}.filter-group button{padding:6px 10px;background:transparent;border:1px solid var(--line);border-radius:6px;font-size:11px}.filter-group button[aria-pressed=true]{background:var(--ink);color:var(--paper);border-color:var(--ink)}input[type=search]{width:220px;max-width:100%;padding:7px 11px;border:1px solid var(--line);border-radius:6px;background:var(--paper);font-size:12px}.event-list{display:grid;gap:13px}.event-card{background:var(--paper);border:1px solid var(--line);border-radius:9px;padding:19px 21px}.event-head{display:flex;justify-content:space-between;gap:15px;align-items:start}.event-meta{font-size:11px;color:var(--muted);margin-top:3px}.event-head .pill{font-size:10px;padding:4px 9px}.meeting{font:500 25px/1.45 Georgia,'Songti SC',serif;margin:13px 0 5px}.meeting small{font:13px -apple-system,BlinkMacSystemFont,'PingFang SC',sans-serif;color:#58634f;margin-left:10px}.deadline{font-size:12px;color:#666e60}.deadline.pending{color:#9a6656}.event-links{display:flex;gap:14px;flex-wrap:wrap;margin-top:13px;font-size:11px}.event-links a{text-decoration:none}.event-card summary{font-size:11px;color:#697d91;cursor:pointer;margin-top:12px}.evidence-body{border-top:1px solid var(--line);margin-top:12px;padding-top:13px;font-size:12px}.source{margin:12px 0}.source a{font-size:12px}.source small{color:var(--muted)}blockquote{margin:8px 0;padding:9px 13px;border-left:3px solid #b9cbb0;background:#f0f2e7;font-size:11px;white-space:pre-wrap;overflow-wrap:anywhere}.side-card{background:#e5e7db;border:1px solid #d1d7c7;border-radius:9px;padding:19px;margin-bottom:15px}.side-card h3{font-size:13px;margin-bottom:10px}.side-card p{font-size:12px;color:#68705f;margin:8px 0}.side-card ul{font-size:11px;color:#6d7468;padding-left:17px;margin-bottom:0}.side-card.warning{background:#eee5dd;border-color:#ddc9bd}.side-card.warning h3{color:#98604f}.small{font-size:11px;color:var(--muted)}.countline{font-size:11px;color:var(--muted);margin-top:12px}.empty{padding:35px;text-align:center;color:var(--muted);background:var(--paper);border:1px dashed var(--line);border-radius:8px}.review-card,.run-card{padding:22px;background:var(--paper);border:1px solid var(--line);border-radius:9px;margin-bottom:16px}.review-card h3,.run-card h3{margin-bottom:10px}.compare{display:grid;grid-template-columns:1fr 1fr;gap:15px;margin:16px 0}.compare>div{background:#eff0e4;padding:13px;border-radius:6px}.compare span{display:block;font-size:11px;color:var(--muted)}.compare strong{font-size:18px;font-weight:500}.table-scroll{overflow:auto}table{width:100%;border-collapse:collapse;font-size:12px}th,td{text-align:left;vertical-align:top;padding:11px;border-bottom:1px solid var(--line)}th{font-weight:500;background:#e2e9ed}.run-grid{display:grid;grid-template-columns:1fr 1fr;gap:18px}.detail-list{display:grid;grid-template-columns:120px 1fr;font-size:12px;gap:9px;margin:0}.detail-list dt{color:var(--muted)}.detail-list dd{margin:0;overflow-wrap:anywhere}.source-list{display:grid;gap:13px}.notice-row{padding:14px 0;border-bottom:1px solid var(--line)}.notice-row a{display:block}.notice-row small{color:var(--muted);font-size:11px}footer{margin-top:32px;padding-top:16px;border-top:1px solid var(--line);font-size:11px;color:var(--muted)}@media(max-width:900px){.workspace{grid-template-columns:1fr}.aside{display:grid;grid-template-columns:1fr 1fr;gap:15px}.side-card{margin:0}.run-grid{grid-template-columns:1fr}}@media(max-width:600px){main{padding:22px 16px 35px}.topbar{align-items:start;flex-direction:column;gap:12px}h1{font-size:28px}.metrics{grid-template-columns:1fr 1fr;gap:9px;margin:18px 0}.metric{padding:12px 14px}.metric strong{font-size:29px}.metric small{display:block;margin:0}.main-tabs{gap:19px}.main-tabs button{font-size:12px}.event-card{padding:16px}.meeting{font-size:22px}.meeting small{display:block;margin:4px 0}.toolbar{display:block}input[type=search]{width:100%;margin-top:11px}.aside{grid-template-columns:1fr}.compare{grid-template-columns:1fr}.detail-list{grid-template-columns:100px 1fr}.event-head h3{font-size:15px}.review-card,.run-card{padding:17px}table{min-width:540px}.sample-note{font-size:11px}}@media print{.main-tabs,.toolbar,.top-actions{display:none}.panel[hidden]{display:block!important}.workspace{display:block}main{padding:0}.event-card{break-inside:avoid}}
"""

JS = """
const tabs=[...document.querySelectorAll('[data-panel]')];
tabs.forEach(button=>button.addEventListener('click',()=>{tabs.forEach(b=>b.setAttribute('aria-selected',String(b===button)));document.querySelectorAll('.panel').forEach(p=>p.hidden=p.id!==button.dataset.panel);}));
let phase='all';const search=document.getElementById('event-search');const cards=[...document.querySelectorAll('.event-card')];
function applyFilters(){const query=search.value.trim().toLowerCase();let visible=0;cards.forEach(card=>{const match=(!query||card.dataset.search.includes(query))&&(phase==='all'||(phase==='review'?card.dataset.review==='true':card.dataset.phase===phase));card.hidden=!match;visible+=match?1:0;});document.getElementById('visible-count').textContent=visible;document.getElementById('no-results').hidden=visible!==0;}
document.querySelectorAll('[data-filter]').forEach(button=>button.addEventListener('click',()=>{phase=button.dataset.filter;document.querySelectorAll('[data-filter]').forEach(b=>b.setAttribute('aria-pressed',String(b===button)));applyFilters();}));search.addEventListener('input',applyFilters);applyFilters();
"""


def period_label(value):
    year, _, period = (value or "").partition("-")
    return year + "年" + PERIODS.get(period, period) if year else "报告期待确认"


def time_label(event):
    day = event.get("meeting_date")
    if not day:
        return "日期待确认"
    start, end = event.get("start_time"), event.get("end_time")
    return day + (" · " + (start or "未注明") + " 至 " + (end or "未注明") if start or end else " · 时刻未注明")


def source_link(record, label=None):
    url = record.get("pdf_url") or record.get("url") or ""
    if not url.startswith(("https://", "http://")):
        return escape(label or record.get("title") or "来源暂不可打开")
    return '<a href="' + escape(url, quote=True) + '" target="_blank" rel="noopener">' + escape(label or record.get("title") or "原公告") + " ↗</a>"


def render_product(state, summary, *, frozen=False, back_url=None):
    now = datetime.fromisoformat(summary["as_of"])
    notices = state.get("notices", {})
    events = list(state.get("events", {}).values())

    def phase(event):
        if event.get("status") in {"cancelled", "postponed"} or not event.get("meeting_date") or event.get("validity") == "needs_review" or {"meeting_date", "start_time", "end_time"}.intersection(event.get("pending_fields", {})):
            return "other"
        at = datetime.fromisoformat(event["meeting_date"] + "T" + (event.get("end_time") or event.get("start_time") or "23:59")).replace(tzinfo=TZ)
        return "past" if at <= now else "future"

    def pending(event):
        return bool(event.get("pending_fields") or event.get("validity") == "needs_review")

    future = sum(phase(e) == "future" for e in events)
    reviews = sum(pending(e) for e in events)
    past = sum(phase(e) == "past" for e in events)
    ordered = sorted(events, key=lambda e: (phase(e) != "future", not pending(e), e.get("meeting_date") or "9999", e["id"]))
    cards, review_cards = [], []
    for event in ordered:
        kind = phase(event)
        needs_review = pending(event)
        label = "即将举行" if kind == "future" else "日期已过" if kind == "past" else "安排待定"
        if event.get("status") == "cancelled":
            label = "已取消"
        if event.get("status") == "postponed":
            label = "延期，待定新日期"
        sources = [notices[i] for i in event.get("source_ids", []) if i in notices]
        evidence = []
        for source in sources:
            value = source.get("extraction", {})
            excerpts = []
            for key, title in [("meeting_evidence", "会议时间"), ("deadline_evidence", "提问截止"), ("relation_evidence", "变更关联")]:
                quote = value.get(key)
                if quote:
                    excerpts.append('<p class="small">' + title + " · PDF第" + str(quote["page"]) + "页</p><blockquote>" + escape(quote["quote"]) + "</blockquote>")
            evidence.append('<div class="source">' + source_link(source) + '<br><small>' + escape(source.get("publication_date", "")) + " · 公告" + escape(value.get("notice_number") or source["id"]) + "</small>" + "".join(excerpts) + "</div>")
        history = []
        for item in event.get("history", []):
            before, after = item["before"], item["after"]
            history.append('<p class="small">' + escape(item.get("publication_date") or "") + " · 会议安排从 " + escape(time_label(before)) + " 更新为 " + escape(time_label(after)) + "；沿用同一事件。</p>")
        deadline = " ".join(filter(None, [event.get("question_deadline_date"), event.get("question_deadline_time")])) or "公告未注明"
        deadline_text = "提问截止存在冲突，先查看待复核项" if needs_review and event.get("pending_fields") else "提问截止 · " + deadline
        join = event.get("participation_url") or ""
        join_link = '<a href="' + escape(join, quote=True) + '" target="_blank" rel="noopener">参与入口 ↗</a>' if join.startswith(("https://", "http://")) else ""
        search = " ".join([event.get("company", ""), event.get("stock_code", ""), period_label(event.get("report_period"))]).lower()
        card = '<article class="event-card" data-phase="' + kind + '" data-review="' + str(needs_review).lower() + '" data-search="' + escape(search, quote=True) + '"><div class="event-head"><div><h3>' + escape(event.get("company", "") + " · " + period_label(event.get("report_period"))) + '</h3><p class="event-meta">' + escape(event.get("stock_code", "")) + " · " + str(len(sources)) + '份来源 · 业绩说明会</p></div><span class="pill' + (" review" if needs_review else "") + '">' + ("待复核" if needs_review else label) + '</span></div><p class="meeting">' + escape(time_label(event)) + '<small>北京时间</small></p><p class="deadline' + (" pending" if needs_review else "") + '">' + escape(deadline_text) + '</p><div class="event-links">' + join_link + (source_link(sources[-1], "打开最新公告") if sources else "") + '</div><details><summary>查看来源、页码与变更记录</summary><div class="evidence-body">' + "".join(history + evidence) + "</div></details></article>"
        cards.append(card)
        for field, candidates in event.get("pending_fields", {}).items():
            for candidate in candidates:
                quote = candidate.get("evidence") or {}
                original = next((source for source in sources if source.get("extraction", {}).get("notice_kind") == "initial"), {})
                review_cards.append('<article class="review-card"><span class="pill review">需要业务方判断</span><h3>' + escape(event.get("company", "") + " · " + period_label(event.get("report_period"))) + "</h3><p>" + escape(FIELDS.get(field, field)) + '在新旧公告中不同，变更公告同时表述其他内容不变。</p><div class="compare"><div><span>原通知保留值</span><strong>' + escape(str(candidate.get("old") or "未注明")) + '</strong></div><div><span>变更公告的新候选</span><strong>' + escape(str(candidate.get("candidate") or "未注明")) + '</strong></div></div><p class="small">原值与新候选均保留。此字段尚未确认，不能把自动更新当成已经核定。</p><blockquote>' + escape(quote.get("quote") or "请打开原公告复核") + '</blockquote><p class="small">PDF第' + str(quote.get("page") or "待确认") + "页 · " + source_link(original, "打开原通知") + " · " + source_link(notices.get(candidate.get("source_id"), {}), "打开变更公告") + "</p></article>")
    history_cards = []
    for event in events:
        for item in event.get("history", []):
            history_cards.append('<article class="review-card"><span class="pill">已应用的明确变更</span><h3>' + escape(event.get("company", "") + " · " + period_label(event.get("report_period"))) + '</h3><div class="compare"><div><span>原安排</span><strong>' + escape(time_label(item["before"])) + '</strong></div><div><span>变更后</span><strong>' + escape(time_label(item["after"])) + '</strong></div></div><p class="small">同一事件保留' + str(len(event.get("source_ids", []))) + "份来源，改期未新建一场会议。</p></article>")
    coverage_rows = []
    for code, info in summary.get("coverage", {}).items():
        company = next((e.get("company", code) for e in events if e.get("stock_code") == code), code)
        complete = info.get("query_complete") and info.get("processing_complete")
        coverage_rows.append("<tr><td>" + escape(company + " " + code) + "</td><td>" + ("查询及处理完成" if complete else "检查不完整") + "</td><td>" + str(info.get("announcement_count", 0)) + "份</td><td>" + escape((info.get("query", {}).get("start_date") or "") + " 至 " + (info.get("query", {}).get("end_date") or "")) + "</td></tr>")
    notice_rows = ['<div class="notice-row">' + source_link(n) + "<small>" + escape(n.get("company", "") + " · " + n.get("publication_date", "")) + " · ID " + escape(n["id"]) + " · " + escape(n.get("model") or "模型未记录") + "</small></div>" for n in sorted(notices.values(), key=lambda n: (n.get("publication_date", ""), n["id"]), reverse=True)]
    total_issues = len(summary.get("issues", []))
    cached = len(summary.get("cached_notice_ids", []))
    usage = summary.get("usage", {})
    unknown = usage.get("calls_with_unknown_usage", 0)
    token_text = str(usage.get("known_total_tokens", 0)) + ("，另有" + str(unknown) + "次未知" if unknown else "")
    back = '<a href="' + escape(back_url, quote=True) + '">返回讲义</a>' if back_url else ""
    note = '<div class="sample-note">展示版 · 数据取自' + escape(summary["as_of"][:10]) + '真实运行。本页可筛选和核对来源，不在线执行后台任务。</div>' if frozen else ""
    empty = '<div class="empty">本轮没有可展示的会议。先检查来源覆盖，空列表不能代替查询成功。</div>'
    review_empty = '<div class="review-card">本轮没有记录待复核字段。仍请核对下方来源与覆盖状态。</div>'
    change_empty = '<div class="review-card">当前账本未记录已经应用的变更。</div>'
    data = json.dumps(summary, ensure_ascii=False, indent=2)
    raw_summary = '<details><summary>查看本轮结构化记录</summary><pre style="white-space:pre-wrap;overflow-wrap:anywhere;font-size:11px">' + escape(data) + "</pre></details>"
    html = '<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>公告事件智能体 · 投研事件工作台</title><style>' + CSS + '</style></head><body><main><header class="topbar"><div><p class="brandline">第三讲 · 投研事件工作台</p><h1>公告事件智能体</h1><p class="subtitle">巨潮资讯 · 业绩说明会通知及变更 · 北京时间</p></div><div class="top-actions"><span class="pill' + (' review' if summary.get("status") != "complete" else '') + '">' + escape(STATUS.get(summary.get("status"), "检查状态待确认")) + '</span>' + back + '</div></header>' + note
    html += '<div class="metrics"><div class="metric"><span>会议事件</span><strong>' + str(len(events)) + '</strong><small>同一场会合并维护</small></div><div class="metric"><span>即将举行</span><strong>' + str(future) + '</strong><small>按本轮时点判断</small></div><div class="metric"><span>待复核事件</span><strong>' + str(reviews) + '</strong><small>原值与候选均保留</small></div><div class="metric"><span>来源公告</span><strong>' + str(len(notices)) + '</strong><small>可打开原始PDF</small></div></div>'
    html += '<nav class="main-tabs" aria-label="产品视图" role="tablist"><button type="button" role="tab" aria-selected="true" data-panel="events-panel">会议安排</button><button type="button" role="tab" aria-selected="false" data-panel="review-panel">变更与待复核</button><button type="button" role="tab" aria-selected="false" data-panel="run-panel">运行与来源</button></nav>'
    filters = ''.join('<button type="button" aria-pressed="' + str(key == "all").lower() + '" data-filter="' + key + '">' + title + ' ' + str(count) + '</button>' for key, title, count in [("all", "全部", len(events)), ("future", "即将举行", future), ("review", "待复核", reviews), ("past", "日期已过", past)])
    html += '<section class="panel" id="events-panel"><div class="workspace"><div><div class="toolbar"><div class="filter-group" aria-label="筛选会议">' + filters + '</div><input type="search" id="event-search" placeholder="搜索公司、代码或报告期" aria-label="搜索公司、代码或报告期"></div><div class="event-list">' + (''.join(cards) or empty) + '</div><p id="no-results" class="empty" hidden>没有匹配的事件，可调整筛选或搜索。</p><p class="countline">当前显示 <span id="visible-count">' + str(len(events)) + '</span> 场会议。日期已过不代表已经确认召开。</p></div><aside class="aside"><div class="side-card"><h3>这次检查做了什么</h3><p>本轮时间 · ' + escape(summary["as_of"].replace("T", " ")[:19]) + '</p><p>本轮实际模型调用 ' + str(summary.get("model_calls", 0)) + ' 次，复用 ' + str(cached) + ' 份经重新核验的提取。</p><p>上方会议信息来自原PDF，运行记录与来源可以在另一个视图检查。</p></div><div class="side-card warning"><h3>有疑问的信息先保留</h3><p>当前有' + str(total_issues) + '项运行或业务待办。改期需要关联原通知；矛盾字段不直接当成已确认信息。</p><ul><li>原公告及页码可逐项打开</li><li>新旧时间和变更依据均保留</li><li>失败不等于没有新增公告</li></ul></div></aside></div></section>'
    html += '<section class="panel" id="review-panel" hidden><h2>待判断的字段</h2><p class="small" style="margin:8px 0 18px">先对照原文，再决定最终采用哪一个值。</p>' + (''.join(review_cards) or review_empty) + '<h2 style="margin:27px 0 17px">已经应用的明确变更</h2>' + (''.join(history_cards) or change_empty) + '</section>'
    html += '<section class="panel" id="run-panel" hidden><div class="run-grid"><article class="run-card"><h3>本轮运行记录</h3><dl class="detail-list"><dt>运行编号</dt><dd>' + escape(summary.get("run_id", "未记录")) + '</dd><dt>业务状态</dt><dd>' + escape(STATUS.get(summary.get("status"), "待确认")) + '</dd><dt>启动方式</dt><dd>' + ("系统定时触发" if summary.get("trigger") == "scheduler" else "手动触发") + '</dd><dt>已报告token</dt><dd>' + escape(token_text) + '</dd><dt>模型调用与复用</dt><dd>' + str(summary.get("model_calls", 0)) + '次调用 · ' + str(cached) + '份提取复用</dd></dl><p class="small" style="margin-top:15px">此处统计本轮实际用量，未把历史模型调用混入本轮。</p></article><article class="run-card"><h3>来源覆盖</h3><div class="table-scroll"><table><thead><tr><th>公司</th><th>检查结果</th><th>本轮查询</th><th>日期窗口</th></tr></thead><tbody>' + ''.join(coverage_rows) + '</tbody></table></div><p class="small" style="margin-top:13px">覆盖限定公司、关键词与日期窗口，不代表全部披露都已召回。</p></article></div><article class="run-card"><h3>保留的原始公告</h3><div class="source-list">' + ''.join(notice_rows) + '</div></article><article class="run-card">' + raw_summary + '</article></section>'
    return html + '<footer>会议与提问截止按北京时间解释。系统任务负责后台检查，工作台负责展示本轮结果、变更和证据。</footer></main><script>' + JS + '</script></body></html>'
