from copy import deepcopy
from datetime import datetime, timezone
import json
import re

import pytest

from disclosure_agent.reminders import reminder_items, render_ics, safe_url
from disclosure_agent.presentation import render_product, product_data


def sample():
    event = dict(id="123456:original", company="虚构测试公司", stock_code="123456", report_period="2030-Q3",
                 status="scheduled", meeting_date="2030-11-25", start_time="14:00", end_time="15:00",
                 question_deadline_date="2030-11-24", question_deadline_time="16:00",
                 participation_url="https://example.invalid/join", pending_fields={}, history=[],
                 source_ids=["original"], activity={"updated_at":"2030-10-30T08:30:00+08:00", "revision":0})
    notices = {"original":dict(id="original", title="虚构公告", publication_date="2030-10-30",pdf_url="https://example.invalid/source.pdf",pdf_path="/private/must-not-leak.pdf",extraction={})}
    return event, notices


def test_ics_encodes_correct_utc_times_two_alarms_and_stable_amendment_uid():
    event, notices = sample()
    before = reminder_items(event, notices)
    assert {item["kind"] for item in before} == {"meeting", "deadline"}
    text = render_ics(before, "2030-10-30T08:30:00+08:00")
    assert "DTSTART:20301125T060000Z\r\nDTEND:20301125T070000Z" in text
    assert "DTSTART:20301124T080000Z" in text
    assert text.count("TRIGGER:-P1D") == 2 and text.count("TRIGGER:-PT30M") == 2
    amended = deepcopy(event)
    amended.update(meeting_date="2030-11-26", activity={"revision":1})
    after = reminder_items(amended, notices)
    assert after[0]["uid"] == before[0]["uid"] and after[0]["sequence"] == 1
    assert "DTSTART:20301126T060000Z" in render_ics(after, "2030-10-31T08:30:00+08:00")


@pytest.mark.parametrize("status", ["cancelled", "postponed"])
def test_inactive_event_generates_no_alarm(status):
    event, notices = sample(); event["status"] = status
    assert reminder_items(event, notices) == []


def test_conflicted_deadline_does_not_block_reliable_meeting_but_does_block_deadline_alarm():
    event, notices = sample()
    event["pending_fields"] = {"question_deadline_date":[{"old":"2030-11-24","candidate":"2030-11-25"}]}
    assert [item["kind"] for item in reminder_items(event, notices)] == ["meeting"]
    event["pending_fields"]["meeting_date"] = [{}]
    assert reminder_items(event, notices) == []


def test_missing_time_is_not_invented_and_source_conflict_blocks_alarm():
    event, notices = sample(); event.update(start_time=None, question_deadline_time=None)
    assert reminder_items(event, notices) == []
    event, notices = sample(); event["end_time"] = None
    assert "DTEND:" not in render_ics([reminder_items(event, notices)[0]], "2030-10-30")
    notices["original"]["versions"] = [{"version_status":"source_conflict"}]
    assert reminder_items(event, notices) == []


def test_incomplete_company_coverage_does_not_export_unchecked_times():
    event, notices = sample()
    assert reminder_items(event, notices, [{"stock_code":"123456","reason":"company_coverage_incomplete"}]) == []


def test_ics_escapes_text_and_folds_utf8_without_splitting_characters():
    event, notices = sample();event["company"] = "甲,乙;丙\\丁\n" + "中文"*60
    text = render_ics(reminder_items(event, notices), "2030-10-30T08:30:00+08:00")
    assert all(len(line.encode()) <= 75 for line in text.split("\r\n"))
    unfolded = re.sub(r"\r\n[ \t]", "", text)
    assert "甲\\,乙\\;丙\\\\丁\\n" in unfolded
    assert text.endswith("END:VCALENDAR\r\n")


def test_projection_has_no_private_paths_and_script_text_cannot_end_data_element():
    event, notices = sample(); event["company"] = '</script><script>alert("x")</script>'
    state={"events":{event["id"]:event},"notices":notices}
    summary={"as_of":"2030-10-30T08:30:00+08:00","status":"complete"}
    html = render_product(state, summary, frozen=True)
    assert "/private/must-not-leak" not in html
    assert '</script><script>alert' not in html
    embedded = re.search(r'<script id="calendar-data" type="application/json">(.*?)</script>',html).group(1)
    assert json.loads(embedded)["events"][0]["company"] == event["company"]


@pytest.mark.parametrize("url", ["javascript:alert(1)", "https://example.invalid/a\r\nBEGIN:VEVENT", "http://", "//example.invalid/a"])
def test_unsafe_participation_and_source_urls_are_not_links(url):
    assert safe_url(url) == ""


