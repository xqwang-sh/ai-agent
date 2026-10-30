"""A self-contained calendar shared by live runs and the lesson."""
from datetime import datetime
from html import escape
import hashlib
import json
from pathlib import Path
import re

from pypdf import PdfReader

from .reminders import reminder_items, render_ics, safe_url
from .ledger import event_review_reasons

ROOT = Path(__file__).resolve().parent
PERIODS = {"H1": "半年度", "Q1": "第一季度", "Q2": "第二季度", "Q3": "第三季度", "Q4": "第四季度", "FY": "年度"}


def participation_excerpts(notice):
    """Quote the participation section by physical page, only from the bound PDF."""
    if "participation_evidence" in notice:
        return notice["participation_evidence"]
    path = notice.get("pdf_path")
    if not path:
        return []
    try:
        if hashlib.sha256(Path(path).read_bytes()).hexdigest() != notice.get("pdf_sha256"):
            return []
        result, started = [], False
        for page, source in enumerate(PdfReader(path).pages, 1):
            text = source.extract_text() or ""
            if not started:
                heading = re.search(r"投资者参[加与]方式", text)
                if not heading:
                    continue
                started = True
                text = text[heading.end():]
            end = re.search(r"(?m)^\s*[一二三四五六七八九十]+[、．.]\s*\S", text)
            quote = text[:end.start() if end else None].strip()
            if quote:
                result.append({"page": page, "quote": quote})
            if end:
                break
        return result
    except Exception:
        return []


def period_label(value):
    year, _, period = (value or "").partition("-")
    return year + "年" + PERIODS.get(period, period) if year else "报告期待确认"


def product_data(state, summary, *, frozen=False):
    notices = state.get("notices", {})
    events = []
    for event in state.get("events", {}).values():
        sources = []
        for identity in event.get("source_ids", []):
            notice = notices.get(identity)
            if not notice:
                continue
            extraction = notice.get("extraction", {})
            evidence = [{"label": label, **extraction[field]} for field, label in [
                ("meeting_evidence", "会议时间"), ("deadline_evidence", "提问/报名截止"),
                ("relation_evidence", "关联原通知")]
                if extraction.get(field)]
            sources.append({"id": identity, "title": notice.get("title", "原公告"),
                            "date": notice.get("publication_date", ""),
                            "url": safe_url(notice.get("pdf_url") or notice.get("url")),
                            "number": extraction.get("notice_number"), "evidence": evidence,
                            "participation": participation_excerpts(notice)})
        projected = {key: event.get(key) for key in ["id", "company", "stock_code", "report_period", "meeting_date",
                     "start_time", "end_time", "question_deadline_date", "question_deadline_time", "status", "validity"]}
        projected.update(period=period_label(event.get("report_period")),
                         participation_url=safe_url(event.get("participation_url")),
                         sources=sources, pending=event.get("pending_fields", {}), history=event.get("history", []),
                         activity=event.get("activity", {}),
                         review_reasons=sorted(set(event.get("review_reasons", []) + event_review_reasons(event, summary.get("issues", [])))))
        components = reminder_items(event, notices, summary.get("issues", []))
        projected["reminders"] = [{**item, "ics": render_ics([item], summary["as_of"])} for item in components]
        projected["reminder_blocked"] = not any(item["kind"] == "meeting" for item in components)
        events.append(projected)
    return {"as_of": summary["as_of"], "frozen": frozen, "run_id": summary.get("run_id"),
            "status": summary.get("status"), "trigger": summary.get("trigger"),
            "model_calls": summary.get("model_calls", 0), "cache_count": len(summary.get("cached_notice_ids", [])),
            "coverage": {code: {"query_complete": value.get("query_complete", False),
                                "processing_complete": value.get("processing_complete", False),
                                "announcement_count": value.get("announcement_count", 0),
                                "query": {key: value.get("query", {}).get(key) for key in ["start_date", "end_date"]}}
                         for code, value in summary.get("coverage", {}).items()},
            "sources": [{"id": identity, "title": value.get("title", "原公告"), "date": value.get("publication_date", ""),
                         "url": safe_url(value.get("pdf_url") or value.get("url"))} for identity, value in notices.items()],
            "source_count": len(notices), "events": events}


