from copy import deepcopy
import json

from disclosure_agent.scope import source_period, title_outside_scope, scoped_issues
from disclosure_agent.ledger import merge
from disclosure_agent.presentation import product_data
from disclosure_agent.cninfo import CninfoSource, STOCK_URL
from disclosure_agent import runner
from disclosure_agent import scope
from test_ledger import notice, change


def test_reporting_period_variants_and_combined_briefing_have_explicit_year():
    assert source_period('关于2026年三季度网上业绩说明会') == '2026-Q3'
    assert source_period('2026年前三季度业绩说明会') == '2026-Q3'
    assert source_period('2026年半年度暨第三季度业绩说明会') == '2026-H1+2026-Q3'
    assert title_outside_scope('2025年第三季度业绩说明会', '2026-Q3')
    assert not title_outside_scope('2026年半年度暨第三季度业绩说明会', '2026-Q3')
    assert not title_outside_scope('关于调整业绩说明会时间的公告', '2026-Q3')
    assert source_period('三季度业绩说明会') is None


def test_all_explicit_quarter_and_half_year_aliases_are_normalized_without_inventing_year():
    aliases = {'第一季度':'Q1','一季度':'Q1','一季':'Q1','一季报':'Q1',
               '第二季度':'Q2','二季度':'Q2','二季':'Q2','二季报':'Q2',
               '第三季度':'Q3','三季度':'Q3','三季':'Q3','三季报':'Q3','前三季度':'Q3',
               '第四季度':'Q4','四季度':'Q4','四季':'Q4','四季报':'Q4',
               '半年度':'H1','上半年':'H1','中报':'H1','中期':'H1','半年报':'H1',
               '年度':'FY','年报':'FY'}
    for label, period in aliases.items():
        assert source_period('2025年' + label + '业绩说明会') == '2025-' + period
        assert source_period(label + '业绩说明会') is None
    assert title_outside_scope('2025年第四季度业绩说明会', '2026-Q3')
    assert title_outside_scope('2026年第二季度业绩说明会', '2026-Q3')
    assert source_period('2026年半年度暨第三季度业绩说明会') == '2026-H1+2026-Q3'


def test_current_period_does_not_take_a_historical_half_year_from_a_generic_amendment():
    title = '关于业绩说明会时间调整的公告'
    pages = ['公告编号：2026-090\n' + title + '\n本公司曾召开2026年半年度业绩说明会。'
             '现将公告编号2026-080项下业绩说明会调整至11月12日。']
    assert scope.source_current_period(title, pages) is None
    assert scope.source_current_period('关于2026年半年度业绩说明会的公告',
             ['公司拟于11月12日召开2026年第三季度业绩说明会。']) == '2026-H1'


def test_generic_title_uses_the_formal_pdf_heading_or_a_bound_current_meeting_statement():
    title = '关于召开业绩说明会的公告'
    assert scope.source_current_period(title, ['公告编号：2026-001\n甲股份有限公司\n'
        '关于召开2026年半年度暨第三季度\n业绩说明会的公告\n本公司及董事会保证真实。']) == '2026-H1+2026-Q3'
    assert scope.source_current_period(title, ['本公司曾召开2026年半年度业绩说明会。'
        '公司拟于11月12日举办2026年第三季度业绩说明会。']) == '2026-Q3'
    assert scope.source_current_period(title, ['公司将对比2026年半年度报告后召开本次业绩说明会。']) is None
    assert scope.source_current_period(title, ['公司定于2026年11月12日召开第三季度业绩说明会。']) is None


def test_null_period_amendment_links_to_one_original_and_explicit_conflict_stays_reviewed():
    original = notice(report_period='2030-Q3')
    update = change(report_period=None)
    coverage = {'600887':dict(status='complete',query_complete=True,processing_complete=True)}
    first, _, _ = merge({}, [original], coverage, 'first', '2030-10-30')
    state, changes, issues = merge(first, [update], coverage, 'second', '2030-10-31', report_period='2030-Q3')
    assert len(state['events']) == 1 and not issues and len(changes) == 1
    assert state['events']['600887:s1']['report_period'] == '2030-Q3'
    assert state['events']['600887:s1']['meeting_date'] == update['extraction']['meeting_date']
    conflicting = change(report_period='2030-H1')
    state, changes, issues = merge(first, [conflicting], coverage, 'conflict', '2030-10-31')
    assert state['events']['600887:s1']['meeting_date'] == original['extraction']['meeting_date']
    assert not changes and issues[0]['reason'] == 'report_period_conflict'


def mixed():
    h1 = notice('half', report_period='2030-H1')
    q3 = notice('quarter', report_period='2030-Q3')
    coverage = {'600887':dict(status='complete', query_complete=True, processing_complete=True)}
    old, _, _ = merge({}, [h1, q3], coverage, 'old', '2030-10-30T08:30:00+08:00')
    return old, coverage


def test_scope_change_removes_h1_events_and_conflicts_without_deleting_originals():
    old, coverage = mixed()
    update = change(related_notice_number='2030-half', report_period='2030-H1', question_deadline_date='2030-01-31')
    scoped, changes, issues = merge(old, [update], coverage, 'q3', '2030-10-30T09:00:00+08:00', report_period='2030-Q3')
    assert list(scoped['events']) == ['600887:quarter']
    assert 'half' in scoped['notices'] and 's2' in scoped['notices']
    assert not changes and not issues
    assert scoped['events']['600887:quarter']['activity'] == old['events']['600887:quarter']['activity']