def test_unlinked_amendment_blocks_old_times_and_is_visible_in_review():
    event, notices = sample()
    issues = [{"stock_code":"123456","source_id":"unlinked","reason":"ambiguous_or_missing_original_notice"}]
    assert reminder_items(event, notices, issues) == []
    projected = product_data({"events":{event["id"]:event},"notices":notices}, {"as_of":"2030-10-30T08:30:00+08:00","issues":issues})
    assert projected["events"][0]["review_reasons"] == ["ambiguous_or_missing_original_notice"]
    assert projected["events"][0]["reminder_blocked"] is True


def test_public_coverage_omits_exception_paths_and_keeps_all_source_links():
    event, notices = sample(); notices["unlinked"]={"title":"未关联变更","pdf_url":"https://example.invalid/change.pdf"}
    summary={"as_of":"2030-10-30T08:30:00+08:00","coverage":{"123456":{"error":"PermissionError /Users/private/secret","query":{"start_date":"2030-10-01","debug":"/private/token"}}}}
    projected=product_data({"events":{event["id"]:event},"notices":notices},summary)
    assert "/Users/private" not in json.dumps(projected) and "/private/token" not in json.dumps(projected)
    assert len(projected["sources"]) == 2
    assert safe_url("https://[invalid") == ""


def test_missing_source_cannot_generate_a_confirmed_reminder():
    event, _ = sample()
    assert reminder_items(event, {}) == []


def test_participation_steps_are_contiguous_physical_page_quotes_from_bound_pdf(tmp_path, monkeypatch):
    import hashlib
    from types import SimpleNamespace
    from disclosure_agent import source_text
    path=tmp_path/'source.pdf';path.write_bytes(b'explicitly synthetic test source')
    pages=['第一页无参与部分', '四、投资者参加方式\n（一）登录合成入口参加\n（二）请先报名', '续接前页的合成报名说明\n五、联系人及咨询办法\n不应进入参与摘录']
    monkeypatch.setattr(source_text,'PdfReader',lambda _:SimpleNamespace(pages=[SimpleNamespace(extract_text=lambda text=text:text) for text in pages]))
    source={'pdf_path':str(path),'pdf_sha256':hashlib.sha256(path.read_bytes()).hexdigest()}
    excerpts=source_text.participation_excerpts(source)
    assert [item['page'] for item in excerpts] == [2,3]
    assert all(item['quote'] in pages[item['page']-1] for item in excerpts)
    assert '不应进入参与摘录' not in str(excerpts)
    source['pdf_sha256']='mismatch'
    assert source_text.participation_excerpts(source) == []


def test_full_participation_keeps_cross_page_routes_and_ignores_hidden_pdf_links(tmp_path, monkeypatch):
    import hashlib
    from types import SimpleNamespace
    from disclosure_agent import source_text
    path = tmp_path / 'synthetic.pdf'
    path.write_bytes(b'explicit synthetic participation source')
    texts = [
        '四、投 资 者 参 与 方 式\n（一）电话会议\n路径1：登录https://example.invalid/register\n路径2：公司官网\n路径3：微信公众号',
        '2\n预报名说明接续上一页。\n（二）音频直播结合网络互动\n1、登录https://example.invalid/roadshow\n2、登录https://example.invalid/\nquestionCollection.do提问。\n五、联系方式\n非参与部分',
    ]
    pages = [SimpleNamespace(extract_text=lambda text=text: text,
                             get=lambda _: [{'/A': {'/URI': 'https://example.invalid/hidden-old-event'}}])
             for text in texts]
    monkeypatch.setattr(source_text, 'PdfReader', lambda _: SimpleNamespace(pages=pages))
    source = {'pdf_path': str(path), 'pdf_sha256': hashlib.sha256(path.read_bytes()).hexdigest()}
    excerpts = source_text.participation_excerpts(source)
    rendered = source_text.participation_html(excerpts)
    assert [row['page'] for row in excerpts] == [1, 2]
    assert all(row['quote'] in texts[row['page'] - 1] for row in excerpts)
    assert all(word in rendered for word in ['路径1', '路径2', '路径3', '微信公众号', '音频直播结合网络互动'])
    assert 'href="https://example.invalid/questionCollection.do"' in rendered
    assert '联系方式' not in rendered and 'hidden-old-event' not in rendered
    assert '<details' not in rendered and '…' not in rendered


