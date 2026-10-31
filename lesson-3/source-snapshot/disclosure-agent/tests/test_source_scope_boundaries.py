import hashlib

import pytest

from disclosure_agent import market
from disclosure_agent.scope import (source_current_period, source_date_outside_window,
                                    source_period, title_outside_scope)


TARGET = '2026-Q3'
TITLE = '关于召开业绩说明会的公告'
START, END = '2026-10-01', '2026-11-30'
CONFIG = {'report_period': TARGET, 'meeting_start': START, 'meeting_end': END}


@pytest.mark.parametrize('family', ['年报', '半年度', '中报', '一季报', '第二季度', '四季报'])
def test_title_family_excludes_non_q3_without_inventing_a_report_year(family):
    title = '关于参加2026年上海辖区上市公司' + family + '集体业绩说明会的公告'
    assert source_period(title) is None
    assert title_outside_scope(title, TARGET)


@pytest.mark.parametrize('title', [
    '关于参加上海辖区上市公司三季报集体业绩说明会的公告',
    '关于参加年报暨三季报业绩说明会的公告',
    '关于召开半年度暨第三季度业绩说明会的公告',
    '关于召开2026年半年度暨第三季度业绩说明会的公告',
    '关于召开2025年年度业绩说明会暨三季报交流的公告',
    '关于调整业绩说明会时间的公告',
])
def test_q3_family_or_unspecified_amendment_is_retained(title):
    assert not title_outside_scope(title, TARGET)


@pytest.mark.parametrize('title', [
    '中国中期召开业绩说明会的公告',
    '关于召开业绩说明会并介绍中期战略的公告',
    '关于召开2026年中期战略业绩说明会的公告',
    '关于召开业绩说明会并介绍年度战略的公告',
    '关于召开业绩说明会并介绍2026年度经营目标的公告',
    '关于召开业绩说明会并介绍2026年中期发展战略的公告',
    '关于召开业绩说明会并介绍2026年度业务规划的公告',
])
def test_company_names_and_strategy_terms_do_not_declare_a_report_period(title):
    assert not title_outside_scope(title, TARGET)
    assert source_current_period(title, ['本次说明会将就2026年第三季度报告与投资者交流。']) != '2026-H1'


@pytest.mark.parametrize('separator', ['，以及', '、'])
def test_parallel_current_financial_purposes_keep_the_q3_period(separator):
    page = ('本次投资者说明会将针对2026年半年度经营成果' + separator +
            '2026年第三季度经营成果与投资者交流。会议时间：2026年11月8日。')
    assert source_current_period(TITLE, [page]) == '2026-H1+2026-Q3'
    assert market._screen_source({'title': TITLE, 'pages': [page]}, CONFIG) is None


@pytest.mark.parametrize('purpose', [
    '2026年半年度报告及第三季度报告',
    '2026年半年度经营成果和第三季度经营成果',
    '2026年半年度经营成果，以及2026年第三季度情况',
])
def test_coordinated_financial_reports_bind_their_shared_year(purpose):
    page = '本次投资者说明会将就' + purpose + '与投资者沟通交流。会议时间：2026年11月8日。'
    assert source_current_period(TITLE, [page]) == '2026-H1+2026-Q3'
    assert market._screen_source({'title': TITLE, 'pages': [page]}, CONFIG) is None


def test_a_joint_heading_is_not_reexcluded_by_a_partial_body_period():
    title = '关于召开2026年半年度业绩说明会暨第三季度业绩说明会的公告'
    assert not title_outside_scope(title, TARGET)
    assert source_current_period(title, []) == '2026-H1+2026-Q3'
    assert market._screen_source({'title': title, 'pages': []}, CONFIG) is None


def test_an_unparsed_possible_q3_purpose_stays_available_for_review():
    page = '本次投资者说明会将介绍2026年半年度经营成果，以及第三季度的其他相关安排。'
    assert source_current_period(TITLE, [page]) == '2026-H1'
    assert market._screen_source({'title': TITLE, 'pages': [page]}, CONFIG) is None


