"""Market discovery and a durable bounded queue around the shared notice worker."""
from concurrent.futures import ThreadPoolExecutor, as_completed, wait, FIRST_COMPLETED
from datetime import date, datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import re
import time
import uuid
from zoneinfo import ZoneInfo
from urllib.parse import urljoin

from .cninfo import CninfoSource, STOCK_URL, STATIC_URL
from .extract import PROMPT_HASH
from .ledger import merge
from .market_source import discover_market
from .scope import period_matches, source_heading_period, title_outside_scope, meeting_window, is_quarterly_briefing, source_date_outside_window, is_update_title
from .worker import process_source

TZ = ZoneInfo('Asia/Shanghai')
TERMINAL = {'accepted', 'excluded_source', 'needs_review'}


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def validate_market_config(config):
    if config.get('strategy','fixed') != 'fixed' or config.get('companies'):
        raise ValueError('全市场使用固定业务流程，不与公司列表混用。')
    if not re.fullmatch(r'\d{4}-Q3',str(config.get('report_period',''))):
        raise ValueError('市场版须明确三季度报告期，如2026-Q3。')
    for key in ('source_start','meeting_start','meeting_end'):
        value=config.get(key)
        if not isinstance(value,str) or date.fromisoformat(value).isoformat()!=value:
            raise ValueError('市场版需要明确日期：'+key)
    if config['meeting_start']>config['meeting_end']:
        raise ValueError('会议日期窗口倒置。')
    for key,default,upper in [('max_source_requests',160,600),('max_downloads',2000,4000),('download_workers',3,3),('model_workers',3,3),('max_transient_attempts',4,8)]:
        value=config.setdefault(key,default)
        if type(value) is not int or not 1<=value<=upper:
            raise ValueError('市场配置超出界限：'+key)
    interval=config.setdefault('source_min_interval',1.4)
    if type(interval) not in (int,float) or not 1.2<=interval<=60:
        raise ValueError('来源请求间隔须在1.2至60秒。')
    return config


def registry(table):
    rows=table.get('stockList') if isinstance(table,dict) else None
    if not isinstance(rows,list):
        raise ValueError('A股身份目录格式错误。')
    all_pairs={(str(row.get('code')),row.get('orgId')):row for row in rows}
    groups={}
    for row in rows:
        if row.get('category')=='A股':
            groups.setdefault(row['orgId'],[]).append(row)
    selected={}
    for org,aliases in groups.items():
        modern=[row for row in aliases if str(row['code']).startswith(('0','3','6','920'))]
        choice=modern if modern else aliases
        selected[org]=choice[0] if len(choice)==1 else None
    return all_pairs,groups,selected


def _load_item(entry):
    path=Path(entry['item_path'])
    if digest(path)!=entry['item_sha256']:
        raise ValueError('候选来源元数据指纹不匹配。')
    item=json.loads(path.read_text())
    pdf=Path(item['pdf_path'])
    if digest(pdf)!=item['pdf_sha256']:
        raise ValueError('候选PDF指纹不匹配。')
    pages_path=Path(item['pages_path'])
    if digest(pages_path)!=item['pages_sha256']:
        raise ValueError('候选逐页文本指纹不匹配。')
    item['pages']=json.loads(pages_path.read_text())
    return item


def _fetch(row, identity, workspace, run_dir):
    source=CninfoSource(workspace,run_dir)
    item=source._pdf(row,identity,run_dir/'source/downloads')
    item['source_stock_code']=row['secCode']
    item['retrieved_at']=datetime.now(TZ).isoformat()
    pages=Path(item['pdf_path']).with_suffix('.pages.json')
    item['pages_path']=str(pages);item['pages_sha256']=digest(pages)
    return item


def _screen_source(item, config):
    from .scope import source_current_period, mentions_period_family
    item.pop('source_scope_proof', None)
    title=item.get('title','')
    if _kind_excluded(title):
        return 'outside_announcement_class'
    if title_outside_scope(title,config['report_period']):
        return 'outside_report_period_in_source'
    period=source_current_period(title,item['pages'])
    if period and not period_matches(period,config['report_period']):
        if mentions_period_family(title + '\n' + '\n'.join(item['pages']), config['report_period']):
            return None
        return 'outside_report_period_in_source'
    if period is None:
        proof=source_date_outside_window(title,item['pages'],config.get('meeting_start'),config.get('meeting_end'))
        if proof and re.fullmatch(r'[0-9a-f]{64}',item.get('pdf_sha256','')):
            item['source_scope_proof']={**proof,'source_pdf_sha256':item['pdf_sha256']}
            return 'meeting_date_outside_window_in_source'
    return None