def test_incomplete_run_keeps_only_in_scope_old_events():
    old, _ = mixed()
    failed = {'600887':dict(status='failed', query_complete=False, processing_complete=False)}
    state, changes, issues = merge(old, [], failed, 'failure', '2030-10-31', report_period='2030-Q3')
    assert list(state['events']) == ['600887:quarter']
    assert not changes and issues[0]['reason'] == 'company_coverage_incomplete'


def test_product_projection_keeps_q3_source_links_and_does_not_inherit_h1_review():
    old, _ = mixed()
    old['scope'] = {'report_period':'2030-Q3'}
    issues = [{'stock_code':'600887','source_id':'half','event_id':'600887:half','reason':'other_fields_unchanged_conflict'}]
    assert scoped_issues(old, issues, '2030-Q3') == []
    projected = product_data(old, {'as_of':'2030-10-30T09:00:00+08:00','issues':issues})
    assert [event['id'] for event in projected['events']] == ['600887:quarter']
    assert [source['id'] for source in projected['sources']] == ['quarter']
    assert projected['source_count'] == 1
    assert not projected['events'][0]['review_reasons']


def test_combined_briefing_is_one_q3_event_not_an_extra_h1_event():
    source = notice(report_period='2030-H1+2030-Q3')
    state, _, _ = merge({}, [source], {'600887':dict(status='complete',query_complete=True,processing_complete=True)}, 'combined', '2030-10-30', report_period='2030-Q3')
    state['scope'] = {'report_period':'2030-Q3'}
    data = product_data(state, {'as_of':'2030-10-30T09:00:00+08:00'})
    assert len(data['events']) == 1 and data['events'][0]['period'] == '2030年第三季度（合并召开）'


def test_source_does_not_download_explicit_h1_pdf_in_q3_scope(tmp_path, monkeypatch):
    code = '600887'; org = 'fictional-org'
    rows = [{'announcementId':str(i),'secCode':code,'orgId':org,'announcementTitle':title} for i,title in
            [(1,'2030年半年度业绩说明会'),(2,'2030年第三季度业绩说明会')]]
    source = CninfoSource(tmp_path, tmp_path/'run')
    def fake_json(method, url, archive, params=None):
        if url == STOCK_URL:
            return {'stockList':[{'code':code,'zwjc':'虚构公司','orgId':org}]}
        return {'totalAnnouncement':2,'hasMore':False,'announcements':rows}
    seen=[]
    def fake_pdf(row, company, evidence):
        seen.append(row['announcementId']); return {'id':row['announcementId']}
    monkeypatch.setattr(source, '_json', fake_json);monkeypatch.setattr(source, '_pdf', fake_pdf)
    result = source.acquire({'code':code,'name':'虚构公司'},'2030-10-01','2030-10-31',report_period='2030-Q3')
    assert result['status'] == 'complete' and seen == ['2']
    assert result['excluded_items'][0]['id'] == '1'


def test_runner_skips_out_of_scope_before_any_model_call(tmp_path, monkeypatch):
    class Source:
        def __init__(self,*args,**kwargs): pass
        def acquire(self, company, start, end, **kwargs):
            assert kwargs['report_period']=='2030-Q3'
            return {'status':'complete','query_complete':True,'query':{},'failed_items':[],
                    'items':[{'id':'historical','stock_code':company['code'],'title':'2030年半年度业绩说明会','publication_date':'2030-09-01'}]}
    monkeypatch.setattr(runner,'CninfoSource',Source)
    monkeypatch.setattr(runner,'extract_notice',lambda *a,**k: (_ for _ in ()).throw(AssertionError('out-of-scope model call')))
    config=tmp_path/'config.json';config.write_text(json.dumps({'companies':[{'code':'111111','name':'虚构公司'}],'models':['test/model'],'report_period':'2030-Q3'}))
    result=runner.run(config,tmp_path/'workspace')
    assert result['model_calls']==0 and result['event_count']==0 and result['status']=='complete'
    assert result['coverage']['111111']['excluded_items'][0]['id']=='historical'


def test_meeting_date_window_filters_initial_outsiders_but_retains_moved_out_change():
    old,coverage=mixed();event=old['events']['600887:quarter']
    event.update(meeting_date='2030-11-02',start_time='14:00',end_time='15:00')
    old['scope']={'report_period':'2030-Q3','meeting_start':'2030-10-01','meeting_end':'2030-11-30'}
    summary={'as_of':'2030-10-31T08:30:00+08:00'}
    assert len(product_data(old,summary)['events'])==1
    event['meeting_date']='2030-12-02'
    assert not product_data(old,summary)['events']
    event['history']=[{'before':{'meeting_date':'2030-11-02'},'after':{'meeting_date':'2030-12-02'}}]
    data=product_data(old,summary)
    assert data['events'][0]['status']=='outside_window'
    assert not data['events'][0]['reminders']
    assert data['events'][0]['meeting_date']=='2030-12-02'
