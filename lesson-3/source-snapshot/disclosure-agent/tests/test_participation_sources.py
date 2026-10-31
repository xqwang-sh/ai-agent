"""Participation routes must remain complete when a source splits their uses."""
from hashlib import sha256
from types import SimpleNamespace

from disclosure_agent import source_text


def bound_source(tmp_path, monkeypatch, pages):
    path = tmp_path / 'synthetic-participation.pdf'
    path.write_bytes(b'explicitly synthetic source fixture')
    monkeypatch.setattr(source_text, 'PdfReader', lambda _: SimpleNamespace(pages=[
        SimpleNamespace(extract_text=lambda text=text: text) for text in pages]))
    return {'pdf_path': str(path), 'pdf_sha256': sha256(path.read_bytes()).hexdigest()}


def test_formal_meeting_mode_is_available_when_no_participation_section_exists(tmp_path, monkeypatch):
    pages = ['一、会议召开时间：\n2030年10月29日15:00-16:30\n'
             '二、会议召开方式：合成投资者互动平台\n网址：https://meeting.example.invalid/company\n'
             '届时公司管理层将在线与投资者互动交流。\n特此公告。\n合成公司董事会']
    source = bound_source(tmp_path, monkeypatch, pages)
    excerpts = source_text.participation_excerpts(source)
    html = source_text.participation_html(excerpts)
    assert '合成投资者互动平台' in html and 'href="https://meeting.example.invalid/company"' in html
    assert '在线与投资者互动交流' in html and '合成公司董事会' not in html
    assert all(row['quote'] in pages[row['page'] - 1] for row in excerpts)


def test_meeting_venue_is_kept_when_later_participation_section_only_collects_questions(tmp_path, monkeypatch):
    pages = [
        '二、说明会召开的时间、地点\n（二）会议召开地点\n本次说明会采用网络方式召开，投资者可登陆全景网“投资关系互动平台”（http://ir.example.invalid）参与本次说明会。\n三、参加人员\n公司管理人员。\n四、投资者参加方式\n',
        '本次说明会采用网络方式召开。\n投资者可于截止日前访问（http://ir.example.invalid/zj/），进入问题征集专题页面，进行提问。\n五、联系方式\n联系电话：0000-00000000。',
    ]
    source = bound_source(tmp_path, monkeypatch, pages)
    excerpts = source_text.participation_excerpts(source)
    html = source_text.participation_html(excerpts)
    assert 'href="http://ir.example.invalid"' in html
    assert 'href="http://ir.example.invalid/zj/"' in html
    assert html.index('参与本次说明会') < html.index('问题征集专题页面')
    assert all(row['quote'] in pages[row['page'] - 1] for row in excerpts)
    assert '联系电话' not in html


def test_unheaded_mini_program_directions_remain_visible_without_report_disclosure_site(tmp_path, monkeypatch):
    pages = ['公司于昨日在巨潮资讯网（http://www.example.invalid/report）披露季度报告。\n公司本次在“合成公司投资者关系”小程序举行说明会，投资者可登录小程序参与。\n参与方式一：在微信小程序搜索“合成公司投资者关系”；\n参与方式二：微信扫一扫以下二维码。']
    source = bound_source(tmp_path, monkeypatch, pages)
    html = source_text.participation_html(source_text.participation_excerpts(source))
    assert '小程序' in html and '参与方式一' in html and '参与方式二' in html
    assert 'http://www.example.invalid/report' not in html


def test_overlap_and_repeated_summary_link_are_shown_once_in_source_order(tmp_path, monkeypatch):
    pages = ['重要提示：投资者可登录https://meeting.example.invalid/参加本次说明会。\n四、投资者参加方式\n（一）投资者可登录https://meeting.example.invalid/参加本次说明会。\n（二）请在https://meeting.example.invalid/questions提问。\n五、联系方式\n请联系公司。']
    source = bound_source(tmp_path, monkeypatch, pages)
    excerpts = source_text.participation_excerpts(source)
    html = source_text.participation_html(excerpts)
    assert html.count('href="https://meeting.example.invalid/"') == 1
    assert html.index('参加本次说明会') < html.index('questions')
    assert all(row['quote'] in pages[row['page'] - 1] for row in excerpts)


def test_unheaded_email_question_route_is_not_lost_after_the_meeting_link(tmp_path, monkeypatch):
    pages = ['本次说明会采用网络方式，投资者可登录http://meeting.example.invalid参与。\n欢迎投资者通过平台或公司电子邮箱 ir@example.invalid 将关注的问题预先提供给公司。']
    source = bound_source(tmp_path, monkeypatch, pages)
    html = source_text.participation_html(source_text.participation_excerpts(source))
    assert 'href="http://meeting.example.invalid"' in html and 'ir@example.invalid' in html


def test_phone_approval_callback_and_page_break_remain_complete_without_page_furniture(tmp_path, monkeypatch):
    pages = ['三、投资者参与方式\n（一）报名方式\n投资者可通过https://meeting.example.invalid/signup报名。',
             '合成董事会公告\n第 2页，共 2页\n（二）参会方式\n公司审核通过后，投资者将收到参会通知短信。\n投资者可选择“需要电话外呼”，会议开始前系统将自动发起来电。\n特此公告。\n合成公司董事会\n2030年10月1日']
    source = bound_source(tmp_path, monkeypatch, pages)
    excerpts = source_text.participation_excerpts(source)
    html = source_text.participation_html(excerpts)
    assert all(word in html for word in ['审核通过', '参会通知短信', '需要电话外呼', '自动发起来电'])
    assert '第 2页' not in html and '合成董事会公告' not in html and '2030年10月1日' not in html
    assert all(row['quote'] in pages[row['page'] - 1] for row in excerpts)


def test_current_routes_do_not_import_report_or_post_meeting_replay_urls(tmp_path, monkeypatch):
    pages = ['公司在http://disclosure.example.invalid披露季度报告。\n四、投资者参加方式\n投资者可登录https://meeting.example.invalid/current参加本次说明会。\n五、其他事项\n本次说明会召开后，投资者可登录https://meeting.example.invalid/replay查看本次说明会的召开情况和主要内容。']
    source = bound_source(tmp_path, monkeypatch, pages)
    html = source_text.participation_html(source_text.participation_excerpts(source))
    assert 'href="https://meeting.example.invalid/current"' in html
    assert 'disclosure.example.invalid' not in html and '/replay' not in html
