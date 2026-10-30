"""Recover provider receipts at the real worker/queue checkpoint boundary."""
import hashlib
import json
from pathlib import Path

import pytest
from disclosure_agent import extract, worker


@pytest.fixture
def context(tmp_path,monkeypatch):
    data={key:None for key in extract.SCHEMA['required']}
    data.update(notice_kind='initial',report_period='2031-H1',notice_number='2031-001',
                meeting_date='2031-09-20',start_time='14:00',end_time='15:00',review_notes=[],
                meeting_evidence={'page':1,'quote':'会议召开时间：2031年9月20日14:00-15:00'})
    item={'id':'900001','stock_code':'111111','company':'虚构甲','publication_date':'2031-09-01',
          'title':'关于召开2031年半年度业绩说明会的公告','pdf_sha256':'a'*64,
          'pages':['公告编号：2031-001\n'+data['meeting_evidence']['quote']]}
    config={'models':['test/model'],'report_period':'2031-H1'}
    calls=[]
    class Response:
        status_code=200;headers={}
        def __init__(self,value):self.value=value;self.text=json.dumps(self.json())
        def json(self):return {'model':'test/model','choices':[{'finish_reason':'stop','message':{'content':json.dumps(self.value)}}],
                               'usage':{'total_tokens':17}}
        def raise_for_status(self):pass
    def post(*args,**kwargs):calls.append(kwargs['json']);return Response(data)
    monkeypatch.setattr(extract,'credentials',lambda:'unit-test-secret')
    monkeypatch.setattr(extract.requests,'post',post)
    return tmp_path,item,config,data,calls,Response


def invoke(root,item,config,run_id,**kwargs):
    return worker.process_source(item,None,config,root/'runs'/run_id,run_id=run_id,
                                 fingerprint='source-extractor-v1',remaining=2,**kwargs)


def paths(root):return list(root.glob('runs/*/model-calls/900001/*.json'))


def test_finished_call_recovers_after_interrupt_before_queue_checkpoint(context):
    root,item,config,data,calls,_=context
    def interrupted(*args,**kwargs):
        extract.extract_notice(*args,**kwargs)
        raise KeyboardInterrupt('after receipt, before worker return')
    with pytest.raises(KeyboardInterrupt):invoke(root,item,config,'interrupted',extract_fn=interrupted)
    originals={path:hashlib.sha256(path.read_bytes()).hexdigest() for path in paths(root)}
    def forbidden(*a,**k):raise AssertionError('must not repay')
    result=invoke(root,item,config,'restored',extract_fn=forbidden,recovery_paths=paths(root))
    assert result['status']=='recovered_revalidated' and result['attempts']==[] and len(calls)==1
    assert result['record']['extraction']==data
    assert all(hashlib.sha256(path.read_bytes()).hexdigest()==digest for path,digest in originals.items())


def test_started_call_is_unknown_and_does_not_blindly_repay(context,monkeypatch):
    root,item,config,data,calls,_=context
    def interrupted(*args,**kwargs):raise KeyboardInterrupt('request outcome unknown')
    monkeypatch.setattr(extract.requests,'post',interrupted)
    with pytest.raises(KeyboardInterrupt):invoke(root,item,config,'interrupted')
    originals={path:path.read_bytes() for path in paths(root)}
    result=invoke(root,item,config,'restored',recovery_paths=paths(root))
    assert result['status']=='outcome_unknown' and result['errors']==['unfinished_provider_attempt']
    assert result['attempts']==[] and all(path.read_bytes()==value for path,value in originals.items())


def test_invalid_finished_first_call_resumes_with_correction_instead_of_repaying_base(context,monkeypatch):
    root,item,config,data,calls,Response=context
    invalid={**data,'meeting_evidence':{'page':1,'quote':'拼接的错误引文'}}
    def first_call_then_interrupt(item,models,run_dir,**kwargs):
        def post(*args,**kwargs):calls.append(kwargs['json']);return Response(invalid)
        monkeypatch.setattr(extract.requests,'post',post)
        extract.call_model(models[0],extract.build_extraction_messages(item),run_dir/'model-calls'/item['id'])
        raise KeyboardInterrupt('between first validation and corrective request')
    with pytest.raises(KeyboardInterrupt):invoke(root,item,config,'interrupted',extract_fn=first_call_then_interrupt)
    first=paths(root)[0];before=first.read_bytes()
    def correction(*args,**kwargs):calls.append(kwargs['json']);return Response(data)
    monkeypatch.setattr(extract.requests,'post',correction)
    result=invoke(root,item,config,'restored',recovery_paths=paths(root))
    assert result['status']=='accepted' and len(result['attempts'])==1 and len(result['recovered_attempts'])==1
    assert len(calls)==2 and len(calls[0]['messages'])==2 and len(calls[1]['messages'])==4
    assert 'ungrounded_quote' in calls[1]['messages'][-1]['content']
    assert len(result['record']['model_receipts'])==2 and first.read_bytes()==before


