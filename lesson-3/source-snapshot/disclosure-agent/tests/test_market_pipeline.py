"""Synthetic queue tests; no network, provider calls or teacher answers."""
from datetime import datetime as RealDateTime, timezone
import hashlib
import json
from pathlib import Path

import pytest
from pypdf import PdfWriter

from disclosure_agent import market, worker, runner
from disclosure_agent.extract import SCHEMA
from disclosure_agent.presentation import product_data


class Clock(RealDateTime):
    current=RealDateTime(2030,10,30,8,30,tzinfo=timezone.utc)
    @classmethod
    def now(cls,tz=None):
        return cls.current.astimezone(tz) if tz else cls.current.replace(tzinfo=None)


@pytest.fixture
def environment(tmp_path,monkeypatch):
    Clock.current=RealDateTime(2030,10,30,8,30,tzinfo=timezone.utc)
    monkeypatch.setattr(market,'datetime',Clock)
    calls={'model':[],'pdf':[],'discovery':[],'failed':set(),'source_complete':True,'retryable':set()}
    rows=[{'announcementId':str(i),'secCode':code,'secName':name,'orgId':org,
           'announcementTime':int(Clock.current.timestamp()*1000),'announcementTitle':'2030年第三季度业绩说明会',
           'adjunctUrl':f'finalpage/2030-10-30/{i}.PDF'}
          for i,code,name,org in [(101,'111111','虚构甲','org-a'),(202,'222222','虚构乙','org-b')]]
    table={'stockList':[{'code':r['secCode'],'zwjc':r['secName'],'orgId':r['orgId'],'category':'A股'} for r in rows]}
    calls['rows']=rows;calls['table']=table
    def discovery(workspace,run_dir,start,end,**kwargs):
        calls['discovery'].append({'workspace':workspace,'end':end,'seeds':kwargs.get('seed_roots')})
        run_dir.mkdir(parents=True,exist_ok=True)
        result={'query_complete':calls['source_complete'],'rows':rows,'as_of':Clock.now(market.TZ).isoformat(),
                'months':{'2030-09':{'query_refs':[{'request':str(tmp_path/'older.request.json'),'end':'2030-09-30'}]}},
                'pending':[] if calls['source_complete'] else [{'month':'2030-10','reason':'missing_unique_ids'}],
                'manifest_path':str(run_dir/'manifest.json')}
        Path(result['manifest_path']).write_text(json.dumps(result));return result
    class Source:
        def __init__(self,*a,**k): pass
        def _json(self,method,url,path,params=None):
            path.parent.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps(table));return table
    def fetch(row,identity,workspace,run_dir):
        key=str(row['announcementId']);calls['pdf'].append(key)
        path=workspace/'raw'/f'{key}.pdf';path.parent.mkdir(parents=True,exist_ok=True)
        if not path.exists():
            pdf=PdfWriter();pdf.add_blank_page(width=100,height=100)
            with path.open('wb') as f:pdf.write(f)
        text='公告编号：2030-001\n关于召开2030年第三季度业绩说明会\n会议召开时间：2030年11月2日14:00-15:00'
        pages=path.with_suffix('.pages.json');pages.write_text(json.dumps([text]))
        return {'id':key,'stock_code':identity['code'],'company':identity['name'],'org_id':identity['org_id'],
                'title':row['announcementTitle'],'publication_date':'2030-10-30','pdf_url':'https://example.invalid/'+key+'.pdf',
                'pdf_path':str(path),'pdf_sha256':market.digest(path),'pages_path':str(pages),'pages_sha256':market.digest(pages),'pages':[text]}
    def extraction(item,models,run_dir,**kwargs):
        calls['model'].append(item['id']);directory=run_dir/'model-calls';directory.mkdir(exist_ok=True)
        receipt=directory/(item['id']+'.json');receipt.write_text(json.dumps({'synthetic':True}))
        attempt={'receipt_path':str(receipt),'usage':{'total_tokens':13},'retryable':item['id'] in calls['retryable']}
        if item['id'] in calls['failed']:
            return {'status':'failed','data':None,'model':None,'attempts':[attempt],'errors':['synthetic_failed_model']}
        data={key:None for key in SCHEMA['required']}
        data.update(notice_kind='initial',report_period='2030-Q3',notice_number='2030-001',meeting_date='2030-11-02',
                    start_time='14:00',end_time='15:00',review_notes=[],meeting_evidence={'page':1,'quote':'会议召开时间：2030年11月2日14:00-15:00'})
        return {'status':'accepted','data':data,'model':models[0],'attempts':[attempt],'errors':[]}
    monkeypatch.setattr(market,'discover_market',discovery);monkeypatch.setattr(market,'CninfoSource',Source)
    monkeypatch.setattr(market,'_fetch',fetch);monkeypatch.setattr(worker,'extract_notice',extraction)
    config=tmp_path/'config.json'
    config.write_text(json.dumps({'universe':'a_share','report_period':'2030-Q3','meeting_start':'2030-10-01',
        'meeting_end':'2030-11-30','source_start':'2030-01-01','models':['test/model'],'max_model_calls':1}))
    return config,tmp_path/'market-workspace',calls