def _kind_excluded(title):
    if is_update_title(title):
        return False
    return bool(re.search(r'说明会.{0,10}(?:召开情况|举行情况|纪要|活动记录表)', title)
                or re.search(r'说明会情况(?:的)?(?:公告|记录|$)', title)
                or (re.search(r'集体接待', title) and not is_quarterly_briefing(title)))


def _source_review(entry, item, config, reason):
    old=entry.get('record')
    if not old or old['extraction']['notice_kind'] not in {'initial','change','postponed','cancelled'} or (old['extraction'].get('report_period') and not period_matches(old['extraction']['report_period'],config['report_period'])):
        return None
    if old.get('pdf_sha256')!=item['pdf_sha256']:
        return 'source_hash_changed'
    return 'source_scope_conflict' if reason else None


def run_market(config, workspace, trigger='manual', claim_id=None, *, refresh=False):
    from .runner import load_state, publish, write_json, _program_hash

    clock=time.monotonic();started=datetime.now(timezone.utc).isoformat()
    run_id=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S')+'-'+uuid.uuid4().hex[:8]
    run_dir=workspace/'runs'/run_id;run_dir.mkdir(parents=True)
    before_hash=_program_hash();previous=load_state(workspace)
    if previous and previous.get('scope',{}).get('universe')!='a_share':
        raise ValueError('全市场必须使用独立工作区，不能覆盖小样本或重放结果。')
    today=datetime.now(TZ).date().isoformat()
    scope={key:config[key] for key in ('report_period','meeting_start','meeting_end')}
    scope['universe']='a_share'
    queue_path=workspace/'market-queue.json'
    queue=json.loads(queue_path.read_text()) if queue_path.is_file() else {}
    if queue and queue.get('scope')!=scope:
        raise ValueError('市场范围变化需要新工作区，避免旧队列混入。')
    fingerprint=hashlib.sha256((PROMPT_HASH+json.dumps(config['models'])).encode()).hexdigest()
    validation_key=hashlib.sha256((fingerprint+digest(Path(__file__).with_name('extract.py'))+digest(Path(__file__).with_name('scope.py'))).encode()).hexdigest()
    unfinished=any(entry.get('status') not in TERMINAL for entry in queue.get('items',{}).values())
    resume=bool(queue and unfinished and queue.get('day')==today and not refresh and trigger!='scheduler')
    source_workspace=Path(queue['source_workspace']) if resume else workspace/'market-days'/today/run_id
    if not queue:
        source_workspace=workspace
    source_end=today
    refresh_start=(date.fromisoformat(today)-timedelta(days=config['overlap_days'])).isoformat()
    seeds=[]
    if queue and not resume:
        old_path=Path(queue['discovery_path'])
        if digest(old_path)!=queue['discovery_sha256']:
            raise ValueError('前次发现清单指纹不匹配。')
        old_discovery=json.loads(old_path.read_text())
        seeds=sorted({ref['request'] for month in old_discovery['months'].values() for ref in month['query_refs']
                      if ref['end']<refresh_start})
    write_json(run_dir/'start.json',{'run_id':run_id,'mode':'live','trigger':trigger,'config':config,
                                   'scope':scope,'program_sha256':before_hash,'started_at':started})
    discovery=discover_market(source_workspace,run_dir/'discovery',config['source_start'],source_end,
                              seed_roots=seeds,max_requests=config['max_source_requests'],
                              min_interval=config['source_min_interval'])
    if not discovery['query_complete']:
        coverage={code:{'status':'failed','query_complete':False,'processing_complete':False,
                        'announcement_count':0,'query':{'start_date':config['source_start'],'end_date':source_end}}
                  for code in previous.get('companies',{})}
        as_of=datetime.now(TZ).isoformat()
        state,changes,issues=merge(previous,[],coverage,run_id,as_of,report_period=config['report_period'])
        issues.append({'stock_code':'all','source_id':None,'reason':'market_discovery_incomplete','pending':discovery['pending']})
        stats={'stage':'discovery','discovery_complete':False,'source_rows':len(discovery['rows']),
               'pending':None,'needs_review':None,'source_as_of':discovery['as_of'],
               'publication_start':config['source_start'],'publication_end':source_end,
                  'source_checked_at':discovery.get('checked_at'),'source_retrieval_start':discovery.get('retrieval_start'),
                  'source_retrieval_end':discovery.get('retrieval_end'),'source_mode':'frozen_resume' if resume else 'live_refresh'}
        review_candidates=[{**entry.get('source',{'id':key}),'errors':entry.get('errors',[]),'status':'needs_review'}
                           for key,entry in queue.get('items',{}).items() if entry.get('status')=='needs_review']
        state.update(mode='live',scope=scope,last_run_id=run_id,market=stats)
        summary={'run_id':run_id,'status':'incomplete','mode':'live','strategy':'fixed','trigger':trigger,
                 'schedule_claim_id':claim_id,'as_of':as_of,'scope':scope,'market':stats,'coverage':coverage,
                 'changes':changes,'issues':issues,'event_count':len(state.get('events',{})),
                 'model_calls':0,'planner_calls':0,'cached_notice_ids':[],
                 'usage':{'known_total_tokens':0,'calls_with_unknown_usage':0},
                 'started_at':started,'finished_at':datetime.now(timezone.utc).isoformat(),
                 'elapsed_seconds':round(time.monotonic()-clock,3),'program_sha256':before_hash,
                 'prompt_sha256':PROMPT_HASH,'discovery_manifest':discovery['manifest_path']}
        summary['review_candidates']=review_candidates
        if _program_hash()!=before_hash:
            raise RuntimeError('发现期间程序发生修改，未发布；原始响应已保留。')
        return publish(workspace,run_dir,state,summary)
    table_path=workspace/'market-universe/company-table.json'
    if not queue or not resume:
        table_path=run_dir/'source/company-table.json'
        table=CninfoSource(workspace,run_dir)._json('GET',STOCK_URL,table_path)
    else:
        table_path=Path(queue['universe_path'])
        if digest(table_path)!=queue['universe_sha256']:
            raise ValueError('A股目录指纹不匹配。')
        table=json.loads(table_path.read_text())
    pairs,groups,identities=registry(table)
    fresh=bool(queue and not resume)
    entries=queue.get('items',{})
    observed={}
    for row in discovery['rows']:
        pair=pairs.get((str(row.get('secCode')),row.get('orgId')))
        if pair and pair.get('category')=='A股':
            observed.setdefault(row['orgId'],set()).add(str(row['secCode']))
    for org,current in list(identities.items()):
        if current is None and len(observed.get(org,set()))==1:
            code=next(iter(observed[org]));identities[org]=pairs[(code,org)]
    screen_revision=hashlib.sha256((digest(Path(__file__).with_name('scope.py'))+'current-purpose-v2').encode()).hexdigest()
    counts={'source_rows':len(discovery['rows']),'a_share_rows':0,'metadata_excluded':0,
            'non_a_share':0,'identity_review':0,'universe_orgs':len(groups)}
    candidate_rows={};excluded=[]
    for row in discovery['rows']:
        key=str(row['announcementId']);pair=pairs.get((str(row.get('secCode')),row.get('orgId')))
        title=re.sub('<[^>]+>','',row['announcementTitle'])
        source_meta={'id':key,'stock_code':str(row.get('secCode') or ''),'company':row.get('secName') or (pair or {}).get('zwjc') or '公司待确认',
                     'title':title,'date':datetime.fromtimestamp(row['announcementTime']/1000,TZ).date().isoformat(),
                     'url':urljoin(STATIC_URL,row['adjunctUrl']),'report_period':source_heading_period(title)}
        if pair and pair.get('category')!='A股':
            counts['non_a_share']+=1;continue
        if pair:
            counts['a_share_rows']+=1
        kind_excluded=_kind_excluded(title)
        if pair and (title_outside_scope(title,config['report_period']) or kind_excluded):
            counts['metadata_excluded']+=1
            reason='outside_announcement_class' if kind_excluded else 'outside_report_period'
            if key in entries:
                entries[key].pop('source_scope_proof',None)
                record=entries[key].get('record')
                if record and (not record['extraction'].get('report_period') or period_matches(record['extraction']['report_period'],config['report_period'])) and record['extraction']['notice_kind'] not in {'collective','completed','other'}:
                    entries[key].update(status='needs_review',errors=['source_metadata_period_changed'])
                else:
                    entries[key].update(status='excluded_source',reason=reason,errors=[])
                entries[key]['source']=source_meta
            excluded.append({'id':key,'reason':reason,'title':title});continue
        if not pair or row.get('orgId') not in identities or identities[row['orgId']] is None:
            counts['identity_review']+=1
            entry=entries.setdefault(key,{'status':'needs_review','errors':['unresolved_a_share_identity'],'source_id':key})
            entry['source']=source_meta
            continue
        candidate_rows[key]=row
        current=identities[row['orgId']]
        identity={'code':str(current['code']),'name':current['zwjc'],'org_id':row['orgId']}
        stamp=hashlib.sha256(json.dumps(row,ensure_ascii=False,sort_keys=True).encode()).hexdigest()
        entry=entries.setdefault(key,{'status':'fetch_pending','source_id':key,'attempts':[]})
        changed=entry.get('row_sha256')!=stamp
        if changed or (fresh and source_meta['date']>=refresh_start):
            entry['status']='fetch_pending'
        if entry.get('fingerprint')!=fingerprint and entry.get('status') in {'accepted','needs_review','retry_pending'}:
            entry['status']='model_pending' if entry.get('item_path') else 'fetch_pending'
        if entry.get('status')=='needs_review' and entry.get('item_path') and entry.get('failed_fingerprint')!=validation_key:
            entry['status']='model_pending'
        entry.update(row_sha256=stamp,identity=identity,source=source_meta)
        if entry.get('item_path') and entry.get('screen_revision')!=screen_revision and entry['status'] in {'excluded_source','model_pending','needs_review'}:
            try:
                item=_load_item(entry)
                reason=_screen_source(item,config)
                entry.pop('source_scope_proof',None)
                if item.get('source_scope_proof'):entry['source_scope_proof']=item['source_scope_proof']
                review=_source_review(entry,item,config,reason)
                entry.update(status='needs_review' if review else 'excluded_source' if reason else 'model_pending',reason=reason,screen_revision=screen_revision)
                if review:entry.update(errors=[review],failed_fingerprint=validation_key)
                elif reason:entry['errors']=[]
            except Exception as exc:
                entry.update(status='needs_review',errors=['source_integrity: '+str(exc)])
    queue={'version':1,'scope':scope,'day':today,'source_end':source_end,
           'source_workspace':str(source_workspace),'discovery_path':discovery['manifest_path'],
           'discovery_sha256':digest(discovery['manifest_path']),'universe_path':str(table_path),
           'universe_sha256':digest(table_path),'items':entries,'metadata_counts':counts}
    write_json(run_dir/'metadata-exclusions.json',{'items':excluded})
    def checkpoint():
        write_json(queue_path,queue)
    checkpoint()
    fetch_ids=[key for key in candidate_rows if entries[key]['status']=='fetch_pending'][:config['max_downloads']]
    with ThreadPoolExecutor(max_workers=config['download_workers']) as pool:
        futures={pool.submit(_fetch,candidate_rows[key],entries[key]['identity'],workspace,run_dir):key for key in fetch_ids}
        for future in as_completed(futures):
            key=futures[future];entry=entries[key]
            try:
                item=future.result()
                target=workspace/'market-inputs'/(key+'-'+item['pdf_sha256']+'.json')
                metadata={k:v for k,v in item.items() if k!='pages'}
                if target.exists() and json.loads(target.read_text())!=metadata:
                    target=target.with_name(target.stem+'-'+uuid.uuid4().hex[:8]+'.json')
                if not target.exists():write_json(target,metadata)
                old_sha=entry.get('pdf_sha256')
                entry.update(item_path=str(target),item_sha256=digest(target),pdf_sha256=item['pdf_sha256'])
                reason=_screen_source(item,config)
                entry.pop('source_scope_proof',None)
                if item.get('source_scope_proof'):entry['source_scope_proof']=item['source_scope_proof']
                review=_source_review(entry,item,config,reason)
                entry['screen_revision']=screen_revision
                if review:
                    entry.update(status='needs_review',errors=[review],failed_fingerprint=validation_key)
                elif reason:
                    entry.update(status='excluded_source',reason=reason,fingerprint=fingerprint,errors=[])
                elif entry.get('failed_fingerprint')==validation_key and old_sha==item['pdf_sha256']:
                    entry['status']='retry_pending' if entry.get('failure_kind')=='transient' and entry.get('transport_failures',0)<config['max_transient_attempts'] else 'needs_review'
                else:entry['status']='model_pending'
            except Exception as exc:
                entry.update(status='needs_review',errors=['source_download_or_text: '+type(exc).__name__+': '+str(exc)[:300]])
            checkpoint()
    attempts=[];cached=[];records=[];issues=[]
    def run_item(key, allowance):
        entry=entries[key]
        try:
            item=_load_item(entry)
        except Exception as exc:
            return {'status':'source_failed','attempts':[],'record':None,'model':None,'errors':['source_integrity: '+str(exc)]}
        old=entry.get('record') or previous.get('notices',{}).get(key)
        paths=list((workspace/'runs').glob('*/model-calls/'+key+'/*.json'))
        return process_source(item,old,config,run_dir,run_id=run_id,fingerprint=fingerprint,
                              remaining=allowance,recovery_paths=paths)

    def save_outcome(key,outcome, *, persist=True):
        entry=entries[key]
        attempts.extend(outcome['attempts'])
        refs=entry.setdefault('attempts',[])
        for receipt in outcome.get('recovered_attempts',[])+outcome['attempts']:
            if not any(ref['path']==receipt['receipt_path'] for ref in refs):
                refs.append({'path':receipt['receipt_path'],'sha256':digest(receipt['receipt_path'])})
        entry['fingerprint']=fingerprint
        if outcome.get('unknown_receipts'):entry['unknown_receipts']=outcome['unknown_receipts']
        if outcome['status'] in {'accepted','recovered_revalidated'}:
            entry.update(status='accepted',record=outcome['record'],errors=[],transport_failures=0)
            if outcome['status']=='recovered_revalidated':cached.append(key)
        elif outcome['status']=='cached_revalidated':
            cached.append(key);entry['status']='accepted'
            if outcome.get('record'):
                entry['record']=outcome['record']
        elif outcome['status']=='deferred':
            entry['status']='model_pending'
        elif outcome['status']=='outside_report_period':
            entry['status']='excluded_source'
        else:
            transient=bool(outcome.get('last_retryable') or (outcome['attempts'] and outcome['attempts'][-1].get('retryable')))
            failures=max(entry.get('transport_failures',0)+len(outcome['attempts']),len(refs))
            entry.update(status='retry_pending' if transient and failures<config['max_transient_attempts'] else 'needs_review',
                         errors=outcome['errors'],failed_fingerprint=validation_key,transport_failures=failures,
                         failure_kind='transient' if transient else 'content')
            if entry['status']=='retry_pending':
                entry['retry_after']=(datetime.now(TZ)+timedelta(seconds=60)).isoformat()
            if outcome.get('unknown_receipts'):entry['unknown_receipts']=outcome['unknown_receipts']
        if persist:checkpoint()

    ordered=sorted(candidate_rows,key=lambda key:(-candidate_rows[key]['announcementTime'],
                   0 if re.search(r'变更|调整|延期|取消|补充',candidate_rows[key]['announcementTitle']) else 1,key))
    # Validate cache and recover completed calls before reserving any paid budget.
    for key in ordered:
        if entries[key]['status'] in {'accepted','model_pending'}:save_outcome(key,run_item(key,0),persist=False)
        elif entries[key]['status']=='retry_pending' and entries[key].get('retry_after','')<=datetime.now(TZ).isoformat():
            entries[key]['status']='model_pending'
    checkpoint()
    pending=[key for key in ordered if entries[key]['status']=='model_pending']
    position=0
    with ThreadPoolExecutor(max_workers=config['model_workers']) as pool:
        futures={};reserved=0
        allowance=1 if config['max_model_calls']==1 else 2
        while position<len(pending) or futures:
            while position<len(pending) and len(futures)<config['model_workers'] and config['max_model_calls']-len(attempts)-reserved>=allowance:
                key=pending[position];position+=1
                futures[pool.submit(run_item,key,allowance)]=key;reserved+=allowance
            if not futures:break
            finished,_=wait(futures,return_when=FIRST_COMPLETED)
            for future in finished:
                reserved-=allowance
                save_outcome(futures.pop(future),future.result())
    write_json(run_dir/'source-exclusions.json',{'items':[
        {'id':key,'reason':entry.get('reason'),'source':entry.get('source'),
         'proof':entry.get('source_scope_proof')}
        for key,entry in entries.items() if entry['status']=='excluded_source']})
    coverage={}
    for key,entry in entries.items():
        identity=entry.get('identity')
        if not identity:continue
        code=identity['code'];value=coverage.setdefault(code,{'status':'complete','query_complete':discovery['query_complete'],
                'processing_complete':True,'announcement_count':0,'query':{'start_date':config['source_start'],'end_date':source_end},'failed_items':[]})
        value['announcement_count']+=1
        if entry['status'] not in {'accepted','excluded_source'}:
            value['processing_complete']=False
            value['failed_items'].append({'id':key,'status':entry['status'],'errors':entry.get('errors',[])})
        if entry.get('record'):records.append(entry['record'])
        if entry['status']=='needs_review':
            reason=next((error for error in entry.get('errors',[]) if error in {'source_hash_changed','source_scope_conflict'}),'market_source_needs_review')
            issues.append({'stock_code':code,'source_id':key,'reason':reason,'errors':entry.get('errors',[])})
    as_of=datetime.now(TZ).isoformat()
    state,changes,merge_issues=merge(previous,records,coverage,run_id,as_of,report_period=config['report_period'])
    issues.extend(merge_issues)
    for change in changes:
        if change['kind']=='new' and not previous.get('companies',{}).get(change['stock_code'],{}).get('baseline_complete'):
            change['kind']='baseline'
    for code,value in coverage.items():
        if value['query_complete'] and value['processing_complete']:
            state['companies'][code]['baseline_complete']=True
    status_counts={name:sum(entry['status']==name for entry in entries.values()) for name in
                   ['accepted','excluded_source','needs_review','fetch_pending','model_pending','retry_pending']}
    market_stats={**counts,**status_counts,'candidate_queue':len(entries),
                  'pending':status_counts['fetch_pending']+status_counts['model_pending']+status_counts['retry_pending'],
                  'discovery_complete':discovery['query_complete'],'source_as_of':discovery['as_of'],
                  'publication_start':config['source_start'],'publication_end':source_end,
                  'source_checked_at':discovery.get('checked_at'),'source_retrieval_start':discovery.get('retrieval_start'),
                  'source_retrieval_end':discovery.get('retrieval_end'),'source_mode':'frozen_resume' if resume else 'live_refresh'}
    market_stats['outside_window']=sum(meeting_window(event,scope)=='outside' for event in state['events'].values())
    market_stats['unknown_provider_outcomes']=len({path for entry in entries.values() for path in entry.get('unknown_receipts',[])})
    market_stats['calendar_event_count']=sum(meeting_window(event,scope)!='outside' for event in state['events'].values())
    complete=discovery['query_complete'] and not market_stats['pending'] and not status_counts['needs_review'] and not issues
    event_sources={source_id for event in state['events'].values() for source_id in event['source_ids']}
    review_candidates=[]
    for key,entry in entries.items():
        if entry['status']=='needs_review':
            review_candidates.append({**entry.get('source',{'id':key}),
                                      'errors':entry.get('errors',[]),'status':'needs_review'})
    for issue in merge_issues:
        key=str(issue.get('source_id') or '')
        if key and key not in event_sources and key in entries and not any(row['id']==key for row in review_candidates):
            review_candidates.append({**entries[key].get('source',{'id':key}),'errors':[issue['reason']],'status':'needs_review'})
    state.update(mode='live',scope=scope,last_run_id=run_id,market=market_stats)
    receipts=attempts
    summary={'run_id':run_id,'status':'complete' if complete else 'incomplete','mode':'live','strategy':'fixed',
             'trigger':trigger,'schedule_claim_id':claim_id,'scope':scope,'market':market_stats,'as_of':as_of,
             'started_at':started,'finished_at':datetime.now(timezone.utc).isoformat(),
             'elapsed_seconds':round(time.monotonic()-clock,3),'program_sha256':before_hash,'prompt_sha256':PROMPT_HASH,
             'model_calls':len(attempts),'planner_calls':0,'cached_notice_ids':cached,
             'usage':{'known_total_tokens':sum(r['usage']['total_tokens'] for r in receipts if isinstance(r.get('usage'),dict) and isinstance(r['usage'].get('total_tokens'),int)),
                      'calls_with_unknown_usage':sum(not isinstance(r.get('usage'),dict) or not isinstance(r['usage'].get('total_tokens'),int) for r in receipts)},
             'coverage':coverage,'changes':changes,'issues':issues,'event_count':len(state['events']),
             'discovery_manifest':discovery['manifest_path'],'review_candidates':review_candidates,'trace':[]}
    write_json(run_dir/'queue-status.json',market_stats)
    if _program_hash()!=before_hash:
        raise RuntimeError('运行期间程序或提示词发生修改，本次不发布。队列及原始回执已保留。')
    return publish(workspace,run_dir,state,summary)
