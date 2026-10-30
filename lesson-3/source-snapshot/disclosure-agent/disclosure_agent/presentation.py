"""A self-contained calendar shared by live runs and the lesson."""
from datetime import datetime
from html import escape
import json
from pathlib import Path

from .reminders import reminder_items, render_ics, safe_url
from .source_text import participation_excerpts, participation_html, deadline_label, event_deadline_label
from .ledger import event_review_reasons
from .scope import period_matches, scoped_issues, meeting_window

ROOT = Path(__file__).resolve().parent
PERIODS = {"H1": "半年度", "Q1": "第一季度", "Q2": "第二季度", "Q3": "第三季度", "Q4": "第四季度", "FY": "年度"}


def review_label(errors):
    text = " ".join(str(error) for error in errors)
    for keyword, label in [("unresolved_a_share_identity", "公司身份需要核对"),
                           ("source_hash_changed", "同一公告原件发生变化，旧安排需要核对"),
                           ("source_scope_conflict", "原文与已收录安排的类型或报告期不一致"),
                           ("source_download", "公告未能完整读取"), ("source_integrity", "原件或记录的指纹需要核对"),
                           ("unfinished_provider_attempt", "上次处理未留下完整回执，需核对后重试"),
                           ("unsupported_report_period", "本次说明会的报告期需要核对"),
                           ("ambiguous_or_missing_original_notice", "变更尚未可靠关联原通知"),
                           ("unsupported_notice_number", "公告编号需要核对"),
                           ("ungrounded_quote", "提取的引文与原文不一致"),
                           ("unsupported_value", "会议或截止时刻需要核对"),
                           ("source_metadata_period_changed", "已收录通知的来源信息发生变化")]:
        if keyword in text:
            return label
    return "尚未通过原文核验，未采用为确定会议安排"



def period_label(value):
    if "+" in (value or ""):
        return "、".join(period_label(part) for part in value.split("+"))
    year, _, period = (value or "").partition("-")
    return year + "年" + PERIODS.get(period, period) if year else "报告期待确认"


