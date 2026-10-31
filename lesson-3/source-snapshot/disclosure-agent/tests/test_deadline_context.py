"""Synthetic deadline amendments and zero-cost source-context refresh."""
from copy import deepcopy
import hashlib
import json

import pytest

from disclosure_agent import ledger, market, runner, worker
from test_ledger import change, event, notice, run
from test_market_pipeline import environment

HEAD='（二）投资者可于2030年10月30日16:00前登录网站，点击“提问预征集”栏目（https://example.invalid/questions），'
TAIL='根据活动时间，选中本次活动或通过公司邮箱ir@example.invalid向公司提问，公司将在说明会上对投资者普遍关注的问题进行回答。'


def initial():
    return notice(report_period='2030-Q3',meeting_date='2030-11-01',
                  question_deadline_date='2030-10-28',question_deadline_time='16:00')


def amendment(quote=HEAD,**fields):
    return change(report_period='2030-Q3',meeting_date='2030-11-02',
                  question_deadline_date='2030-10-30',question_deadline_time='16:00',
                  deadline_evidence={'page':1,'quote':quote},**fields)


def source(record,text=None):
    return {key:deepcopy(value) for key,value in record.items() if key not in {'extraction','model','revision_reason'}} | {
        'title':'关于延期召开2030年第三季度业绩说明会的公告','pages':[text if text is not None else HEAD+TAIL]}


def cached(tmp_path,record,text=None):
    item=source(record,text)
    receipt=tmp_path/'original-attempt.json';receipt.write_text('{"frozen":"original attempt"}')
    old=deepcopy(record)
    old.update(model_receipts=[{'path':str(receipt),'sha256':hashlib.sha256(receipt.read_bytes()).hexdigest()}],
               extractor_fingerprint='frozen-prompt',extraction_run_id='original-run',source_flags={'other_fields_unchanged':False})
    def forbidden(*a,**k):raise AssertionError('must not call a model')
    def process(previous):
        return worker.process_source(item,previous,{'models':['synthetic'],'report_period':'2030-Q3'},tmp_path/'new-run',
            run_id='today-run',fingerprint='frozen-prompt',remaining=0,extract_fn=forbidden,validate_fn=lambda *a:[])
    return item,old,receipt,process


def test_current_same_period_submission_instruction_updates_deadline_without_change_verb():
    quote='投资者可于2030年10月30日16:00前登录平台，进入公司2030年三季度业绩说明会页面进行提问。'
    state,_,issues=run([initial(),amendment(quote)])
    assert not issues and event(state)['question_deadline_date']=='2030-10-30'
    assert event(state)['pending_fields']=={}


def test_bound_continuous_current_context_is_refreshed_without_model_revision_or_repeated_update(tmp_path):
    record=amendment();item,old,receipt,process=cached(tmp_path,record)
    frozen=deepcopy(old);raw=receipt.read_bytes()
    before,_,issues=run([initial(),old]);assert issues
    result=process(old)
    assert result['status']=='cached_revalidated' and result['attempts']==[] and not result['invalidated']
    refreshed=result['record'];assert refreshed is not None
    context=refreshed['source_flags']['deadline_context']
    assert context['quote'] in item['pages'][0] and '选中本次活动' in context['quote']
    assert context['original_evidence']==old['extraction']['deadline_evidence']
    assert context['source_id']==old['id'] and context['pdf_sha256']==old['pdf_sha256'] and context['page']==1
    assert refreshed['extraction']==old['extraction'] and refreshed['extraction_run_id']=='original-run'
    assert old==frozen and receipt.read_bytes()==raw
    state,changes,issues=run([refreshed],before,as_of='2030-10-31T08:30:00+08:00')
    assert not issues and event(state)['question_deadline_date']=='2030-10-30'
    assert state['notices']['s2']['versions']==[] and changes
    repeated=process(refreshed)
    assert repeated['status']=='cached_revalidated' and repeated['record'] is None
    unchanged,changes,_=run([],state,as_of='2030-11-01T08:30:00+08:00')
    assert not changes and event(unchanged)['activity']==event(state)['activity']


@pytest.mark.parametrize('mutation',['source_id','pdf_sha256','original_evidence','page','quote'])
def test_context_must_be_bound_to_this_source_and_original_evidence(tmp_path,mutation):
    _,old,_,process=cached(tmp_path,amendment())
    record=process(old)['record'];assert record is not None
    context=record['source_flags']['deadline_context']
    if mutation=='original_evidence':context[mutation]={'page':1,'quote':'different original quote'}
    elif mutation=='page':context[mutation]=2
    elif mutation=='quote':context[mutation]=TAIL
    else:context[mutation]='different'
    state,_,issues=run([initial(),record])
    assert issues and event(state)['question_deadline_date']=='2030-10-28'