def test_small_budget_resumes_without_repaying_or_duplicating_events(environment):
    config,workspace,calls=environment
    first=runner.run(config,workspace)
    assert first['status']=='incomplete' and first['model_calls']==1 and first['market']['pending']==1
    assert first['event_count']==1
    second=runner.run(config,workspace)
    assert second['status']=='complete' and second['model_calls']==1 and second['event_count']==2
    original=runner.load_state(workspace)
    third=runner.run(config,workspace)
    assert third['status']=='complete' and third['model_calls']==0 and third['changes']==[]
    assert calls['model']==['101','202'] and len(calls['pdf'])==4
    assert calls['discovery'][0]['workspace']==calls['discovery'][1]['workspace']
    assert calls['discovery'][2]['workspace']!=calls['discovery'][1]['workspace']
    assert runner.load_state(workspace)['events']==original['events']


def test_network_source_recovery_refetches_only_failed_pdf_before_reusing_answer(environment,monkeypatch):
    import requests
    config,workspace,calls=environment
    runner.run(config,workspace);runner.run(config,workspace)
    original=market._fetch
    def broken(row,*args):
        if str(row['announcementId'])=='101':raise requests.ConnectionError('synthetic connection reset')
        return original(row,*args)
    monkeypatch.setattr(market,'_fetch',broken)
    failed=runner.run(config,workspace,refresh=True)
    assert failed['status']=='incomplete'
    calls['pdf'].clear();monkeypatch.setattr(market,'_fetch',original)
    result=runner.run(config,workspace)
    assert result['status']=='complete' and result['model_calls']==0
    assert calls['pdf']==['101']
    assert result['market']['source_mode']=='frozen_resume'
    queue=json.loads((workspace/'market-queue.json').read_text())
    assert queue['items']['101']['status']=='accepted' and queue['items']['101']['errors']==[]


@pytest.mark.parametrize('older_field',[None,'fingerprint','screen_revision'])
def test_unreadable_source_cannot_be_cleared_by_rechecking_its_old_cached_pdf(environment,monkeypatch,older_field):
    config,workspace,calls=environment
    runner.run(config,workspace);runner.run(config,workspace)
    path=workspace/'market-queue.json';queue=json.loads(path.read_text())
    queue['items']['101'].update(status='needs_review',errors=['source_download_or_text: HTTPError: 403 forbidden'])
    if older_field:queue['items']['101'][older_field]='older-version'
    queue['items']['202']['status']='model_pending'
    path.write_text(json.dumps(queue));calls['pdf'].clear()
    result=runner.run(config,workspace)
    assert result['status']=='incomplete'
    queue=json.loads(path.read_text())
    assert queue['items']['101']['status']=='needs_review'
    assert queue['items']['101']['errors']==['source_download_or_text: HTTPError: 403 forbidden']


def test_failed_prefix_does_not_starve_later_records(environment):
    config,workspace,calls=environment;calls['failed'].add('101')
    first=runner.run(config,workspace)
    assert first['market']['needs_review']==1
    second=runner.run(config,workspace)
    assert second['model_calls']==1 and second['event_count']==1
    assert calls['model']==['101','202']
    third=runner.run(config,workspace)
    assert third['model_calls']==0 and third['status']=='incomplete'
    assert calls['model']==['101','202']


def test_incomplete_discovery_pays_nothing_and_keeps_old_events_without_reminders(environment):
    config,workspace,calls=environment;runner.run(config,workspace);runner.run(config,workspace)
    calls['source_complete']=False
    result=runner.run(config,workspace)
    assert result['status']=='incomplete' and result['model_calls']==0 and result['event_count']==2
    assert len(calls['model'])==2
    data=product_data(runner.load_state(workspace),result)
    assert all(not event['reminders'] for event in data['events'])


def test_next_day_refreshes_recent_sources_and_reuses_unchanged_model_extractions(environment):
    config,workspace,calls=environment;runner.run(config,workspace);runner.run(config,workspace)
    old=runner.load_state(workspace)
    Clock.current=RealDateTime(2030,10,31,8,30,tzinfo=timezone.utc)
    result=runner.run(config,workspace)
    assert result['status']=='complete' and result['model_calls']==0
    assert len(calls['pdf'])==4 and len(calls['model'])==2
    assert 'market-days/2030-10-31' in str(calls['discovery'][-1]['workspace'])
    assert calls['discovery'][-1]['seeds'] and calls['discovery'][-1]['end']=='2030-10-31'
    assert runner.load_state(workspace)['events']==old['events']