def test_participation_links_only_visible_urls_and_escapes_the_remaining_source_text():
    from disclosure_agent.source_text import participation_html
    from html.parser import HTMLParser
    class Links(HTMLParser):
        def __init__(self):
            super().__init__(); self.urls = []
        def handle_starttag(self, tag, attrs):
            if tag == 'a':
                self.urls.append(dict(attrs)['href'])
    text = '（一）电话会议\n路径1：登录https://example.invalid/sign-\nup?x=1&y=2。\n路径2：官网https://example.invalid/。\n路径3：微信公众号。\n（二）网络互动\n1、登录https://roadshow.example.invalid/。\n2、提问https://roadshow.example.invalid/\npreCallQa。\n<script>不执行</script>'
    html = participation_html([{'page': 2, 'quote': text}])
    parser = Links(); parser.feed(html)
    assert parser.urls == ['https://example.invalid/sign-up?x=1&y=2', 'https://example.invalid/',
                           'https://roadshow.example.invalid/', 'https://roadshow.example.invalid/preCallQa']
    assert '<h4>（一）电话会议</h4>' in html and '<h4>（二）网络互动</h4>' in html
    assert '<script>' not in html and '&lt;script&gt;' in html


def test_bound_pdf_is_verified_even_when_a_participation_cache_is_present(tmp_path):
    from disclosure_agent.source_text import participation_excerpts
    path = tmp_path / 'changed.pdf'; path.write_bytes(b'changed synthetic bytes')
    notice = {'pdf_path': str(path), 'pdf_sha256': 'wrong',
              'participation_evidence': [{'page': 1, 'quote': '不应沿用的缓存'}]}
    assert participation_excerpts(notice) == []


@pytest.mark.parametrize('quote,label', [
    ('投资者可于2030年11月24日16:00前进行预报名。','预报名截止'),
    ('报名截止时间为2030年11月24日16:00。','报名截止'),
    ('投资者提问征集截至2030年11月24日16:00。','提问截止'),
    ('截止时间为2030年11月24日16:00。','截止时间'),
])
def test_deadline_role_is_shared_by_event_and_calendar_export(quote,label):
    from disclosure_agent.source_text import event_deadline_label
    event,notices=sample()
    notices['original']['extraction']={'question_deadline_date':'2030-11-24','deadline_evidence':{'page':2,'quote':quote}}
    assert event_deadline_label(event,notices)==label
    component=next(item for item in reminder_items(event,notices) if item['kind']=='deadline')
    assert component['title'].endswith(' · '+label)
    projected=product_data({'events':{event['id']:event},'notices':notices},{'as_of':'2030-10-30T08:30:00+08:00'})
    assert projected['events'][0]['deadline_label']==label


def test_role_context_must_contain_exact_quote_and_stay_in_same_subsection():
    from disclosure_agent.source_text import deadline_label
    quote='2030年11月24日16:00前登录网站首页'
    notice={'extraction':{'deadline_evidence':{'page':2,'quote':quote}},'participation_evidence':[{'page':2,'quote':'（一）预报名截止为2030年11月23日。\n（二）投资者可于'+quote+'，点击“提问预征集”栏目。'}]}
    assert deadline_label(notice)=='提问截止'
    notice['extraction']['deadline_evidence']['quote']='原文中不存在的截止句'
    assert deadline_label(notice)=='截止时间'


def test_unchanged_old_deadline_uses_its_original_role_not_latest_notice_other_task():
    from disclosure_agent.source_text import event_deadline_label
    event,notices=sample()
    notices['original']['extraction']={'question_deadline_date':'2030-11-24','deadline_evidence':{'page':2,'quote':'投资者提问截止为2030年11月24日16:00。'}}
    notices['change']={'extraction':{'question_deadline_date':'2030-11-23','deadline_evidence':{'page':2,'quote':'预报名截止2030年11月23日16:00。'}}}
    event['source_ids'].append('change')
    assert event_deadline_label(event,notices)=='提问截止'


def test_unheaded_participation_paragraph_keeps_the_actual_mini_program(monkeypatch,tmp_path):
    from disclosure_agent import source_text
    import hashlib
    text='证券代码：000000。公司定于2030年10月19日下午3:00至5:00在“虚构公司投资者关系”小程序举行三季度说明会，投资者可登录该小程序参与互动。此前投资者可登录旧网址回看上次会议。'
    class Page:
        def extract_text(self): return text
    class PDF:
        pages=[Page()]
    path=tmp_path/'synthetic.pdf';path.write_bytes(b'synthetic source binding')
    monkeypatch.setattr(source_text,'PdfReader',lambda path:PDF())
    excerpts=source_text.participation_excerpts({'pdf_path':str(path),'pdf_sha256':hashlib.sha256(path.read_bytes()).hexdigest()})
    assert '“虚构公司投资者关系”小程序' in ''.join(x['quote'] for x in excerpts)
    assert all('旧网址' not in x['quote'] for x in excerpts)
    assert all(x['quote'] in text for x in excerpts)