@pytest.mark.parametrize('changed', ['pdf','extractor'])
def test_changed_source_or_extractor_cannot_reuse_finished_receipt(context,changed):
    root,item,config,data,calls,_=context
    invoke(root,item,config,'original');originals=paths(root)
    modified={**item,'pdf_sha256':'b'*64} if changed=='pdf' else item
    result=worker.process_source(modified,None,config,root/'runs'/'new',run_id='new',
            fingerprint='changed' if changed=='extractor' else 'source-extractor-v1',remaining=1,recovery_paths=originals)
    assert result['status']=='accepted' and len(calls)==2 and len(result['attempts'])==1


def test_transport_recovers_after_two_timeouts_without_repeating_content_budget(context,monkeypatch):
    root,item,config,data,calls,Response=context
    monkeypatch.setattr(extract.time,'sleep',lambda seconds:None)
    def timeout(*args,**kwargs):calls.append(kwargs['json']);raise extract.requests.Timeout('synthetic provider outage')
    monkeypatch.setattr(extract.requests,'post',timeout)
    first=invoke(root,item,config,'outage')
    assert len(first['attempts'])==2 and first['last_retryable']
    def restored(*args,**kwargs):calls.append(kwargs['json']);return Response(data)
    monkeypatch.setattr(extract.requests,'post',restored)
    second=invoke(root,item,config,'restored',recovery_paths=paths(root))
    assert second['status']=='accepted' and len(second['attempts'])==1 and len(calls)==3


def test_persistent_transport_outage_stops_at_four_actual_requests(context,monkeypatch):
    root,item,config,data,calls,_=context
    monkeypatch.setattr(extract.time,'sleep',lambda seconds:None)
    def timeout(*args,**kwargs):calls.append(kwargs['json']);raise extract.requests.Timeout('synthetic outage')
    monkeypatch.setattr(extract.requests,'post',timeout)
    first=invoke(root,item,config,'one')
    second=invoke(root,item,config,'two',recovery_paths=paths(root))
    third=invoke(root,item,config,'three',recovery_paths=paths(root))
    fourth=invoke(root,item,config,'four',recovery_paths=paths(root))
    assert [len(item['attempts']) for item in [first,second,third,fourth]]==[2,1,1,0]
    assert len(calls)==4 and fourth['status']=='failed'


def test_successful_recovery_also_keeps_another_unknown_paid_attempt(context):
    root,item,config,data,calls,_=context
    invoke(root,item,config,'original')
    original=paths(root)[0]
    receipt=json.loads(original.read_text());receipt.update(status='started',usage=None)
    for key in ['response','raw_response','finished_at','validation_errors','finish_reason']:
        receipt.pop(key,None)
    unknown=original.with_name('99999999-unknown.json');unknown.write_text(json.dumps(receipt))
    originals={path:path.read_bytes() for path in paths(root)}
    result=invoke(root,item,config,'restored',recovery_paths=paths(root))
    assert result['status']=='recovered_revalidated' and len(calls)==1 and result['attempts']==[]
    assert result['unknown_receipts']==[str(unknown)]
    assert result['record']['unknown_provider_receipts']==[str(unknown)]
    assert len(result['record']['model_receipts'])==2
    assert all(path.read_bytes()==body for path,body in originals.items())


