from copy import deepcopy
import hashlib
import json
import pytest

from disclosure_agent.question_collection import question_collection_range
from disclosure_agent.watchlist import company_directory, directory_for_run


def sample(quote='投资者可于2030年11月18日（星期一）至11月24日（星期日）16:00前登录提问预征集栏目。'):
    event={'status':'scheduled','source_ids':['original'],'question_deadline_date':'2030-11-24','question_deadline_time':'16:00'}
    extraction={'question_deadline_date':'2030-11-24','question_deadline_time':'16:00','deadline_evidence':{'page':2,'quote':quote}}
    notices={'original':{'extraction':extraction,'participation_evidence':[{'page':2,'quote':quote}]}}
    sources=[{'id':'original','participation':[{'page':2,'quote':quote}]}]
    return event,notices,sources


def test_range_is_a_contiguous_physical_page_quote_and_dates_are_not_invented():
    event,notices,sources=sample()
    result=question_collection_range(event,notices,sources)
    assert result['text']=='11月18日至11月24日16:00'
    assert result['quote'] in sources[0]['participation'][0]['quote']
    assert result['source_id']=='original' and result['page']==2
    assert '00:00' not in result['text']


@pytest.mark.parametrize('quote',[
    '提问截止2030年11月24日16:00。',
    '报名时间为2030年11月18日至11月24日16:00。',
    '提问预征集时间为2030年11月25日至11月24日16:00。',
    '提问预征集时间为2030年11月18日至11月24日15:00。',
])
def test_incomplete_unrelated_or_conflicting_ranges_are_not_added(quote):
    assert question_collection_range(*sample(quote)) is None


def test_amendment_never_pairs_original_start_with_new_deadline():
    event,notices,sources=sample()
    event['source_ids'].append('change')
    notices['change']={'extraction':{'question_deadline_date':'2030-11-24','question_deadline_time':'16:00','deadline_evidence':{'page':1,'quote':'提问截止仍为2030年11月24日16:00。'}}}
    sources.append({'id':'change','participation':[{'page':1,'quote':'提问截止仍为2030年11月24日16:00。'}]})
    assert question_collection_range(event,notices,sources) is None


def test_source_mismatch_and_pending_field_block_display_range():
    event,notices,sources=sample()
    sources[0]['participation'][0]['quote']='另一条提问时间2030年11月18日至11月24日16:00。'
    assert question_collection_range(event,notices,sources) is None
    event,notices,sources=sample();event['pending_fields']={'question_deadline_time':[{}]}
    assert question_collection_range(event,notices,sources) is None


def test_company_directory_is_bound_to_saved_source_bytes_and_excludes_other_markets(tmp_path):
    path=tmp_path/'table.json'
    path.write_text(json.dumps({'stockList':[{'category':'A股','code':'001301','zwjc':'合成测试','orgId':'synthetic'}, {'category':'B股','code':'200001'}]}))
    result=company_directory(path,run_id='synthetic-run')
    assert result['rows']==[{'code':'001301','name':'合成测试','org_id':'synthetic'}]
    assert result['source']['sha256']==hashlib.sha256(path.read_bytes()).hexdigest()
    assert result['source']['run_id']=='synthetic-run'
    assert str(path) not in json.dumps(result)


@pytest.mark.parametrize('status', ['complete', 'incomplete'])
def test_resume_or_failed_discovery_retains_verified_full_identity_directory(tmp_path, status):
    original=tmp_path/'runs/original/source/company-table.json';original.parent.mkdir(parents=True)
    original.write_text(json.dumps({'stockList':[{'category':'A股','code':'001301','zwjc':'合成测试','orgId':'actual-org'}]}))
    (tmp_path/'market-queue.json').write_text(json.dumps({'universe_path':str(original),'universe_sha256':hashlib.sha256(original.read_bytes()).hexdigest()}))
    summary={'run_id':'next-run','status':status,'scope':{'universe':'a_share'}}
    result=directory_for_run(tmp_path,summary,{'events':{'synthetic':{'stock_code':'001301','company':'合成测试'}}})
    assert result['source']['complete'] is True and result['source']['bound_run_id']=='next-run'
    assert result['rows'][0]['org_id']=='actual-org'
    original.write_text('{}')
    with pytest.raises(ValueError,match='integrity'):
        directory_for_run(tmp_path,summary,{})


def test_market_directory_is_not_silently_replaced_with_synthetic_identities(tmp_path):
    with pytest.raises(ValueError,match='No verified A-share'):
        directory_for_run(tmp_path,{'run_id':'no-table','scope':{'universe':'a_share'}},{'events':{'x':{}}})