@pytest.mark.parametrize('title', [
    '关于召开2025年度业绩暨现金分红说明会的公告',
    '关于举行2025年度业绩和利润分配预案网上说明会并征集问题的公告',
    '关于召开2025年度及2026年第一季度业绩暨2025年度利润分配预案网上说明会的公告',
    '关于召开2025年度业绩暨2026年第一季度业绩暨现金分红说明会的公告',
    '关于召开2025年度及2026年第一季度业绩暨2025年度分红说明会的提示性公告',
])
def test_financial_distribution_topics_do_not_hide_an_explicit_non_target_period(title):
    assert title_outside_scope(title, TARGET)
    assert market._screen_source({'title': title, 'pages': []}, CONFIG) == 'outside_report_period_in_source'


def test_q3_with_distribution_topics_is_still_a_target_briefing():
    title = '关于召开2026年半年度业绩暨第三季度业绩暨现金分红说明会的公告'
    assert source_current_period(title, []) == '2026-H1+2026-Q3'
    assert not title_outside_scope(title, TARGET)
    assert market._screen_source({'title': title, 'pages': []}, CONFIG) is None


@pytest.mark.parametrize('title', [
    '甲公司2026年第三季度业绩说明会投资者关系活动记录表',
    '关于2026年第三季度业绩说明会情况的公告',
    '2026年半年度业绩暨现金分红说明会纪要',
])
def test_explicit_post_meeting_records_are_not_future_notifications(title):
    assert market._kind_excluded(title)


@pytest.mark.parametrize('title', [
    '关于业绩说明会情况变更的公告',
    '关于2026年第三季度业绩说明会召开情况变更的公告',
    '关于调整2026年第三季度业绩说明会召开情况的公告',
])
def test_a_situation_change_notice_is_not_a_post_meeting_report(title):
    assert not market._kind_excluded(title)
    assert market._screen_source({'title': title, 'pages': ['现将召开时间调整为11月12日。']}, CONFIG) is None


def test_distribution_year_is_not_the_earnings_reporting_period():
    from disclosure_agent.extract import validate_evidence
    from test_extract_runner import output
    title = '关于召开2031年第三季度业绩暨2030年度现金分红说明会的公告'
    data = {**output(), 'report_period': '2031-Q3'}
    page = '公告编号：2031-001\n' + title + '\n' + data['meeting_evidence']['quote']
    assert source_current_period(title, [page]) == '2031-Q3'
    assert not validate_evidence(data, [page], {'title': title})


def test_update_heading_is_not_forced_to_completed_by_its_situation_word():
    from disclosure_agent.extract import validate_evidence
    from test_extract_runner import output
    title = '关于2031年第三季度业绩说明会召开情况变更的公告'
    data = {**output(), 'notice_kind': 'change', 'report_period': '2031-Q3'}
    page = '公告编号：2031-001\n' + title + '\n' + data['meeting_evidence']['quote']
    assert 'source_scope_conflict' not in validate_evidence(data, [page], {'title': title})


@pytest.mark.parametrize('purpose', ['2026年度经营目标', '2026年中期发展战略', '2026年度业务规划'])
def test_current_strategy_purpose_is_not_a_financial_report_period(purpose):
    assert source_current_period(TITLE, ['本次投资者说明会将介绍' + purpose + '。']) is None


def test_an_explicit_wrong_report_year_remains_outside_scope():
    assert title_outside_scope('关于召开2025年第三季度业绩说明会的公告', TARGET)
    assert not title_outside_scope('关于召开2026年第三季度业绩说明会的公告', TARGET)