def test_new_validator_error_allows_one_new_correction_and_keeps_old_receipts(context, monkeypatch):
    root,item,config,data,calls,_=context
    monkeypatch.setattr(extract, 'validate_evidence', lambda *args: ['old_rule'])
    first = invoke(root,item,config,'old-rule',validate_fn=extract.validate_evidence)
    assert first['status'] == 'failed' and len(calls) == 2
    originals = {path:path.read_bytes() for path in paths(root)}
    monkeypatch.setattr(extract, 'validate_evidence', lambda *args: ['new_rule'])
    second = invoke(root,item,config,'new-rule',validate_fn=extract.validate_evidence,recovery_paths=paths(root))
    assert second['status'] == 'failed' and len(second['attempts']) == 1 and len(calls) == 3
    assert 'new_rule' in calls[-1]['messages'][-1]['content']
    assert '纠正问题签名' in calls[-1]['messages'][-1]['content']
    third = invoke(root,item,config,'same-rule',validate_fn=extract.validate_evidence,recovery_paths=paths(root))
    assert third['attempts'] == [] and len(calls) == 3
    monkeypatch.setattr(extract, 'validate_evidence', lambda *args: ['old_rule'])
    fourth = invoke(root,item,config,'back-to-old',validate_fn=extract.validate_evidence,recovery_paths=paths(root))
    assert fourth['attempts'] == [] and len(calls) == 3
    assert all(path.read_bytes() == before for path,before in originals.items())


def test_error_list_subset_does_not_buy_the_same_correction_twice(context, monkeypatch):
    root,item,config,data,calls,_=context
    monkeypatch.setattr(extract, 'validate_evidence', lambda *args: ['rule_a','rule_b'])
    invoke(root,item,config,'both-errors',validate_fn=extract.validate_evidence)
    assert len(calls) == 2
    monkeypatch.setattr(extract, 'validate_evidence', lambda *args: ['rule_b'])
    result=invoke(root,item,config,'subset',validate_fn=extract.validate_evidence,recovery_paths=paths(root))
    assert result['attempts'] == [] and len(calls) == 2


def test_zero_budget_does_not_consume_a_new_rule_correction(context, monkeypatch):
    root,item,config,data,calls,_=context
    monkeypatch.setattr(extract, 'validate_evidence', lambda *args: ['old_rule'])
    invoke(root,item,config,'old',validate_fn=extract.validate_evidence)
    monkeypatch.setattr(extract, 'validate_evidence', lambda *args: ['new_rule'])
    before = {path:path.read_bytes() for path in paths(root)}
    deferred=worker.process_source(item,None,config,root/'runs'/'no-budget',run_id='no-budget',
        fingerprint='source-extractor-v1',remaining=0,validate_fn=extract.validate_evidence,recovery_paths=paths(root))
    assert deferred['status'] == 'deferred' and deferred['attempts'] == [] and len(calls) == 2
    assert all(path.read_bytes() == body for path,body in before.items())
    result=invoke(root,item,config,'with-budget',validate_fn=extract.validate_evidence,recovery_paths=paths(root))
    assert len(result['attempts']) == 1 and len(calls) == 3


def test_one_bad_content_answer_after_transport_recovery_still_gets_one_correction(context,monkeypatch):
    root,item,config,data,calls,Response=context
    monkeypatch.setattr(extract.time,'sleep',lambda seconds:None)
    def timeout(*args,**kwargs):calls.append(kwargs['json']);raise extract.requests.Timeout('synthetic outage')
    monkeypatch.setattr(extract.requests,'post',timeout)
    invoke(root,item,config,'transport')
    invalid = {**data, 'meeting_evidence': {'page': 1, 'quote': 'not in source'}}
    def invalid_content(*args,**kwargs):calls.append(kwargs['json']);return Response(invalid)
    monkeypatch.setattr(extract.requests,'post',invalid_content)
    result = invoke(root,item,config,'bad-content',recovery_paths=paths(root))
    assert result['status'] == 'failed' and len(result['attempts']) == 1
    def corrected(*args,**kwargs):calls.append(kwargs['json']);return Response(data)
    monkeypatch.setattr(extract.requests,'post',corrected)
    result=invoke(root,item,config,'correct-content',recovery_paths=paths(root))
    assert result['status'] == 'accepted' and len(result['attempts']) == 1 and len(calls) == 4


def test_real_previous_prompt_transport_continues_with_current_binding_and_stops_at_four(context,monkeypatch):
    root,item,config,data,calls,_=context
    current_system = extract.SYSTEM
    old_fingerprint,old_messages = next(iter(extract.compatible_extraction_contexts(item,config['models']).items()))
    current_fingerprint=hashlib.sha256((extract.PROMPT_HASH+json.dumps(config['models'])).encode()).hexdigest()
    monkeypatch.setattr(extract.time,'sleep',lambda seconds:None)
    def timeout(*args,**kwargs):calls.append(kwargs['json']);raise extract.requests.Timeout('synthetic transport')
    monkeypatch.setattr(extract.requests,'post',timeout)
    def process(run_id,fingerprint):
        return worker.process_source(item,None,config,root/'runs'/run_id,run_id=run_id,fingerprint=fingerprint,
                                      remaining=2,recovery_paths=paths(root))
    monkeypatch.setattr(extract,'SYSTEM',old_messages[0]['content'])
    first=process('old-v4',old_fingerprint)
    originals={path:path.read_bytes() for path in paths(root)}
    monkeypatch.setattr(extract,'SYSTEM',current_system)
    second=process('new-v5-a',current_fingerprint)
    third=process('new-v5-b',current_fingerprint)
    fourth=process('new-v5-c',current_fingerprint)
    assert [len(r['attempts']) for r in (first,second,third,fourth)] == [2,1,1,0]
    assert len(calls)==4 and all(c['messages'][0]['content']==current_system for c in calls[2:])
    assert len(fourth['recovered_attempts'])==4
    assert all(path.read_bytes()==body for path,body in originals.items())