def test_market_rejects_fixture_and_a_watchlist_workspace(environment):
    config,workspace,calls=environment
    with pytest.raises(ValueError,match='fixture'):
        runner.run(config,workspace,fixture=Path('fictional.json'))
    with pytest.raises(ValueError,match='公司列表'):
        value=json.loads(config.read_text());value['companies']=[{'code':'111111','name':'虚构甲'}]
        config.write_text(json.dumps(value));runner.load_config(config)


def test_next_day_checks_new_sources_even_with_model_backlog(environment):
    config,workspace,calls=environment
    first=runner.run(config,workspace)
    assert first['market']['pending']==1
    Clock.current=RealDateTime(2030,10,31,8,30,tzinfo=timezone.utc)
    second=runner.run(config,workspace)
    assert calls['discovery'][-1]['end']=='2030-10-31'
    assert calls['discovery'][-1]['workspace']!=calls['discovery'][0]['workspace']
    assert second['status']=='complete' and calls['model']==['101','202']


def test_explicit_same_day_refresh_does_not_freeze_source_while_backlogged(environment):
    config,workspace,calls=environment
    runner.run(config,workspace)
    result=runner.run(config,workspace,refresh=True)
    assert result['status']=='complete'
    assert calls['discovery'][-1]['workspace']!=calls['discovery'][0]['workspace']
    assert calls['model']==['101','202']


def test_transient_failure_survives_refresh_then_recovers_after_cooldown(environment):
    config,workspace,calls=environment
    calls['failed'].add('101');calls['retryable'].add('101')
    first=runner.run(config,workspace)
    assert first['market']['retry_pending']==1 and first['market']['needs_review']==0
    second=runner.run(config,workspace,refresh=True)
    assert second['market']['retry_pending']==1 and calls['model']==['101','202']
    calls['failed'].clear()
    Clock.current+=__import__('datetime').timedelta(seconds=61)
    third=runner.run(config,workspace)
    assert third['status']=='complete' and calls['model']==['101','202','101']


def test_transient_retries_stop_at_cumulative_limit(environment):
    config,workspace,calls=environment
    value=json.loads(config.read_text());value['max_transient_attempts']=2;config.write_text(json.dumps(value))
    calls['failed'].add('101');calls['retryable'].add('101')
    runner.run(config,workspace);runner.run(config,workspace)
    Clock.current+=__import__('datetime').timedelta(seconds=61)
    final=runner.run(config,workspace)
    assert final['market']['needs_review']==1 and final['market']['retry_pending']==0
    runner.run(config,workspace)
    assert calls['model']==['101','202','101']


def test_failed_q3_source_is_reviewable_even_without_an_event(environment):
    config,workspace,calls=environment;calls['failed'].add('101')
    result=runner.run(config,workspace)
    data=product_data(runner.load_state(workspace),result)
    assert data['events']==[] and len(data['review_candidates'])==1
    item=data['review_candidates'][0]
    assert item['company']=='虚构甲' and item['url'].endswith('101.PDF')
    assert item['scope_label']=='三季度候选' and '核验' in item['reason']


def test_completed_same_day_refresh_discovers_new_company_without_repaying_old(environment):
    config,workspace,calls=environment
    runner.run(config,workspace);runner.run(config,workspace)
    extra={**calls['rows'][0],'announcementId':'303','secCode':'333333','secName':'虚构丙','orgId':'org-c',
           'adjunctUrl':'finalpage/2030-10-30/303.PDF'}
    calls['rows'].append(extra)
    calls['table']['stockList'].append({'code':'333333','zwjc':'虚构丙','orgId':'org-c','category':'A股'})
    result=runner.run(config,workspace)
    assert result['status']=='complete' and result['event_count']==3 and result['model_calls']==1
    assert calls['model']==['101','202','303']


def test_registry_alias_uses_only_the_one_code_observed_in_official_rows(environment):
    config,workspace,calls=environment
    calls['rows'][0]['secCode']='611111';calls['table']['stockList'][0]['code']='611111'
    calls['table']['stockList'].append({'code':'666666','zwjc':'虚构甲旧代码','orgId':'org-a','category':'A股'})
    result=runner.run(config,workspace)
    assert result['market']['identity_review']==0
    state=runner.load_state(workspace)
    assert next(iter(state['events'].values()))['stock_code']=='611111'


