"""One source-bound extraction worker shared by watchlists and market batches."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import re

from .extract import build_extraction_messages, build_request_payload, compatible_extraction_contexts, extract_notice, validate_evidence
from .scope import title_outside_scope


def _deadline_context(item, data):
    evidence = data.get('deadline_evidence')
    if data.get('notice_kind') not in {'change', 'postponed'} or not evidence:
        return None
    part = (evidence.get('parts') or [evidence])[-1]
    page_number = part.get('page')
    if type(page_number) is not int or not 1 <= page_number <= len(item['pages']):
        return None
    page = item['pages'][page_number - 1]
    positions = [match.start() for match in re.finditer(r'\S', page)]
    compact = ''.join(page[index] for index in positions)
    quote = re.sub(r'\s+', '', part.get('quote', ''))
    if not quote or compact.count(quote) != 1:
        return None
    index = compact.index(quote)
    start, end = positions[index], positions[index + len(quote) - 1] + 1
    preceding = list(re.finditer(r'\n\s*\n|[。；\f]', page[:start]))
    paragraph_start = preceding[-1].end() if preceding else 0
    if not page[start:end].rstrip().endswith(('。', '；')):
        boundary = re.search(r'[。；\f]|\n\s*\n|(?:^|\n)\s*(?:[一二三四五六七八九十]+[、．.]|[（(][一二三四五六七八九十\d]+[）)]|\d+[、．.])', page[end:])
        if boundary:
            end += boundary.end() if boundary.group() in {'。', '；'} else boundary.start()
        else:
            end = len(page)
    context = page[paragraph_start:end].strip()
    if not context or len(context) > 800:
        return None
    return {'source_id': str(item['id']), 'pdf_sha256': item['pdf_sha256'],
            'page': page_number, 'quote': context, 'original_evidence': deepcopy(evidence)}


def _source_flags(item, data):
    text = re.sub(r'\s+', '', '\n'.join(item['pages']))
    flags = {'other_fields_unchanged': bool(re.search(r'其他.{0,12}(不变|无变|未变)|其余.{0,12}(不变|无变|未变)', text))}
    context = _deadline_context(item, data)
    if context:
        flags['deadline_context'] = context
    return flags


def _record(item, data, model, receipts, fingerprint, run_id, old):
    record = {key:value for key,value in item.items() if key != 'pages'}
    record.update(extraction=data, model=model, extractor_fingerprint=fingerprint,
                  extraction_run_id=run_id, model_receipts=receipts,
                  revision_reason='extraction_revision' if old else 'new_source',
                  source_flags=_source_flags(item, data))
    return record


def _compatible_revalidation(record, item, old_fingerprint, fingerprint, run_id):
    expected = {'source_id':str(item['id']), 'pdf_sha256':item['pdf_sha256'],
                'old_extractor_fingerprint':old_fingerprint, 'current_extractor_fingerprint':fingerprint}
    previous = record.get('compatible_prompt_revalidation') or {}
    if any(previous.get(key) != value for key, value in expected.items()):
        record['compatible_prompt_revalidation'] = {**expected, 'run_id':run_id}


def _recover(item, config, paths, validate, fingerprint, contexts=None):
    contexts = contexts if contexts is not None else {
        fingerprint:build_extraction_messages(item), **compatible_extraction_contexts(item, config['models'])}
    unknown=[];completed=[];accepted=None
    for path in sorted(map(Path, paths), reverse=True):
        try:
            receipt=json.loads(path.read_text())
            model=receipt.get('model')
            if model not in config['models']:
                continue
            if path.parent.name != item['id'] or path.parent.parent.name != 'model-calls':
                continue
            binding_path=path.parents[2]/'source-bindings'/(item['id']+'.json')
            if not binding_path.is_file():
                continue
            binding=json.loads(binding_path.read_text())
            messages=contexts.get(binding.get('extractor_fingerprint'))
            if binding.get('pdf_sha256')!=item['pdf_sha256'] or messages is None:
                continue
            request=receipt.get('request')
            if request:
                expected=hashlib.sha256(json.dumps(request,ensure_ascii=False,sort_keys=True).encode()).hexdigest()
                matching=request.get('model')==model and request.get('messages',[])[:2]==messages and expected==receipt.get('request_fingerprint')
            else:
                payload=build_request_payload(model,messages)
                matching=hashlib.sha256(json.dumps(payload,ensure_ascii=False,sort_keys=True).encode()).hexdigest()==receipt.get('request_fingerprint')
            if not matching:
                continue
            if receipt.get('status')=='started':
                unknown.append(str(path));continue
            receipt['receipt_path']=str(path)
            completed.append(receipt)
            body=receipt.get('response') or {}
            if not isinstance(body,dict) or not isinstance(body.get('choices'),list) or not body['choices'] or not isinstance(body['choices'][0],dict):
                continue
            choice=body['choices'][0]
            if receipt.get('error') or body.get('model')!=model or choice.get('finish_reason')!='stop':
                continue
            data=json.loads(choice['message']['content'])
            if not isinstance(data,dict) or validate(data,item['pages'],item):
                continue
            if accepted is None:
                accepted={'data':data,'model':model,'path':str(path),'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),
                          'extractor_fingerprint':binding.get('extractor_fingerprint'),'extraction_run_id':binding.get('run_id')}
        except (OSError,ValueError,KeyError,IndexError,TypeError):
            continue
    return accepted, unknown, sorted(completed,key=lambda receipt:receipt['receipt_path'])


def process_source(item, old, config, run_dir, *, run_id, fingerprint, remaining,
                   extract_fn=None, validate_fn=None, recovery_paths=()):
    outcome = {'status':None, 'attempts':[], 'record':None, 'errors':[], 'invalidated':False, 'model':None}
    if title_outside_scope(item.get('title',''), config.get('report_period')):
        return {**outcome, 'status':'outside_report_period'}
    validate=validate_fn or validate_evidence
    errors = validate(old['extraction'], item['pages'], item) if old and old.get('extraction') else []
    receipts = (old or {}).get('model_receipts', [])
    intact = bool(receipts) and all(Path(r['path']).is_file() and hashlib.sha256(Path(r['path']).read_bytes()).hexdigest()==r['sha256'] for r in receipts)
    same_source = bool(old and old.get('pdf_sha256') == item['pdf_sha256'])
    contexts = {fingerprint:build_extraction_messages(item), **compatible_extraction_contexts(item, config['models'])}
    same_extractor = bool(old and old.get('extractor_fingerprint') in contexts)
    outcome['invalidated'] = bool(old and (errors or not intact or not same_source or not same_extractor))
    recovered,unknown,completed=_recover(item,config,recovery_paths,validate,fingerprint,contexts) if recovery_paths else (None,[],[])
    outcome.update(recovered_attempts=completed, unknown_receipts=unknown)
    if config.get('reuse_extractions', True) and same_source and same_extractor and not errors and intact:
        flags = deepcopy(old.get('source_flags', {}))
        flags.pop('deadline_context', None)
        flags.update(_source_flags(item, old['extraction']))
        record = deepcopy(old)
        record['source_flags'] = flags
        if old.get('extractor_fingerprint') != fingerprint:
            _compatible_revalidation(record,item,old.get('extractor_fingerprint'),fingerprint,run_id)
        refs = record['model_receipts']
        for path in sorted(set([receipt['receipt_path'] for receipt in completed] + unknown)):
            if not any(ref['path'] == path for ref in refs):
                refs.append({'path':path,'sha256':hashlib.sha256(Path(path).read_bytes()).hexdigest()})
        if unknown or 'unknown_provider_receipts' in record:
            record['unknown_provider_receipts'] = unknown
        return {**outcome, 'status':'cached_revalidated', 'record':record if record != old else None,
                'recovered_attempts':completed, 'unknown_receipts':unknown}
    if recovered:
        ref={key:recovered[key] for key in ('path','sha256')}
        all_paths=sorted(set([receipt['receipt_path'] for receipt in completed]+unknown))
        refs=[{'path':path,'sha256':hashlib.sha256(Path(path).read_bytes()).hexdigest()} for path in all_paths]
        record=_record(item,recovered['data'],recovered['model'],refs,recovered['extractor_fingerprint'],recovered['extraction_run_id'],old)
        record.update(revalidated_by_fingerprint=fingerprint,revalidation_run_id=run_id)
        if recovered['extractor_fingerprint'] != fingerprint:
            _compatible_revalidation(record,item,recovered['extractor_fingerprint'],fingerprint,run_id)
        record['unknown_provider_receipts']=unknown
        record['revalidated_from_receipt']=ref
        directory=Path(run_dir)/'receipt-revalidation';directory.mkdir(parents=True,exist_ok=True)
        target=directory/(item['id']+'-'+ref['sha256']+'.json')
        target.write_text(json.dumps({'source_id':item['id'],'source_pdf_sha256':item['pdf_sha256'],
                                     'receipt':ref,'run_id':run_id,'status':'revalidated',
                                     'original_extractor_fingerprint':recovered['extractor_fingerprint'],
                                     'original_extraction_run_id':recovered['extraction_run_id'],
                                     'revalidated_by_fingerprint':fingerprint,
                                     'original_attempt_unchanged':True,'all_receipts':refs,
                                     'unknown_provider_receipts':unknown},ensure_ascii=False,indent=2))
        return {**outcome,'status':'recovered_revalidated','record':record,'model':recovered['model'],
                'recovered_attempts':completed,'unknown_receipts':unknown}
    if unknown:
        return {**outcome,'status':'outcome_unknown','errors':['unfinished_provider_attempt'],'unknown_receipts':unknown}
    if remaining <= 0:
        return {**outcome, 'status':'deferred', 'errors':['model_budget_exhausted']}
    from .runner import write_json
    write_json(Path(run_dir)/'source-bindings'/(item['id']+'.json'),
               {'id':item['id'],'pdf_sha256':item['pdf_sha256'],'extractor_fingerprint':fingerprint,
                'run_id':run_id,'source_path':item.get('pdf_path')})
    extra={'recovered_attempts':completed,'max_transient_attempts':config.get('max_transient_attempts',4)} if completed else {}
    result = (extract_fn or extract_notice)(item, config['models'], run_dir, max_calls=remaining, **extra)
    outcome.update(attempts=result['attempts'], model=result['model'], errors=result['errors'])
    outcome['recovered_attempts']=result.get('reused_attempts',[])
    outcome['last_retryable']=result.get('last_retryable',False)
    if result['status'] != 'accepted':
        return {**outcome, 'status':'failed'}
    refs=[{'path':r['receipt_path'],'sha256':hashlib.sha256(Path(r['receipt_path']).read_bytes()).hexdigest()} for r in result.get('reused_attempts',[])+result['attempts']]
    return {**outcome,'status':'accepted','record':_record(item,result['data'],result['model'],refs,fingerprint,run_id,old)}