@pytest.mark.parametrize('quote',[
    '本次说明会回复提问时间调整至2030年10月30日16:00。',
    '原通知规定投资者可于2030年10月30日16:00前登录平台，进入公司2030年三季度业绩说明会页面进行提问。',
    '此前投资者可于2030年10月30日16:00前登录平台选中本次活动进行提问。',
    '投资者可于2030年10月30日16:00前登录提问预征集栏目进行提问。',
    '投资者可于2030年10月30日16:00前登录平台，进入公司2030年半年度业绩说明会页面进行提问。',
])
def test_response_historical_unbound_or_other_period_deadlines_stay_pending(quote):
    state,_,issues=run([initial(),amendment(quote)])
    assert issues and event(state)['question_deadline_date']=='2030-10-28'


def test_other_fields_unchanged_still_blocks_conflicting_current_deadline():
    update=amendment(HEAD+TAIL);update['source_flags']={'other_fields_unchanged':True}
    state,_,issues=run([initial(),update])
    assert event(state)['question_deadline_date']=='2030-10-28'
    assert issues[0]['reason']=='other_fields_unchanged_conflict'


@pytest.mark.parametrize('separator',['。\n','\n\n','\n（三）其他安排：','\f'])
def test_context_extension_cannot_cross_sentence_paragraph_section_or_page(tmp_path,separator):
    _,old,_,process=cached(tmp_path,amendment(),HEAD+separator+TAIL)
    result=process(old);record=result['record'] or old
    state,_,issues=run([initial(),record])
    assert issues and event(state)['question_deadline_date']=='2030-10-28'


def test_current_registration_instruction_keeps_legacy_deadline_role():
    quote='投资者请于2030年10月30日16:00前进入本次业绩说明会页面提交预报名。'
    state,_,issues=run([initial(),amendment(quote)])
    assert not issues and event(state)['question_deadline_date']=='2030-10-30'


def test_reclassifying_ignored_source_is_an_extraction_revision_on_first_display():
    ignored=notice(kind='collective',report_period='2030-Q3')
    previous,_,_=run([ignored],as_of='2030-10-29T08:30:00+08:00')
    assert not previous['events']
    corrected=deepcopy(ignored);corrected['extraction']['notice_kind']='initial'
    state,changes,_=run([corrected],previous,as_of='2030-10-31T08:30:00+08:00')
    activity=event(state)['activity']
    assert activity['kind']=='extraction_revision' and changes[0]['kind']=='extraction_revision'
    assert activity['first_seen_at']=='2030-10-31T08:30:00+08:00'
    assert len(state['notices']['s1']['versions'])==1


def test_q3_briefing_is_not_metadata_excluded_for_collective_reception_words(environment):
    config,workspace,calls=environment
    for row in calls['rows']:
        row['announcementTitle']='关于参加2030年辖区集体接待日暨第三季度业绩网上说明会的公告'
    result=runner.run(config,workspace)
    assert result['market']['metadata_excluded']==0 and result['model_calls']==1
    assert result['event_count']==1


@pytest.mark.parametrize('title',[
    '关于参加2030年辖区上市公司集体接待日的公告',
    '关于召开2030年第三季度业绩说明会的召开情况公告',
])
def test_generic_reception_and_postmeeting_remain_excluded(title):
    assert market._screen_source({'title':title,'pages':['无当前报告期正文']},{'report_period':'2030-Q3'})=='outside_announcement_class'


def test_market_persists_refreshed_flags_from_cached_worker(environment,monkeypatch):
    config,workspace,calls=environment;runner.run(config,workspace);runner.run(config,workspace)
    original=worker.process_source
    def refresh(*args,**kwargs):
        result=original(*args,**kwargs)
        if result['status']=='cached_revalidated':
            result['record']=deepcopy(args[1]);result['record']['source_flags']['synthetic_refresh']=True
        return result
    monkeypatch.setattr(market,'process_source',refresh)
    before=runner.load_state(workspace)
    result=runner.run(config,workspace)
    assert result['model_calls']==0 and not result['changes']
    after=runner.load_state(workspace)
    assert all(row['source_flags'].get('synthetic_refresh') for row in after['notices'].values())
    assert after['events']==before['events']
    assert all(not row['versions'] for row in after['notices'].values())