@pytest.mark.parametrize('label', ['会议时间', '会议召开时间', '活动时间', '说明会时间', '召开时间'])
def test_current_meeting_labels_produce_physical_continuous_source_proof(label):
    page = '二、说明会安排\n' + label + '：2026 年 6 月 5 日15:00-17:00。'
    proof = source_date_outside_window(TITLE, ['', page], START, END)
    assert proof['meeting_date'] == '2026-06-05'
    assert proof['physical_page'] == proof['page'] == 2
    assert proof['quote'] in page and proof['quote'].startswith(label)
    assert proof['page_text_sha256'] == hashlib.sha256(page.encode()).hexdigest()
    assert not proof['year_inferred']


@pytest.mark.parametrize('verb', ['召开', '举行', '举办', '参加'])
def test_direct_company_plan_binds_only_its_meeting_date(verb):
    page = '公司将于2026年5月8日下午15:00-17:00在全景网提供的平台' + verb + '业绩说明会。'
    proof = source_date_outside_window('关于' + verb + '业绩说明会的公告', [page], START, END)
    assert proof['meeting_date'] == '2026-05-08'
    assert proof['quote'] == page[:-1]


def test_missing_year_is_preserved_when_only_the_month_can_exclude():
    title = '关于举办2025年业绩说明会的公告'
    proof = source_date_outside_window(title, ['会议召开时间：5月8日15:00-17:00。'], START, END)
    assert proof['meeting_date'] is None and proof['meeting_year'] is None
    assert proof['meeting_month'] == 5 and proof['meeting_day'] == 8
    assert proof['basis'] == 'month_without_year_outside_window'
    assert not proof['year_inferred']
    assert source_date_outside_window(title, ['会议召开时间：10月8日。'], START, END) is None
    assert source_date_outside_window(title, ['活动时间：5月。'], '2026-10-01', '2027-11-30') is None


@pytest.mark.parametrize('pages', [
    ['投资者提问截止：2026年5月8日16:00。'],
    ['报告发布日期：2026年5月8日。'],
    ['报名时间：2026年5月8日。'],
    ['问题征集活动时间：2026年5月8日。'],
    ['公司将于2026年4月29日披露报告，并于10月31日举行业绩说明会。'],
    ['公司将于2026年4月29日发布报告，并于10月31日举行业绩说明会。会议时间：2026年5月8日。'],
    ['公司计划于2026年5月8日前征集提问，随后举行业绩说明会。'],
    ['公司将于2026年5月8日参加其他活动，并于11月8日举行业绩说明会。'],
    ['历史会议时间：2026年5月8日。'],
    ['旧会议时间：2026年5月8日。'],
    ['原定于2026年5月8日召开，会议时间：2026年5月9日。'],
    ['会议召开时间：2026年5月8日。说明会日期待定。'],
    ['会议召开时间：2026年5月8日。', '会议时间：2026年10月8日。'],
    ['会议时间：2025年5月8日。', '会议时间：2026年5月8日。'],
    ['会议时间：2026年5月8日至5月9日。'],
    ['会议召开时间：2026年5月32日。'],
    ['股东大会会议时间：2026年5月8日。'],
    ['会议时间：2026-05-08至2026-11-08。'],
    ['会议时间：2026年5月8日（第一场）、11月8日（第二场）。'],
    ['此前，公司定于2026年5月8日召开业绩说明会。本次三季度说明会举办时间为2026年11月8日。'],
    ['会议时间：2026年5月8日。现更正为2026年11月8日。'],
    ['公司将于5月8日召开股东大会，另举办业绩说明会，时间为11月8日。'],
    ['会议时间：2026年5月8日。其他安排另见11月8日公告。'],
    ['会议时间：2026年5月8日。第二场时间：2026/11/08。'],
    ['会议时间：2026年5月8日。另一次会议为十一月八日。'],
    ['会议时间：2026年9月30日至次月2日。'],
    ['会议时间：2026年9月30日及翌日。'],
    ['会议时间：2026年5月至次年2月。'],
    ['会议时间：2026年5月起，持续至2027年2月。'],
    ['会议时间：2026年9月30日（星期三）及翌日。'],
    ['会议时间：2026年9月30日后的第一个星期五。'],
    ['会议时间：2026年5月8日15:00至2027年2月2日16:00。'],
])
def test_other_date_roles_and_uncertain_sources_cannot_exclude(pages):
    assert source_date_outside_window(TITLE, pages, START, END) is None