def product_data(state, summary, *, frozen=False):
    scope = summary.get("scope") or state.get("scope", {})
    target = scope.get("report_period")
    notices = {identity: notice for identity, notice in state.get("notices", {}).items()
               if (not notice.get("extraction", {}).get("report_period") or period_matches(notice["extraction"]["report_period"], target))
               and notice.get("extraction", {}).get("notice_kind") not in {"completed", "collective", "other"}}
    issues = scoped_issues(state, summary.get("issues", []), target)
    review_candidates = []
    for candidate in summary.get("review_candidates", []):
        if candidate.get("report_period") and not period_matches(candidate["report_period"], target) and "source_metadata_period_changed" not in candidate.get("errors", []):
            continue
        review_candidates.append({key: candidate.get(key) for key in ("id", "company", "stock_code", "title", "date")} |
                                 {"url": safe_url(candidate.get("url")), "reason": review_label(candidate.get("errors", [])),
                                  "scope_label": "三季度候选" if period_matches(candidate.get("report_period"), target) else "范围待确认"})
    events = []
    for event in state.get("events", {}).values():
        if not period_matches(event.get("report_period"), target):
            continue
        window = meeting_window(event, scope)
        if window == "outside":
            continue
        sources = []
        for identity in event.get("source_ids", []):
            notice = notices.get(identity)
            if not notice:
                continue
            extraction = notice.get("extraction", {})
            evidence = [{"label": label, **extraction[field]} for field, label in [
                ("meeting_evidence", "会议时间"), ("deadline_evidence", deadline_label(notice)),
                ("relation_evidence", "关联原通知")]
                if extraction.get(field)]
            participation = participation_excerpts(notice)
            sources.append({"id": identity, "title": notice.get("title", "原公告"),
                            "date": notice.get("publication_date", ""),
                            "url": safe_url(notice.get("pdf_url") or notice.get("url")),
                            "number": extraction.get("notice_number"), "evidence": evidence,
                            "participation": participation,
                            "participation_html": participation_html(participation)})
        projected = {key: event.get(key) for key in ["id", "company", "stock_code", "report_period", "meeting_date",
                     "start_time", "end_time", "question_deadline_date", "question_deadline_time", "status", "validity"]}
        display_period = period_label(target or event.get("report_period"))
        if target and "+" in (event.get("report_period") or ""):
            display_period += "（合并召开）"
        projected.update(period=display_period,
                         participation_url=safe_url(event.get("participation_url")),
                         deadline_label=event_deadline_label(event, notices),
                         sources=sources, pending=event.get("pending_fields", {}), history=event.get("history", []),
                         activity=event.get("activity", {}),
                         review_reasons=sorted(set(event.get("review_reasons", []) + event_review_reasons(event, issues))))
        components = reminder_items(event, notices, issues) if window != "moved_out" else []
        if window == "moved_out":
            projected["status"] = "outside_window"
        projected["reminders"] = [{**item, "ics": render_ics([item], summary["as_of"])} for item in components]
        projected["reminder_blocked"] = not any(item["kind"] == "meeting" for item in components)
        events.append(projected)
    visible_ids={source['id'] for event in events for source in event['sources']}
    if not scope.get('meeting_start'):
        visible_ids.update(notices)
    sources={identity:{"id":identity,"title":value.get("title","原公告"),"date":value.get("publication_date",""),
                       "url":safe_url(value.get("pdf_url") or value.get("url"))}
             for identity,value in notices.items() if identity in visible_ids}
    for candidate in review_candidates:
        sources.setdefault(candidate['id'],{key:candidate[key] for key in ('id','title','date','url')})
    return {"as_of": summary["as_of"], "frozen": frozen, "run_id": summary.get("run_id"), "scope": scope,
            "scope_label": period_label(target) if target else "",
            "market": summary.get("market"),
            "review_candidates": review_candidates,
            "status": summary.get("status"), "trigger": summary.get("trigger"),
            "model_calls": summary.get("model_calls", 0), "cache_count": len(summary.get("cached_notice_ids", [])),
            "coverage": {code: {"query_complete": value.get("query_complete", False),
                                "processing_complete": value.get("processing_complete", False),
                                "announcement_count": value.get("announcement_count", 0),
                                "query": {key: value.get("query", {}).get(key) for key in ["start_date", "end_date"]}}
                         for code, value in summary.get("coverage", {}).items()},
            "sources": list(sources.values()),
            "source_count": len(sources), "events": events}


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
<header class="app-header"><div class="wordmark"><span class="brand-mark" aria-hidden="true">ae</span><div>公告事件智能体<small>投研团队的说明会日程</small></div></div><div class="header-actions">''' + back + '''</div></header>
<main id="calendar-main"><div class="page-heading"><div><p class="eyebrow">CNINFO · 业绩说明会通知及变更</p><h1>公告事件日历</h1><p id="data-context" class="muted"></p></div><p class="timezone">日期与时刻<br><strong>北京时间 UTC+8</strong></p></div>
<div id="freshness-note" class="context-note"></div>
<div class="workspace-tools"><nav class="view-tabs" aria-label="事件视图"><button data-view="calendar" aria-pressed="true">日历</button><button data-view="updates" aria-pressed="false" id="updates-tab">今日更新</button><button data-view="all" aria-pressed="false">全部事件</button><button data-view="review" aria-pressed="false" id="review-tab">待复核</button></nav><div class="search-tools"><label class="sr-only" for="company-filter">跟踪公司</label><select id="company-filter"><option value="">全部公司</option></select><label class="sr-only" for="event-search">搜索公司、代码或报告期</label><input type="search" id="event-search" placeholder="搜索公司、代码或报告期"></div></div>
<section id="calendar-view"><div class="calendar-layout"><section class="calendar-card" aria-label="月历"><div class="month-toolbar"><div class="month-title"><h2 id="month-label"></h2><span id="month-count"></span></div><div class="month-actions"><button id="previous-month" aria-label="上个月">‹</button><button id="go-today">今天</button><button id="next-month" aria-label="下个月">›</button><button id="next-meeting" class="next-meeting">下次会议 ↗</button></div></div><div class="legend"><span><i class="key existing"></i>已有会议</span><span id="fresh-legend"><i class="key fresh"></i>今日收录/更新</span><span><i class="key deadline"></i>截止日</span><span><i class="key review"></i>待复核</span></div><div class="weekdays" aria-hidden="true"><span>一</span><span>二</span><span>三</span><span>四</span><span>五</span><span>六</span><span>日</span></div><div id="month-grid" class="month-grid" aria-label="按日期查看公司事件"></div><p class="calendar-help">选择有标记的日期，再点公司查看摘要、参与方式和公告原文。历史安排继续保留。</p></section><aside class="agenda-column"><section class="day-card"><div class="section-caption">当天安排</div><h2 id="selected-date"></h2><div id="day-events" aria-live="polite"></div></section></aside></div></section>
<section id="list-view" class="list-view" hidden><div class="list-heading"><h2 id="list-title"></h2><p id="list-description" class="muted"></p></div><div id="event-list" class="record-list" aria-live="polite"></div></section>
<details class="data-details"><summary id="data-status">数据状态与原公告</summary><div id="data-details-content"></div></details>
<footer>公告来源为巨潮资讯。会议日期已过不代表已核实召开；有冲突的字段保留原值和候选，复核前不生成该字段提醒。</footer></main>
<dialog id="event-dialog" aria-labelledby="event-dialog-title"><button class="close-dialog" data-close aria-label="关闭事件详情">×</button><div id="event-dialog-content"></div></dialog>
<p id="action-status" role="status" aria-live="polite"></p><noscript><p class="context-note">请启用JavaScript以使用交互日历。原始状态和运行摘要另行保留。</p></noscript>
<script id="calendar-data" type="application/json">''' + data + '''</script><script>''' + js + '''</script></body></html>'''