def test_real_previous_prompt_started_transport_is_not_hidden_by_new_binding(context,monkeypatch):
    root,item,config,data,calls,Response=context
    current_system=extract.SYSTEM
    old_fingerprint,old_messages=next(iter(extract.compatible_extraction_contexts(item,config['models']).items()))
    current_fingerprint=hashlib.sha256((extract.PROMPT_HASH+json.dumps(config['models'])).encode()).hexdigest()
    monkeypatch.setattr(extract.time,'sleep',lambda seconds:None)
    def timeout(*args,**kwargs):calls.append(kwargs['json']);raise extract.requests.Timeout('synthetic transport')
    monkeypatch.setattr(extract.requests,'post',timeout)
    monkeypatch.setattr(extract,'SYSTEM',old_messages[0]['content'])
    worker.process_source(item,None,config,root/'runs'/'old',run_id='old',fingerprint=old_fingerprint,remaining=2)
    monkeypatch.setattr(extract,'SYSTEM',current_system)
    def interrupted(*args,**kwargs):calls.append(kwargs['json']);raise KeyboardInterrupt('started, outcome unknown')
    monkeypatch.setattr(extract.requests,'post',interrupted)
    with pytest.raises(KeyboardInterrupt):
        worker.process_source(item,None,config,root/'runs'/'new',run_id='new',fingerprint=current_fingerprint,
                              remaining=2,recovery_paths=paths(root))
    originals={path:path.read_bytes() for path in paths(root)}
    def should_not_be_called(*args,**kwargs):calls.append(kwargs['json']);return Response(data)
    monkeypatch.setattr(extract.requests,'post',should_not_be_called)
    result=worker.process_source(item,None,config,root/'runs'/'recover',run_id='recover',fingerprint=current_fingerprint,
                                  remaining=2,recovery_paths=paths(root))
    assert result['status']=='outcome_unknown' and len(result['unknown_receipts'])==1
    assert result['attempts']==[] and len(calls)==3 and calls[-1]['messages'][0]['content']==current_system
    assert all(path.read_bytes()==body for path,body in originals.items())


def test_truncated_last_answer_does_not_hide_an_earlier_answer_with_a_new_rule_error(context,monkeypatch):
    root,item,config,data,calls,Response=context
    monkeypatch.setattr(extract,'validate_evidence',lambda *args:['old_rule'])
    class Truncated(Response):
        def json(self):
            body=super().json();body['choices'][0]['finish_reason']='length';return body
    def first_two(*args,**kwargs):
        calls.append(kwargs['json']);return Response(data) if len(calls)==1 else Truncated(data)
    monkeypatch.setattr(extract.requests,'post',first_two)
    first=invoke(root,item,config,'old-rule',validate_fn=extract.validate_evidence)
    assert len(first['attempts'])==2 and 'incomplete_model_output:length' in first['attempts'][-1]['error']
    originals={path:path.read_bytes() for path in paths(root)}
    monkeypatch.setattr(extract,'validate_evidence',lambda *args:['new_rule'])
    def new_rule(*args,**kwargs):calls.append(kwargs['json']);return Response(data)
    monkeypatch.setattr(extract.requests,'post',new_rule)
    second=invoke(root,item,config,'new-rule',validate_fn=extract.validate_evidence,recovery_paths=paths(root))
    assert len(second['attempts'])==1 and len(calls)==3
    assert 'new_rule' in calls[-1]['messages'][-1]['content']
    third=invoke(root,item,config,'same-rule',validate_fn=extract.validate_evidence,recovery_paths=paths(root))
    assert third['attempts']==[] and len(calls)==3
    assert all(path.read_bytes()==body for path,body in originals.items())