@pytest.mark.parametrize('new_body', ['关于召开2030年半年度业绩说明会。','关于2030年第三季度业绩说明会召开情况的公告。'])
def test_active_pdf_replacement_cannot_be_hidden_by_source_exclusion(environment,monkeypatch,new_body):
    config,workspace,calls=environment
    runner.run(config,workspace);runner.run(config,workspace)
    original_fetch=market._fetch
    def replacement(row,identity,workspace,run_dir):
        item=original_fetch(row,identity,workspace,run_dir)
        if item['id']=='101':
            item['title']='关于业绩说明会的公告'
            path=Path(item['pdf_path']).with_name('replacement.pdf')
            path.write_bytes(Path(item['pdf_path']).read_bytes()+b'\n% controlled source replacement')
            pages=path.with_suffix('.pages.json');pages.write_text(json.dumps([new_body]))
            item.update(pdf_path=str(path),pdf_sha256=market.digest(path),pages_path=str(pages),pages_sha256=market.digest(pages),pages=[new_body])
        return item
    monkeypatch.setattr(market,'_fetch',replacement)
    result=runner.run(config,workspace)
    assert result['status']=='incomplete' and result['model_calls']==0
    assert any(issue['source_id']=='101' and issue['reason']=='source_hash_changed' for issue in result['issues'])
    data=product_data(runner.load_state(workspace),result)
    prior=next(item for item in data['events'] if item['stock_code']=='111111')
    assert prior['reminders']==[] and 'source_hash_changed' in prior['review_reasons']
    assert any(item['id']=='101' for item in data['review_candidates'])


def test_failed_refresh_keeps_existing_unformed_review_candidates(environment):
    config,workspace,calls=environment;calls['failed'].add('101')
    first=runner.run(config,workspace)
    assert len(product_data(runner.load_state(workspace),first)['review_candidates'])==1
    calls['source_complete']=False
    second=runner.run(config,workspace,refresh=True)
    data=product_data(runner.load_state(workspace),second)
    assert len(data['review_candidates'])==1 and data['review_candidates'][0]['id']=='101'
    assert second['model_calls']==0


def add_more_companies(calls):
    for key in (303,404,505):
        code=str(key//101)*6;org='org-'+str(key)
        calls['rows'].append({**calls['rows'][0],'announcementId':str(key),'secCode':code,'orgId':org,'secName':'虚构'+code,
                              'adjunctUrl':f'finalpage/2030-10-30/{key}.PDF'})
        calls['table']['stockList'].append({'code':code,'orgId':org,'zwjc':'虚构'+code,'category':'A股'})


def test_model_workers_refill_without_waiting_for_an_unrelated_slow_request(environment,monkeypatch):
    from threading import Event,Lock
    config,workspace,calls=environment;add_more_companies(calls)
    cfg=json.loads(config.read_text());cfg['max_model_calls']=6;config.write_text(json.dumps(cfg))
    real=worker.extract_notice;release=Event();guard=Lock();active=0;maximum=0
    def extraction(item,*args,**kwargs):
        nonlocal active,maximum
        with guard:active+=1;maximum=max(active,maximum)
        try:
            if item['id']=='101':assert release.wait(3),'worker did not refill after other requests finished'
            if item['id']=='404':release.set()
            return real(item,*args,**kwargs)
        finally:
            with guard:active-=1
    monkeypatch.setattr(worker,'extract_notice',extraction)
    result=runner.run(config,workspace)
    assert result['status']=='complete' and result['model_calls']==5 and maximum<=3


def test_parallel_budget_reserves_the_possible_corrective_call(environment,monkeypatch):
    config,workspace,calls=environment;add_more_companies(calls)
    cfg=json.loads(config.read_text());cfg['max_model_calls']=6;config.write_text(json.dumps(cfg))
    real=worker.extract_notice
    def two_attempts(item,*args,**kwargs):
        value=real(item,*args,**kwargs)
        old=Path(value['attempts'][0]['receipt_path']);other=old.with_name(old.stem+'-first.json')
        other.write_text('{"synthetic_first_failure":true}')
        value['attempts'].insert(0,{'receipt_path':str(other),'usage':{'total_tokens':3}})
        return value
    monkeypatch.setattr(worker,'extract_notice',two_attempts)
    result=runner.run(config,workspace)
    assert result['model_calls']==6 and result['market']['accepted']==3 and result['market']['pending']==2


def test_each_scheduled_market_invocation_refreshes_even_same_day_with_backlog(environment):
    config,workspace,calls=environment
    runner.run(config,workspace)
    runner.run(config,workspace,trigger='scheduler')
    assert calls['discovery'][1]['workspace']!=calls['discovery'][0]['workspace']


def test_market_daily_budget_is_explicit_and_bounded(environment):
    config,workspace,calls=environment
    value=json.loads(config.read_text());value['max_model_calls']=240;config.write_text(json.dumps(value))
    assert runner.load_config(config)['max_model_calls']==240
    value['max_model_calls']=241;config.write_text(json.dumps(value))
    with pytest.raises(ValueError,match='max_model_calls'):runner.load_config(config)