def test_watchlist_persists_cached_flags_without_revising_extraction(tmp_path,monkeypatch):
    from test_extract_runner import output, HEADER
    data=output();calls=[]
    item={'id':'900001','stock_code':'111111','company':'虚构甲','title':'关于召开2031年半年度业绩说明会的公告',
          'publication_date':'2031-09-01','pdf_sha256':'a'*64,'pages':[HEADER+data['meeting_evidence']['quote']]}
    class Source:
        def __init__(self,*a,**k):pass
        def acquire(self,company,start,end,**kwargs):
            return {'company':company,'status':'complete','query_complete':True,'failed_items':[],'error':None,'query':{},'items':[item]}
    def extraction(*a,**k):
        calls.append(True);receipt=tmp_path/'frozen-receipt.json';receipt.write_text('{"original":true}')
        return {'status':'accepted','data':data,'model':'test/model','attempts':[{'receipt_path':str(receipt),'usage':{'total_tokens':7}}],'errors':[]}
    monkeypatch.setattr(runner,'CninfoSource',Source);monkeypatch.setattr(runner,'extract_notice',extraction)
    config=tmp_path/'watch-config.json';config.write_text(json.dumps({'companies':[{'code':'111111','name':'虚构甲'}],
            'models':['test/model'],'report_period':'2031-H1','strategy':'fixed'}))
    workspace=tmp_path/'watchlist';runner.run(config,workspace)
    before=runner.load_state(workspace);original=worker.process_source
    def refresh(*a,**k):
        result=original(*a,**k)
        if result['status']=='cached_revalidated':
            result['record']=deepcopy(a[1]);result['record']['source_flags']['synthetic_refresh']=True
        return result
    monkeypatch.setattr(worker,'process_source',refresh)
    result=runner.run(config,workspace);after=runner.load_state(workspace)
    assert result['model_calls']==0 and len(calls)==1 and not result['changes']
    assert after['notices']['900001']['source_flags'].get('synthetic_refresh')
    assert after['events']==before['events'] and not after['notices']['900001']['versions']
    assert after['notices']['900001']['extraction_run_id']==before['notices']['900001']['extraction_run_id']


def test_valid_cache_accounts_for_other_matching_started_and_finished_receipts(tmp_path):
    item,old,original_receipt,_=cached(tmp_path,amendment())
    directory=tmp_path/'runs'/'interrupted'/'model-calls'/item['id'];directory.mkdir(parents=True)
    binding=directory.parents[1]/'source-bindings'/(item['id']+'.json');binding.parent.mkdir()
    binding.write_text(json.dumps({'pdf_sha256':item['pdf_sha256'],'extractor_fingerprint':'frozen-prompt'}))
    payload=worker.build_request_payload('synthetic',worker.build_extraction_messages(item))
    base={'model':'synthetic','request':payload,'request_fingerprint':hashlib.sha256(json.dumps(payload,ensure_ascii=False,sort_keys=True).encode()).hexdigest()}
    started=directory/'1-started.json';started.write_text(json.dumps({**base,'status':'started','usage':None}))
    finished=directory/'2-finished.json';finished.write_text(json.dumps({**base,'status':'finished','usage':{'total_tokens':17},
        'response':{'model':'synthetic','choices':[{'finish_reason':'stop','message':{'content':json.dumps(old['extraction'])}}]}}))
    originals={p:p.read_bytes() for p in [original_receipt,started,finished]}
    def forbidden(*a,**k):raise AssertionError('must not call a model')
    def process(previous):
        return worker.process_source(item,previous,{'models':['synthetic'],'report_period':'2030-Q3'},tmp_path/'cache-run',
            run_id='cache-run',fingerprint='frozen-prompt',remaining=0,extract_fn=forbidden,validate_fn=lambda *a:[],
            recovery_paths=[started,finished])
    result=process(old)
    assert result['status']=='cached_revalidated' and result['attempts']==[]
    assert result['unknown_receipts']==[str(started)]
    assert [r['receipt_path'] for r in result['recovered_attempts']]==[str(finished)]
    record=result['record'];assert record['unknown_provider_receipts']==[str(started)]
    assert {r['path'] for r in record['model_receipts']}=={str(p) for p in originals}
    assert record['extraction']==old['extraction'] and record['extraction_run_id']=='original-run'
    repeated=process(record)
    assert repeated['record'] is None and repeated['unknown_receipts']==[str(started)]
    assert all(path.read_bytes()==body for path,body in originals.items())


