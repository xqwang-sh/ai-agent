from copy import deepcopy
import json

import pytest

from disclosure_agent import runner


@pytest.mark.parametrize('status',['incomplete','needs_review'])
def test_render_does_not_turn_unverified_data_into_a_complete_product(tmp_path,monkeypatch,status):
    monkeypatch.setattr(runner,'render_calendar',lambda *args:'<html>synthetic</html>')
    source=tmp_path/'runs/source';source.mkdir(parents=True)
    runner.publish(tmp_path,source,{'last_run_id':'source','events':{}},{'run_id':'source','status':status,'as_of':'2030-10-30T08:30:00+08:00'})
    pointer=(tmp_path/'current.json').read_bytes()
    with pytest.raises(ValueError,match='核验通过'):
        runner.render_saved(tmp_path)
    assert (tmp_path/'current.json').read_bytes()==pointer


def test_render_reads_verified_data_without_refreshing_source_time_or_events(tmp_path,monkeypatch):
    monkeypatch.setattr(runner,'render_calendar',lambda *args:'<html>synthetic</html>')
    source=tmp_path/'runs/source';source.mkdir(parents=True)
    state={'last_run_id':'source','events':{'one':{'meeting_date':'2030-11-02','activity':{'updated_at':'2030-10-30T08:30:00+08:00'}}}}
    summary={'run_id':'source','status':'complete','as_of':'2030-10-30T08:30:00+08:00','model_calls':7,'issues':[],
             'cached_notice_ids':['one'],'usage':{'known_total_tokens':100,'calls_with_unknown_usage':0}}
    runner.publish(tmp_path,source,deepcopy(state),summary)
    old_summary=(source/'summary.json').read_bytes()
    result=runner.render_saved(tmp_path)
    after=runner.load_state(tmp_path)
    assert result['run_id']!='source' and result['as_of']==summary['as_of']
    assert result['model_calls']==0 and result['cached_notice_ids']==[]
    assert result['presentation_origin']['run_id']=='source'
    assert result['presentation_origin']['model_calls']==7
    assert after['events']==state['events'] and (source/'summary.json').read_bytes()==old_summary


def test_real_render_keeps_original_company_identities_and_no_event_companies(tmp_path):
    import re
    source=tmp_path/'runs/source';(source/'source').mkdir(parents=True)
    table={'stockList':[{'code':'600001','zwjc':'合成甲','orgId':'org-real','category':'A股'},
                        {'code':'600002','zwjc':'合成乙无当前会议','orgId':'org-no-event','category':'A股'}]}
    (source/'source/company-table.json').write_text(json.dumps(table))
    event={'id':'one','company':'合成甲','stock_code':'600001','report_period':'2030-Q3','status':'scheduled',
           'meeting_date':'2030-11-02','start_time':'14:00','end_time':'15:00','source_ids':[],
           'pending_fields':{},'history':[],'activity':{}}
    runner.publish(tmp_path,source,{'last_run_id':'source','events':{'one':event},'notices':{}},
                   {'run_id':'source','status':'complete','as_of':'2030-10-30T08:30:00+08:00','issues':[]})
    for _ in range(2):
        result=runner.render_saved(tmp_path)
        html=(tmp_path/'runs'/result['run_id']/'calendar.html').read_text()
        data=json.loads(re.search(r'<script id="calendar-data" type="application/json">(.*?)</script>',html).group(1))
        assert {row['code']:row['org_id'] for row in data['company_directory']['rows']}=={'600001':'org-real','600002':'org-no-event'}
        assert result['presentation_origin']['run_id']=='source'
    pointer=(tmp_path/'current.json').read_bytes()
    (source/'calendar.html').write_text('explicit corruption test')
    with pytest.raises(ValueError,match='identity source'):
        runner.render_saved(tmp_path)
    assert (tmp_path/'current.json').read_bytes()==pointer
