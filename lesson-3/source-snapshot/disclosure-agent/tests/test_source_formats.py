import pytest

from disclosure_agent.extract import source_notice_numbers, validate_evidence, _date_in
from disclosure_agent.scope import source_heading_period, source_current_period, is_quarterly_briefing
from test_extract_runner import output


@pytest.mark.parametrize('label', ['公告编号：2031[001]', '公告编号：第2031-001号',
                                 '公告编号：2031—临001号', '公告编码：2031-001',
                                 '公告编号：临2031-001', '公告编号：2031001',
                                 '编码：临2031-001', '公告编号：临-2031-001'])
def test_own_notice_header_formats_preserve_the_same_number(label):
    data = output()
    page = label + '\n关于召开2031年半年度业绩说明会的公告\n' + data['meeting_evidence']['quote']
    assert source_notice_numbers(label) == [('2031', '001')]
    assert not validate_evidence(data, [page])
    data['notice_number'] = '2031-002'
    assert 'unsupported_notice_number' in validate_evidence(data, [page])


def test_security_and_bond_codes_are_not_the_announcement_number():
    assert source_notice_numbers('证券编码：1234567\n债券编码：2234567\n编码：临2031-001') == [('2031','001')]


def test_empty_image_cover_does_not_change_physical_evidence_page_numbers():
    data = output()
    data['meeting_evidence']['page'] = 2
    page = '公告编号：2031-001\n关于召开2031年半年度业绩说明会的公告\n' + data['meeting_evidence']['quote']
    assert not validate_evidence(data, ['', page])
    data['meeting_evidence']['page'] = 1
    assert 'ungrounded_quote:meeting_evidence' in validate_evidence(data, ['', page])


def test_regional_heading_year_binds_only_to_the_explicit_reporting_period():
    title = '关于参加2031年虚构辖区上市公司三季报集体业绩说明会的公告'
    assert source_heading_period(title) == '2031-Q3'
    assert source_current_period(title, []) == '2031-Q3'
    assert is_quarterly_briefing(title)
    assert not is_quarterly_briefing('关于参加2031年虚构辖区上市公司集体接待日的公告')
    assert source_heading_period('公告编号2031-001 关于参加三季报业绩说明会') is None
    assert source_heading_period('关于2031年10月20日召开三季度业绩说明会的公告') is None
    assert source_heading_period('参加2031年虚构辖区上市公司2030年度业绩说明会') == '2030-FY'
    assert source_heading_period('参加2031年虚构辖区上市公司年报集体业绩说明会') is None
    assert source_current_period('参加2031年虚构辖区上市公司年报集体业绩说明会',
        ['本次活动中，公司将介绍2030年度业绩。']) == '2030-FY'
    assert source_current_period('关于召开业绩说明会的公告',
        ['', '公告编号2031-001\n' + title + '\n本公司保证真实。']) == '2031-Q3'


def test_current_company_quarterly_collective_briefing_is_an_event_but_reception_is_not():
    title = '关于参加2031年虚构辖区上市公司三季报集体业绩说明会的公告'
    page = '公告编号2031-001\n' + title + '\n会议召开时间：2031年9月20日14:00-15:00'
    ignored = {key: None for key in output()}
    ignored.update(notice_kind='collective', report_period='2031-Q3', notice_number='2031-001', review_notes=[])
    assert 'source_scope_conflict' in validate_evidence(ignored, [page], {'title': title})
    event = {**output(), 'report_period': '2031-Q3'}
    assert not validate_evidence(event, [page], {'title': title})
    generic = '关于参加2031年第三季度上市公司集体接待日的公告'
    assert not validate_evidence(ignored, ['公告编号2031-001\n' + generic], {'title': generic})
    assert 'source_scope_conflict' in validate_evidence(event, [page], {'title': generic})


def test_completed_quarterly_collective_briefing_cannot_become_a_future_event():
    title = '2031年第三季度集体业绩说明会投资者关系活动记录表'
    data = {key: None for key in output()}
    data.update(notice_kind='completed', report_period='2031-Q3', notice_number='2031-001', review_notes=[])
    assert not validate_evidence(data, ['公告编号2031-001\n' + title], {'title': title})
    data['notice_kind'] = 'initial'
    assert 'source_scope_conflict' in validate_evidence(data, ['公告编号2031-001\n' + title], {'title': title})


def test_day_only_range_endpoint_inherits_month_only_with_an_immediate_range_bridge():
    assert _date_in('2031-11-09', '2031年11月3日至9日16:00前')
    assert not _date_in('2031-10-09', '2031年11月3日至9日16:00前')
    assert not _date_in('2031-11-09', '2031年11月3日活动结束；9日16:00前')
    assert not _date_in('2032-11-09', '2031年11月3日至2032年9日16:00前')


def test_named_earnings_briefing_time_is_a_meeting_role():
    data = output()
    data['meeting_evidence']['quote'] = '2031年半年度业绩说明会时间为2031年9月20日14:00-15:00。'
    assert not validate_evidence(data, ['公告编号：2031-001\n' + data['meeting_evidence']['quote']])
    data['meeting_evidence']['quote'] = '2031年半年度业绩说明会提问截止时间为2031年9月20日14:00。'
    assert 'unproven_meeting_role' in validate_evidence(data, ['公告编号：2031-001\n' + data['meeting_evidence']['quote']])


def test_company_participation_in_its_briefing_proves_the_meeting_role():
    data = output()
    header = '公告编号：2031-001\n关于召开2031年半年度业绩说明会的公告\n'
    data['meeting_evidence']['quote'] = '公司计划于2031年9月20日14:00-15:00参加2031年半年度集体业绩说明会。'
    assert not validate_evidence(data, [header + data['meeting_evidence']['quote']])
    data['meeting_evidence']['quote'] = '公司计划于2031年9月20日14:00-15:00披露半年度报告。'
    assert 'unproven_meeting_role' in validate_evidence(data, [header + data['meeting_evidence']['quote']])