def test_a_range_is_not_reduced_to_its_first_endpoint_outside_the_window():
    assert source_date_outside_window(TITLE, ['会议时间：2026-05-08至2026-09-08。'],
                                      '2026-07-01', '2026-07-31') is None


def test_another_meeting_action_cannot_supply_the_briefing_date():
    assert source_date_outside_window(TITLE, ['公司将于5月8日召开股东大会，另举办业绩说明会。'], START, END) is None


@pytest.mark.parametrize('title', ['关于变更业绩说明会的公告', '关于延期举办业绩说明会的公告',
                                    '关于取消业绩说明会的公告', '关于召开业绩说明会的补充公告',
                                    '业绩说明会活动记录表', '关于召开业绩说明会的情况公告'])
def test_non_initial_or_unproven_title_does_not_produce_a_date_exclusion(title):
    assert source_date_outside_window(title, ['会议时间：2026年5月8日。'], START, END) is None


def test_conflicting_dates_are_checked_before_window_exclusion():
    pages = ['会议召开时间：2026年5月8日。公司拟于2026年11月8日举行业绩说明会。']
    assert source_date_outside_window(TITLE, pages, START, END) is None


def test_date_screen_only_applies_to_unknown_report_period_and_binds_pdf_hash():
    item = {'title': TITLE, 'pages': ['会议时间：2026年6月30日15:00-16:00。'], 'pdf_sha256': 'a' * 64}
    assert source_current_period(item['title'], item['pages']) is None
    reason = market._screen_source(item, CONFIG)
    assert reason == 'meeting_date_outside_window_in_source'
    assert item['source_scope_proof']['source_pdf_sha256'] == item['pdf_sha256']
    assert item['source_scope_proof']['quote'] in item['pages'][0]
    assert source_current_period(item['title'], item['pages']) is None
    current = {**item, 'title': '关于召开2026年第三季度业绩说明会的公告'}
    assert market._screen_source(current, CONFIG) is None
    assert 'source_scope_proof' not in current


def test_a_date_proof_without_bound_pdf_cannot_exclude_a_source():
    item = {'title': TITLE, 'pages': ['会议时间：2026年6月30日。']}
    assert market._screen_source(item, CONFIG) is None
    assert 'source_scope_proof' not in item


def test_a_previous_valid_target_record_keeps_scope_conflict_review_protection():
    item = {'title': TITLE, 'pages': ['会议时间：2026年6月30日。'], 'pdf_sha256': 'a' * 64}
    entry = {'record': {'pdf_sha256': item['pdf_sha256'],
                        'extraction': {'notice_kind': 'initial', 'report_period': TARGET}}}
    reason = market._screen_source(item, CONFIG)
    assert reason == 'meeting_date_outside_window_in_source'
    assert market._source_review(entry, item, CONFIG, reason) == 'source_scope_conflict'


@pytest.mark.parametrize('months', ['2026年5月至11月', '5月/11月'])
def test_a_month_range_cannot_be_excluded_by_its_first_month(months):
    assert source_date_outside_window(TITLE, ['会议时间：' + months + '，具体场次另见安排。'], START, END) is None


def test_an_invalid_explicit_year_is_not_treated_as_an_omitted_year():
    assert source_date_outside_window(TITLE, ['会议时间：0000年5月15日。'], START, END) is None


def test_company_name_before_about_is_not_a_half_year_reporting_label():
    assert not title_outside_scope('中国中期关于召开业绩说明会的公告', TARGET)
    assert title_outside_scope('中国中期关于召开半年度业绩说明会的公告', TARGET)