def test_exact_compatible_cache_keeps_original_prompt_and_records_one_revalidation(tmp_path,monkeypatch):
    item,old,receipt,_=cached(tmp_path,amendment())
    monkeypatch.setattr(worker,'compatible_extraction_contexts',lambda *a:{'frozen-prompt':worker.build_extraction_messages(item)},raising=False)
    def forbidden(*a,**k):raise AssertionError('must not call a model')
    def process(previous,run_id):
        return worker.process_source(item,previous,{'models':['synthetic'],'report_period':'2030-Q3'},tmp_path/run_id,
            run_id=run_id,fingerprint='current-v5',remaining=0,extract_fn=forbidden,validate_fn=lambda *a:[])
    raw=receipt.read_bytes();result=process(old,'first-revalidation')
    assert result['status']=='cached_revalidated' and result['attempts']==[] and not result['invalidated']
    record=result['record'];proof=record['compatible_prompt_revalidation']
    assert record['extractor_fingerprint']=='frozen-prompt' and record['extraction_run_id']=='original-run'
    assert proof=={'source_id':item['id'],'pdf_sha256':item['pdf_sha256'],'old_extractor_fingerprint':'frozen-prompt',
                  'current_extractor_fingerprint':'current-v5','run_id':'first-revalidation'}
    second=process(record,'next-day')
    assert second['status']=='cached_revalidated' and second['record'] is None
    before,_,_=run([initial(),old]);state,_,_=run([record],before)
    assert state['notices']['s2']['compatible_prompt_revalidation']==proof
    assert state['notices']['s2']['extraction_run_id']=='original-run' and not state['notices']['s2']['versions']
    assert receipt.read_bytes()==raw


def test_compatible_recovery_preserves_actual_old_binding_and_all_unknown_receipts(tmp_path,monkeypatch):
    item,old,_,_=cached(tmp_path,amendment())
    old_messages=deepcopy(worker.build_extraction_messages(item));old_messages[0]['content']='Exact frozen old SYSTEM'
    monkeypatch.setattr(worker,'compatible_extraction_contexts',lambda *a:{'frozen-prompt':old_messages},raising=False)
    directory=tmp_path/'runs'/'original-provider-run'/'model-calls'/item['id'];directory.mkdir(parents=True)
    binding=directory.parents[1]/'source-bindings'/(item['id']+'.json');binding.parent.mkdir()
    binding.write_text(json.dumps({'pdf_sha256':item['pdf_sha256'],'extractor_fingerprint':'frozen-prompt','run_id':'original-provider-run'}))
    payload=worker.build_request_payload('synthetic',old_messages)
    base={'model':'synthetic','request':payload,'request_fingerprint':hashlib.sha256(json.dumps(payload,ensure_ascii=False,sort_keys=True).encode()).hexdigest()}
    finished=directory/'1-finished.json';finished.write_text(json.dumps({**base,'status':'finished','usage':{'total_tokens':17},
        'response':{'model':'synthetic','choices':[{'finish_reason':'stop','message':{'content':json.dumps(old['extraction'])}}]}}))
    started=directory/'2-started.json';started.write_text(json.dumps({**base,'status':'started','usage':None}))
    originals={p:p.read_bytes() for p in [finished,started]}
    result=worker.process_source(item,None,{'models':['synthetic'],'report_period':'2030-Q3'},tmp_path/'new-run',
        run_id='new-revalidation-run',fingerprint='current-v5',remaining=0,validate_fn=lambda *a:[],recovery_paths=[finished,started])
    assert result['status']=='recovered_revalidated' and result['attempts']==[]
    record=result['record']
    assert record['extractor_fingerprint']=='frozen-prompt' and record['extraction_run_id']=='original-provider-run'
    assert record['revalidated_by_fingerprint']=='current-v5' and record['revalidation_run_id']=='new-revalidation-run'
    assert record['unknown_provider_receipts']==[str(started)] and len(record['model_receipts'])==2
    assert all(path.read_bytes()==body for path,body in originals.items())


@pytest.mark.parametrize('rejection',['unknown_version','changed_source','current_validation_fails'])
def test_compatibility_never_bypasses_version_source_or_current_validation(tmp_path,monkeypatch,rejection):
    item,old,receipt,_=cached(tmp_path,amendment())
    monkeypatch.setattr(worker,'compatible_extraction_contexts',lambda *a:{'frozen-prompt':worker.build_extraction_messages(item)})
    if rejection=='unknown_version':old['extractor_fingerprint']='unknown-version'
    if rejection=='changed_source':item['pdf_sha256']='different-source-hash'
    def forbidden(*a,**k):raise AssertionError('no request with zero allowance')
    before=receipt.read_bytes()
    result=worker.process_source(item,old,{'models':['synthetic'],'report_period':'2030-Q3'},tmp_path/'run',
        run_id='current',fingerprint='current-v5',remaining=0,extract_fn=forbidden,
        validate_fn=(lambda *a:['unproven_current_purpose']) if rejection=='current_validation_fails' else (lambda *a:[]))
    assert result['status']=='deferred' and result['record'] is None and result['invalidated']
    assert result['attempts']==[] and receipt.read_bytes()==before