def render_product(state, summary, *, frozen=False, back_url=None):
    datetime.fromisoformat(summary["as_of"])
    data = json.dumps(product_data(state, summary, frozen=frozen), ensure_ascii=False).replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")
    css = (ROOT / "calendar.css").read_text(encoding="utf-8")
    js = (ROOT / "calendar.js").read_text(encoding="utf-8")
    back = '<a class="back-link" href="' + escape(back_url, quote=True) + '">返回讲义 ↗</a>' if back_url else ""
    return '''<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>公告事件日历 · 公告事件智能体</title><style>''' + css + '''</style></head>
<body><a class="skip" href="#calendar-main">跳到日历</a>
<header class="app-header"><div class="wordmark"><span class="brand-mark" aria-hidden="true">ae</span><div>公告事件智能体<small>投研团队的说明会日程</small></div></div><div class="header-actions">''' + back + '''<button class="primary" id="reminder-settings" type="button">提醒设置</button></div></header>
<main id="calendar-main"><div class="page-heading"><div><p class="eyebrow">CNINFO · 业绩说明会通知及变更</p><h1>公告事件日历</h1><p id="data-context" class="muted"></p></div><p class="timezone">日期与时刻<br><strong>北京时间 UTC+8</strong></p></div>
<div id="freshness-note" class="context-note"></div>
<div class="workspace-tools"><nav class="view-tabs" aria-label="事件视图"><button data-view="calendar" aria-pressed="true">日历</button><button data-view="updates" aria-pressed="false" id="updates-tab">今日更新</button><button data-view="all" aria-pressed="false">全部事件</button><button data-view="review" aria-pressed="false" id="review-tab">待复核</button></nav><div class="search-tools"><label class="sr-only" for="company-filter">跟踪公司</label><select id="company-filter"><option value="">全部公司</option></select><label class="sr-only" for="event-search">搜索公司、代码或报告期</label><input type="search" id="event-search" placeholder="搜索公司、代码或报告期"></div></div>
<section id="calendar-view"><div class="calendar-layout"><section class="calendar-card" aria-label="月历"><div class="month-toolbar"><div class="month-title"><h2 id="month-label"></h2><span id="month-count"></span></div><div class="month-actions"><button id="previous-month" aria-label="上个月">‹</button><button id="go-today">今天</button><button id="next-month" aria-label="下个月">›</button><button id="next-meeting" class="next-meeting">下次会议 ↗</button></div></div><div class="legend"><span><i class="key existing"></i>已有会议</span><span id="fresh-legend"><i class="key fresh"></i>今日收录/更新</span><span><i class="key deadline"></i>提问/报名截止</span><span><i class="key review"></i>待复核</span></div><div class="weekdays" aria-hidden="true"><span>一</span><span>二</span><span>三</span><span>四</span><span>五</span><span>六</span><span>日</span></div><div id="month-grid" class="month-grid" aria-label="按日期查看公司事件"></div><p class="calendar-help">选择有标记的日期，再点公司查看摘要、参与方式和公告原文。历史安排继续保留。</p></section><aside class="agenda-column"><section class="day-card"><div class="section-caption">当天安排</div><h2 id="selected-date"></h2><div id="day-events" aria-live="polite"></div></section><section class="upcoming-card"><div class="section-caption">接下来要做</div><div id="upcoming-items"></div><button class="text-button" id="export-upcoming">添加未来日程提醒 ↗</button><p class="small muted">导入日历后，默认提前1天、30分钟提醒。</p></section></aside></div></section>
<section id="list-view" class="list-view" hidden><div class="list-heading"><h2 id="list-title"></h2><p id="list-description" class="muted"></p></div><div id="event-list" class="record-list" aria-live="polite"></div></section>
<details class="data-details"><summary id="data-status">数据状态与原公告</summary><div id="data-details-content"></div></details>
<footer>公告来源为巨潮资讯。会议日期已过不代表已核实召开；有冲突的字段保留原值和候选，复核前不生成该字段提醒。</footer></main>
<dialog id="event-dialog" aria-labelledby="event-dialog-title"><button class="close-dialog" data-close aria-label="关闭事件详情">×</button><div id="event-dialog-content"></div></dialog>
<dialog id="reminder-dialog" aria-labelledby="reminder-dialog-title"><button class="close-dialog" data-close aria-label="关闭提醒设置">×</button><p class="eyebrow">参会与提问提醒</p><h2 id="reminder-dialog-title">把安排加入你的日历</h2><p>下载未来会议和已确认的提问/报名截止日程，导入系统日历后使用。默认在每项安排前<strong>1天、30分钟</strong>提醒。</p><div class="reminder-example"><span>提醒内容</span><strong>公司 · 会议时间或截止时间</strong><small>包含参与入口和原公告链接，按北京时间保存。</small></div><div id="reminder-eligible"></div><button class="primary" id="download-reminders">下载未来日程 .ics</button><p class="small" id="download-status" role="status"></p><h3>第一次使用</h3><ol><li>下载 .ics 文件，导入自己新建的“公告事件”日历。</li><li>核对公司、时间和两条提醒，确认日历应用允许通知。</li><li>公告改期、取消或进入待复核时，检查并更新已导入的旧提醒。</li></ol><p class="import-note">这是当前日程的导入快照，不会自动同步后续变更。页面上的后台定时更新与个人日历的提醒设置分别维护；关闭网页后，由已导入的日历负责提醒。</p></dialog>
<p id="action-status" role="status" aria-live="polite"></p><noscript><p class="context-note">请启用JavaScript以使用交互日历。原始状态和运行摘要另行保留。</p></noscript>
<script id="calendar-data" type="application/json">''' + data + '''</script><script>''' + js + '''</script></body></html>'''
