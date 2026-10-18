"""Run public synthetic checks against the learner's production modules."""
from .offline_guard import install
install()  # Before importing learner code, discovering tests or starting workers.
import argparse
from copy import deepcopy
import hashlib
import importlib
import json
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import unittest
import zipfile
from .fixtures import observation, swapped, selection, reference, script, write_pdf, PAGES, alternate, alternate_reference, run_selection, RUN_PAGES, COMPANY, TEXT, income_envelope

SUBJECT = None
PROJECT = None
THROUGH = 8
OUTPUT = None

def load(path):
    return json.loads(Path(path).read_text())

def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def text_leaves(value):
    if isinstance(value,str):
        try:parsed=json.loads(value)
        except (ValueError,TypeError):return [value]
        if parsed==value:return [value]
        return text_leaves(parsed)
    if isinstance(value,list):return [item for part in value for item in text_leaves(part)]
    if isinstance(value,dict):return [item for part in value.values() for item in text_leaves(part)]
    return []

class Acceptance(unittest.TestCase):
    def test_00_offline_parent_and_child(self):
        from .offline_guard import OfflineNetworkError
        with self.assertRaises(OfflineNetworkError):
            socket.create_connection(('203.0.113.1',443),timeout=0.1)
        r=subprocess.run([sys.executable,'-c',"import socket; socket.create_connection(('203.0.113.1',443),timeout=.1)"],capture_output=True,text=True)
        self.assertNotEqual(r.returncode,0)
        self.assertIn('offline acceptance blocked',r.stderr)
        with self.assertRaises(OfflineNetworkError):
            subprocess.run(['hithink-finance','symbol','search','--keyword','synthetic'])

    def test_05_exact_source_and_context(self):
        good=observation()
        result=SUBJECT.validate(good,PAGES,[1])
        self.assertTrue(result['passed'],result)
        self.assertEqual(len(result['bound_rows']),5)
        other=deepcopy(good);other['company']='另一家公司'
        self.assertFalse(SUBJECT.validate(other,PAGES,[1],expected_company=COMPANY)['passed'])
        context=deepcopy(good);context['current_column_evidence'][0]['quote']='合并利润表\n2026年1-6月'
        self.assertTrue(SUBJECT.validate(context,PAGES,[1])['passed'])
        for quote in ('2026年1-6月合并','本期金额：2026年1-6月（合并）'):
            pages=deepcopy(PAGES);pages[0]['text']=pages[0]['text'].replace('2026年1-6月',quote)
            context=deepcopy(good);context['current_column_evidence'][0]['quote']=quote
            self.assertTrue(SUBJECT.validate(context,pages,[1])['passed'])
        bads=[]
        for raw in ('0.8','8','0.830','-0.83','(0.83)'):
            x=deepcopy(good);x['rows'][-1]['current']=raw;bads.append(('numeric boundary '+raw,x))
        x=deepcopy(good);x['rows'][0]['original_label']='营业总收入';x['rows'][0]['current']='120';x['rows'][0]['prior']='115';bads.append(('total revenue',x))
        x=deepcopy(good);x['rows'][1]['original_label']='营业总成本';x['rows'][1]['current']='90';x['rows'][1]['prior']='80';bads.append(('total cost',x))
        x=deepcopy(good);x['current_column_path']=['2026年合并半年累计'];x['current_column_evidence']=[{'page':1,'quote':'2026年合并半年累计'}];bads.append(('invented header',x))
        x=deepcopy(good);x['current_column_path']=['2026年虚构半年列'];x['current_column_evidence']=[{'page':1,'quote':''}];bads.append(('empty citation cannot prove invented header',x))
        x=deepcopy(good);x['current_column_path']=['2026年1-6月虚构分组'];bads.append(('short quote cannot prove longer header',x))
        x=deepcopy(good);x['prior_column_evidence']=[{'page':1,'quote':'2025'}];bads.append(('year alone cannot prove full H1 component',x))
        x=deepcopy(good);x['current_column_path']=['2026年4-6月'];x['current_column_evidence']=[{'page':1,'quote':'2026年4-6月'}];bads.append(('Q2-only',x))
        x=deepcopy(good);x['scope_evidence']={'page':1,'quote':'公司利润表'};bads.append(('parent scope',x))
        x=deepcopy(good);del x['scope_evidence'];bads.append(('missing scope',x))
        x=deepcopy(good);x['rows'][-1]['unit']='万元';bads.append(('EPS amount unit',x))
        x=deepcopy(good);x['rows'][0]['current']='11';bads.append(('borrow parent-profit value for revenue',x))
        x=deepcopy(good);x['rows'][2]['current']='66';bads.append(('borrow cost value for operating profit',x))
        x=deepcopy(good);x['rows'][-1]['unit_quote']='单位：万元';bads.append(('amount header cannot prove EPS unit',x))
        for label,x in bads:
            with self.subTest(label=label):
                result=SUBJECT.validate(x,PAGES,[1]);self.assertFalse(result['passed'],result);self.assertTrue(result['rules'])
        self.assertFalse(SUBJECT.validate(good,PAGES,[])['passed'])
        for fragment in ('0 .83','0. 83'):
            pages=deepcopy(PAGES);pages[0]['text']=pages[0]['text'].replace('0.83',fragment)
            self.assertFalse(SUBJECT.validate(good,pages,[1])['passed'])
        for sign in ('+', '−', '－'):
            with self.subTest(source_sign=sign):
                pages=deepcopy(PAGES);pages[0]['text']=pages[0]['text'].replace('0.83',sign+'0.83')
                self.assertFalse(SUBJECT.validate(good,pages,[1])['passed'])
                signed=deepcopy(good);signed['rows'][-1]['current']=sign+'0.83'
                self.assertTrue(SUBJECT.validate(signed,pages,[1])['passed'])
        with self.subTest(ungrouped_long_integer=True):
            pages=deepcopy(PAGES);pages[0]['text']=pages[0]['text'].replace('营业收入 110 100','营业收入 1234567 100')
            large=deepcopy(good);large['rows'][0]['current']='1234567'
            self.assertTrue(SUBJECT.validate(large,pages,[1])['passed'])
        with self.subTest(ambiguous_duplicate_row=True):
            pages=deepcopy(PAGES);pages[0]['text']+='\n营业收入 110 100'
            self.assertFalse(SUBJECT.validate(good,pages,[1])['passed'])
        for quote in ('单位：人民币万元','除另有注明外，金额单位均为人民币万元','除基本每股收益外，金额单位为人民币万元'):
            with self.subTest(amount_unit_expression=quote):
                pages=deepcopy(PAGES);pages[0]['text']=pages[0]['text'].replace('单位：万元',quote)
                x=deepcopy(good)
                for row in x['rows'][:-1]:row['unit_quote']=quote
                self.assertTrue(SUBJECT.validate(x,pages,[1])['passed'])
        with self.subTest(per_share_header_is_not_amount_unit=True):
            quote='基本每股收益单位：元/股';pages=deepcopy(PAGES);pages[0]['text']+='\n'+quote
            self.assertTrue(SUBJECT.validate(good,pages,[1])['passed'])
            x=deepcopy(good);x['rows'][0]['unit']='元';x['rows'][0]['unit_quote']=quote
            self.assertFalse(SUBJECT.validate(x,pages,[1])['passed'])
        # Precision must bind the longest source token, including trailing zeros.
        pages=deepcopy(PAGES);pages[0]['text']=pages[0]['text'].replace('0.83','0.830')
        self.assertFalse(SUBJECT.validate(good,pages,[1])['passed'])
        x=deepcopy(good);x['rows'][-1]['current']='0.830'
        self.assertTrue(SUBJECT.validate(x,pages,[1])['passed'])

    def test_05_one_dispatcher(self):
        seq=[{'action':'search_fulltext','query':'合并利润表','offset':0},{'action':'read_pages','pages':[1]},
             {'action':'select_pages','selection':selection()},{'action':'submit','observation':observation()}]
        r=SUBJECT.dispatch(seq,PAGES,'extract')
        self.assertEqual(r['trace'],['search_fulltext','read_pages','select_pages','submit'])
        self.assertEqual(r['candidate_count'],1);self.assertEqual(r['source_actions'],3);self.assertEqual(r['failures'],[])
        for seq,phase in [([{'action':'submit','observation':observation()}],'locate'),([{'action':'invent'}],'extract'),([{'rows':[]}],'extract')]:
            r=SUBJECT.dispatch(seq,PAGES,phase);self.assertTrue(r['failures']);self.assertEqual(r['candidate_count'],0)
        self.assertEqual(SUBJECT.dispatch([selection()],PAGES,'locate')['trace'],['select_pages'])
        self.assertEqual(SUBJECT.dispatch([observation()],PAGES,'extract')['candidate_count'],1)

    def test_06_two_layers_and_precision(self):
        def compare(text,vision,ref,pages):
            return SUBJECT.compare(text,vision,ref,pages,expected_thscode='000001.SZ',expected_company=COMPANY)
        r=compare(observation(),observation(),reference(),PAGES)
        for gate in ('internal','external'):
            self.assertTrue(r[gate]['passed'],r);self.assertEqual(r[gate]['matched'],10)
        self.assertTrue(compare(observation(),observation(),income_envelope(reference()),PAGES)['external']['passed'])
        for field,value in (('ok',False),('ok','true'),('command','financials.cashflow'),('period','annual')):
            ref=income_envelope(reference())
            if field=='period':ref['data']['item'][0]['period']=value
            else:ref[field]=value
            with self.subTest(cli_contract=(field,value)):
                self.assertFalse(compare(observation(),observation(),ref,PAGES)['external']['passed'])
        other=observation();other['company']='另一家公司'
        self.assertFalse(compare(other,other,reference(),PAGES)['internal']['passed'])
        wrong=observation();wrong['current_column_path']=['invented'];wrong['current_column_evidence']=[{'page':1,'quote':'invented'}]
        r=compare(observation(),wrong,reference(),PAGES)
        self.assertFalse(r['internal']['passed'])
        r=compare(swapped(),swapped(),reference(),PAGES)
        self.assertFalse(r['external']['passed'])
        feedback=json.dumps(r.get('feedback',{}),ensure_ascii=False)
        self.assertNotIn('1100000',feedback);self.assertNotIn('expected',feedback);self.assertNotIn('difference',feedback)
        # Source integer 110万元, external value rounds with source precision.
        for raw,passed in [('1104999',True),('1105000',False)]:
            ref=reference();ref['records'][0]['operating_income']=raw
            r=compare(observation(),observation(),ref,PAGES)
            self.assertEqual(r['external']['passed'],passed,r)
        ref=reference();ref['records']=ref['records'][:1]
        self.assertFalse(compare(observation(),observation(),ref,PAGES)['external']['passed'])

        for field,value in (('thscode','999999.SH'),('record_thscode','999999.SH'),('period_end','2025-06-30')):
            ref=reference()
            if field=='thscode':ref[field]=value
            elif field=='record_thscode':ref['records'][0]['thscode']=value
            else:ref['records'][0][field]=value
            with self.subTest(reference_identity_or_date=field):
                self.assertFalse(compare(observation(),observation(),ref,PAGES)['external']['passed'])

    def test_07_lifetime_progress(self):
        events=[{'event':'gate','gate':'source','rules':[],'candidate':'a'},
                {'event':'gate','gate':'internal','rules':['value:basic_eps:current'],'candidate':'a'},
                {'event':'candidate_changed','candidate':'b'},
                {'event':'gate','gate':'source','rules':[],'candidate':'b'},
                {'event':'gate','gate':'internal','rules':['value:basic_eps:current'],'candidate':'b'}]
        r=SUBJECT.progress(events)
        self.assertTrue(r['stopped'],r);self.assertEqual(r['counters']['failed_gate_evaluations'],2)
        self.assertEqual(r['counters']['feedback_emitted'],1)
        self.assertEqual(r['snapshots'][-1]['no_progress'],2)
        self.assertTrue(r['snapshots'][-1]['ever_passed']['source'])
        events=[{'event':'gate','gate':'source','rules':['a','b'],'candidate':'a'},
                {'event':'candidate_changed','candidate':'b'},
                {'event':'gate','gate':'source','rules':['a'],'candidate':'b'}]
        r=SUBJECT.progress(events);self.assertFalse(r['stopped']);self.assertEqual(r['snapshots'][-1]['no_progress'],0)
        events=[{'event':'request_reserved','id':'1'}, {'event':'request_finished','id':'1','usage':None}, {'event':'request_reserved','id':'2'}]
        r=SUBJECT.progress(events);self.assertTrue(r['stopped']);self.assertIn('unknown',r['reason'])

    def run_case(self,name,after_create=None):
        folder=OUTPUT/name;folder.mkdir(parents=True,exist_ok=True)
        scenario=script(name)
        pdf=folder/'synthetic.pdf';write_pdf(pdf);scenario['pdf_path']=str(pdf)
        if name=='combined':
            good,revised=observation(),alternate();invalid=deepcopy(good);invalid['rows'][-1]['unit_quote']='没有这段单位'
            seq=scenario['model_script'][:3]+[
                {'stage':'extract','response':{'action':'submit','observation':invalid}},
                {'stage':'extract','response':{'action':'search_fulltext','query':'基本每股收益','offset':0}},
                {'stage':'extract','response':{'action':'submit','observation':good}},
                {'stage':'vision','response':good},
                {'stage':'extract','response':{'action':'read_pages','pages':[1]}},
                {'stage':'extract','response':{'action':'submit','observation':revised}},
                {'stage':'vision','response':revised}]
            scenario['model_script']=seq
            scenario['reference_script']=[alternate_reference(),alternate_reference()]
        if name=='no_progress':
            a=observation();b=deepcopy(a);b['rows'][0]['unit_quote']='万元'
            scenario['model_script']=[{'stage':'locate','response':run_selection()},
                {'stage':'extract','response':a},{'stage':'vision','response':alternate()},
                {'stage':'extract','response':b},{'stage':'vision','response':alternate()}]
            scenario['reference_script']=[]
        for i,item in enumerate(scenario['model_script']):
            item.update(id=f'{name}-{i+1}',usage={'prompt_tokens':100,'completion_tokens':10,'total_tokens':110})
        from .services import run_with_services
        result, services=run_with_services(SUBJECT,scenario,folder/'run',after_create)
        (folder/'transport-receipts.json').write_text(json.dumps(services,ensure_ascii=False,indent=2))
        self.assertTrue(Path(result['task_dir']).is_dir())
        state=load(result['state_file']);trace=load(result['trace_file']);ledger=load(result['ledger_file'])
        program=Path(result['task_dir'])/'program'
        requests=trace['requests'];self.assertEqual(len(requests),len(ledger['requests']))
        self.assertEqual(len(requests),len(services['model_receipts']))
        self.assertEqual(ledger['total_tokens'],len(requests)*110)
        for i,(req,receipt) in enumerate(zip(requests,services['model_receipts'])):
            self.assertEqual(req['request_id'],ledger['requests'][i]['request_id'])
            actual=load(req['request_path']);response=load(req['response_path'])
            self.assertEqual(response['usage']['total_tokens'],110)
            self.assertEqual(actual['messages'],receipt['request']['messages'])
            self.assertEqual(response,receipt['response'])
            self.assertEqual(req['stage'],receipt['expected_stage'])
            self.assertEqual(response['id'],receipt['script_id'])
            self.assertIn((program/'prompts/runtime'/f"{req['stage']}.md").read_text(),actual['messages'][0]['content'])
        from pypdf import PdfReader
        actual_text={i+1:p.extract_text() for i,p in enumerate(PdfReader(str(pdf)).pages)}
        text_requests=[req for req in requests if req['stage'] in ('locate','extract')]
        for before,after in zip(text_requests,text_requests[1:]):
            reply=json.loads(load(before['response_path'])['choices'][0]['message']['content'])
            action=reply.get('action') if isinstance(reply,dict) else None
            if action is None and isinstance(reply,dict) and 'anchors' in reply:action='select_pages';reply={'selection':reply}
            if action not in ('search_fulltext','read_pages','select_pages'):continue
            previous=load(before['request_path'])['messages'];following=load(after['request_path'])['messages']
            self.assertEqual(before['session_id'],after['session_id'])
            prior_history=[m for m in previous if m['role']!='system']
            next_history=[m for m in following if m['role']!='system']
            self.assertEqual(next_history[:len(prior_history)],prior_history)
            users=[m['content'] for m in next_history[len(prior_history):] if m['role']=='user']
            delivered='\n'.join(text_leaves(users))
            if action=='search_fulltext':
                self.assertIn(reply['query'],delivered)
                self.assertIn('physical_page',json.dumps(users,ensure_ascii=False))
            elif action=='read_pages':
                for page in reply['pages']:self.assertIn(actual_text[page].strip(),delivered)
            else:
                self.assertTrue(any(label in json.dumps(users,ensure_ascii=False) for label in ('selected_pages','selection','physical_page','pages','物理页','已选页')))
                available='\n'.join(text_leaves([m['content'] for m in next_history]))
                for page in reply['selection']['pages']:self.assertIn(actual_text[page].strip(),available)
        # Provider-boundary visual requests, not a claimed independence boolean.
        visions=[r for r in requests if r['stage']=='vision']
        self.assertTrue(visions)
        blind_starts={}
        for req in visions:
            messages=load(req['request_path'])['messages']
            session=req['session_id']
            if session in blind_starts:
                self.assertEqual(messages[:2],blind_starts[session])
                self.assertEqual(messages[2]['role'],'assistant')
                self.assertEqual(messages[-1]['role'],'user')
                continue
            blind_starts[session]=deepcopy(messages)
            self.assertEqual([m['role'] for m in messages],['system','user'])
            content=messages[1]['content'];self.assertIsInstance(content,list)
            self.assertTrue(any(p.get('type')=='image_url' and p['image_url']['url'].startswith('data:image/') for p in content))
            safe_request=deepcopy(load(req['request_path']))
            for msg in safe_request['messages']:
                if isinstance(msg['content'],list):msg['content']=[p for p in msg['content'] if p.get('type')!='image_url']
            texts=json.dumps(safe_request,ensure_ascii=False)
            for forbidden in ('text_candidate','text_observation','reference_values','1100000','1110000','0.83','0.84','0.75'):
                self.assertNotIn(forbidden,texts)
        from pypdf import PdfReader
        prepared=load(result['prepared_file'])
        self.assertEqual(sha(prepared['pdf_path']),sha(pdf))
        actual_pages=load(prepared['pages_path'])
        self.assertEqual([p['text'] for p in actual_pages],[p.extract_text() for p in PdfReader(str(pdf)).pages])
        for image in prepared['images']:
            self.assertEqual(sha(image['path']),image['sha256'])
            self.assertGreater(Path(image['path']).stat().st_size,1000)
        self.assertEqual(len(prepared['images']),2)
        import base64
        image_hashes=[image['sha256'] for image in prepared['images']]
        for req in visions:
            payload=load(req['request_path'])
            seen=[hashlib.sha256(base64.b64decode(part['image_url']['url'].split(',',1)[1])).hexdigest()
                  for msg in payload['messages'] if isinstance(msg['content'],list)
                  for part in msg['content'] if part.get('type')=='image_url']
            self.assertEqual(sorted(seen),sorted(image_hashes))
            parts=payload['messages'][1]['content']
            expected_pages={im['sha256']:im['physical_page'] for im in prepared['images']}
            for index,part in enumerate(parts):
                if part.get('type')!='image_url':continue
                digest=hashlib.sha256(base64.b64decode(part['image_url']['url'].split(',',1)[1])).hexdigest()
                self.assertGreater(index,0)
                self.assertEqual(parts[index-1].get('type'),'text')
                self.assertIn(f"physical_page={expected_pages[digest]}",parts[index-1].get('text',''))

        proof=load(result['proof_file'])
        self.assertEqual(proof['image_source'],'page_image_hashes')
        self.assertEqual(proof['selected_pages'],[1,2])
        self.assertEqual({int(k):v for k,v in proof['image_hashes'].items()},
                         {im['physical_page']:im['sha256'] for im in prepared['images']})
        self.assertEqual(proof['candidate_id'],state['current']['candidate_id'])
        self.assertEqual(proof['visual_session_id'],visions[-1]['session_id'])
        execution=load(result['execution_file']);program=Path(result['task_dir'])/'program'
        self.assertNotEqual(execution['pid'],__import__('os').getpid())
        self.assertTrue(Path(execution['entrypoint']).resolve().is_relative_to(program.resolve()))
        for module,path in execution['loaded_modules'].items():
            if module=='app' or module.startswith('app.'):
                self.assertTrue(Path(path).resolve().is_relative_to(program.resolve()),(module,path))
        manifest=load(result['freeze_manifest_file'])
        for f in manifest['files']:
            path=program/f['path'];self.assertTrue(path.resolve().is_relative_to(program.resolve()));self.assertFalse(path.is_symlink());self.assertEqual(sha(path),f['sha256'])
            self.assertNotIn('.env',f['path']);self.assertNotEqual(Path(f['path']).parts[0],'runtime');self.assertNotIn('.git',Path(f['path']).parts)
            self.assertNotIn('__pycache__',Path(f['path']).parts);self.assertFalse(f['path'].endswith('.pyc'))
        if name=='no_progress':
            self.assertEqual(state['status'],'stopped');self.assertFalse(state.get('review'))
            self.assertEqual(state['counters']['failed_gate_evaluations'],2)
            self.assertEqual(state['counters']['feedback_emitted'],1)
            self.assertEqual(state['counters']['feedback_requests'],1)
            self.assertTrue(state['latest_failure'])
            self.assertFalse(state['current']['internal']['passed'])
        else:
            self.assertEqual(state['status'],'candidate_ready',state)
            self.assertTrue(state['review'])
            for gate in ('internal','external'):
                self.assertTrue(state['current'][gate]['passed']);self.assertEqual(state['current'][gate]['matched'],10)
                self.assertEqual(state['current'][gate]['candidate_id'],state['current']['candidate_id'])
            self.assertEqual(len(requests),len(scenario['model_script']))
            with zipfile.ZipFile(result['sealed_archive']) as z:
                for f in manifest['files']:
                    self.assertEqual(hashlib.sha256(z.read('program/'+f['path'])).hexdigest(),f['sha256'])
                payloads=[z.read(name) for name in z.namelist() if not name.endswith('/')]
                embedded={hashlib.sha256(content).hexdigest() for content in payloads}
                immutable=[result['freeze_manifest_file'],result['prepared_file'],result['proof_file'],
                           prepared['pdf_path'],prepared['pages_path']]
                immutable.extend(im['path'] for im in prepared['images'])
                immutable.extend(req[key] for req in requests for key in ('request_path','response_path'))
                immutable.extend(event[key] for event in trace.get('external_evaluations',[]) for key in ('candidate_path','reference_path'))
                for filename in immutable:
                    self.assertIn(sha(filename),embedded,f'missing actual sealed evidence: {filename}')
                objects=[]
                for content in payloads:
                    try:value=json.loads(content)
                    except (ValueError,UnicodeDecodeError):continue
                    if isinstance(value,dict):objects.append(value)
                live_modules={k:v for k,v in execution['loaded_modules'].items() if k=='app' or k.startswith('app.')}
                self.assertTrue(live_modules)
                self.assertTrue(any(value.get('pid')==execution['pid'] and value.get('entrypoint')==execution['entrypoint']
                                    and {k:v for k,v in value.get('loaded_modules',{}).items() if k=='app' or k.startswith('app.')}==live_modules
                                    and (value.get('evidence_completed_at') or value.get('run_completed_at'))
                                    for value in objects),'seal needs completed execution evidence; live process-exit metadata may be appended after seal')
                self.assertTrue(any(value.get('status')=='candidate_ready' and value.get('current',{}).get('candidate_id')==state['current']['candidate_id'] and value.get('review') for value in objects),'seal needs a final candidate-ready projection; publish live ready only after seal succeeds')
                self.assertTrue(any(value.get('requests')==ledger['requests'] and value.get('total_tokens')==ledger['total_tokens']
                                    for value in objects),'sealed ledger must retain all actual request receipts and tokens')
                self.assertTrue(any(value.get('requests')==trace['requests'] and value.get('actions')==trace['actions']
                                    and value.get('external_evaluations')==trace.get('external_evaluations')
                                    for value in objects),'sealed trace must retain all calls, actions and private comparison evaluations')
        if name in ('combined','vision_revision','external_revision','no_progress'):
            self.assertEqual(len({r['session_id'] for r in visions}),2)
            text=[r for r in requests if r['stage']=='extract']
            self.assertEqual(len({r['session_id'] for r in text}),1)
        if name=='vision_self_repair':
            self.assertEqual(len({r['session_id'] for r in visions}),1)
            self.assertEqual(len([r for r in requests if r['stage']=='extract']),1)
        if name=='combined':
            self.assertEqual([a['action'] for a in trace['actions']],['search_fulltext','read_pages','select_pages','submit','search_fulltext','submit','read_pages','submit'])
            self.assertEqual(state['counters']['failed_gate_evaluations'],2)
        if name in ('combined','external_revision'):
            self.assert_external_rechecks(trace,state,services,visions)
        (folder/'receipt.json').write_text(json.dumps(result,ensure_ascii=False,indent=2))
        return result

    def assert_external_rechecks(self,trace,state,services,visions):
        # A frozen reference may be fetched once and cached; comparisons may not be cached.
        receipts=services['reference_receipts']
        self.assertGreaterEqual(len(receipts),1);self.assertLessEqual(len(receipts),2)
        self.assertTrue(all(r['response']==income_envelope(alternate_reference()) for r in receipts))
        events=trace['external_evaluations'];self.assertEqual(len(events),2)
        self.assertLess(events[0]['sequence'],events[1]['sequence'])
        self.assertNotEqual(events[0]['candidate_id'],events[1]['candidate_id'])
        self.assertEqual(events[-1]['candidate_id'],state['current']['candidate_id'])
        self.assertNotEqual(events[0]['candidate_sha256'],events[1]['candidate_sha256'])
        self.assertEqual(events[0]['reference_sha256'],events[1]['reference_sha256'])
        for i,(event,candidate) in enumerate(zip(events,(observation(),alternate()))):
            actual=load(event['candidate_path'])
            self.assertEqual({k:actual[k] for k in candidate},candidate)
            self.assertEqual(sha(event['candidate_path']),event['candidate_sha256'])
            self.assertEqual(load(event['reference_path']),income_envelope(alternate_reference()))
            self.assertEqual(sha(event['reference_path']),event['reference_sha256'])
            self.assertEqual(event['after_request_id'],visions[i]['request_id'])
            expected={(metric,period):not(i==0 and period=='current' and metric in ('revenue','basic_eps'))
                      for metric in ('revenue','operating_cost','operating_profit','parent_net_profit','basic_eps')
                      for period in ('current','prior')}
            self.assertEqual({(r['metric'],r['period']):r['matched'] for r in event['comparisons']},expected)
            self.assertEqual(event['matched'],sum(expected.values()));self.assertEqual(event['total'],10)
            self.assertEqual(event['passed'],i==1)

    def test_08_production_composition(self):
        for case in ('combined','vision_self_repair','vision_revision','external_revision','no_progress'):
            with self.subTest(case=case):self.run_case(case)

    def test_08_malformed_usage_stops_before_another_request(self):
        from .services import run_with_services
        for number,usage in enumerate(({'completion_tokens':10},{'total_tokens':-1},
                {'prompt_tokens':1.25,'completion_tokens':10,'total_tokens':11},
                {'prompt_tokens':100,'completion_tokens':10,'total_tokens':999},
                {'prompt_tokens':100,'completion_tokens':10,'total_tokens':110,'cached_tokens':101},
                {'prompt_tokens':True,'completion_tokens':10,'total_tokens':11})):
            with self.subTest(usage=usage):
                folder=OUTPUT/f'unknown-usage-{number}';folder.mkdir(parents=True,exist_ok=True)
                scenario=script('freeze');pdf=folder/'synthetic.pdf';write_pdf(pdf);scenario['pdf_path']=str(pdf)
                scenario['model_script'][0]['usage']=usage;scenario['reference_script']=[]
                result,services=run_with_services(SUBJECT,scenario,folder/'run')
                state=load(result['state_file']);ledger=load(result['ledger_file'])
                self.assertEqual(state['status'],'stopped');self.assertFalse(state.get('review'))
                self.assertEqual(len(services['model_receipts']),1);self.assertEqual(services['reference_receipts'],[])
                self.assertIn('unknown',json.dumps(ledger).lower());self.assertTrue(state['latest_failure'])

    def test_08_wrong_reference_identity_or_date_stops(self):
        from .services import run_with_services
        for field in ('thscode','record_thscode','period_end','ok','command','period'):
            with self.subTest(field=field):
                folder=OUTPUT/f'wrong-reference-{field}';folder.mkdir(parents=True,exist_ok=True)
                scenario=script('freeze');pdf=folder/'synthetic.pdf';write_pdf(pdf);scenario['pdf_path']=str(pdf)
                ref=reference()
                if field=='thscode':ref[field]='999999.SH'
                elif field=='record_thscode':ref['records'][0]['thscode']='999999.SH'
                elif field=='period_end':ref['records'][0][field]='2025-06-30'
                else:
                    ref=income_envelope(ref)
                    if field=='period':ref['data']['item'][0]['period']='annual'
                    elif field=='ok':ref['ok']=False
                    else:ref['command']='financials.cashflow'
                scenario['reference_script']=[ref]
                result,services=run_with_services(SUBJECT,scenario,folder/'run')
                state=load(result['state_file'])
                self.assertEqual(state['status'],'stopped');self.assertFalse(state.get('review'))
                self.assertFalse(state['current']['external']['passed'])
                self.assertEqual(len(services['model_receipts']),5);self.assertEqual(len(services['reference_receipts']),1)

    def test_08_invalid_action_uses_dispatcher(self):
        from .services import run_with_services
        folder=OUTPUT/'invalid-action';folder.mkdir(parents=True,exist_ok=True)
        scenario=script('freeze');pdf=folder/'synthetic.pdf';write_pdf(pdf);scenario['pdf_path']=str(pdf)
        scenario['model_script']=[{'stage':'locate','response':{'action':'invent'},'id':f'invalid-{i}',
                                  'usage':{'prompt_tokens':100,'completion_tokens':10,'total_tokens':110}} for i in range(2)]
        scenario['reference_script']=[]
        result,services=run_with_services(SUBJECT,scenario,folder/'run')
        state=load(result['state_file']);trace=load(result['trace_file'])
        self.assertEqual(state['status'],'stopped');self.assertFalse(state.get('review'))
        self.assertEqual([a['action'] for a in trace['actions']],['invent','invent'])
        self.assertEqual(len(services['model_receipts']),2);self.assertEqual(services['reference_receipts'],[])

    def test_08_candidate_company_is_bound_to_task(self):
        from .services import run_with_services
        folder=OUTPUT/'wrong-candidate-company';folder.mkdir(parents=True,exist_ok=True)
        scenario=script('freeze');pdf=folder/'synthetic.pdf';write_pdf(pdf);scenario['pdf_path']=str(pdf)
        wrong=observation();wrong['company']='另一家公司'
        scenario['model_script']=scenario['model_script'][:3]+[
            {'stage':'extract','response':wrong,'id':f'wrong-company-{i}','usage':{'prompt_tokens':100,'completion_tokens':10,'total_tokens':110}}
            for i in range(2)]
        scenario['reference_script']=[]
        result,services=run_with_services(SUBJECT,scenario,folder/'run')
        state=load(result['state_file']);trace=load(result['trace_file'])
        self.assertEqual(state['status'],'stopped');self.assertFalse(state.get('review'))
        self.assertEqual([r['stage'] for r in trace['requests']],['locate','locate','locate','extract','extract'])
        self.assertEqual(state['counters']['failed_gate_evaluations'],2);self.assertEqual(services['reference_receipts'],[])

    def test_08_page_pack_change_invalidates_same_text(self):
        from .services import run_with_services
        folder=OUTPUT/'page-pack';folder.mkdir(parents=True,exist_ok=True)
        scenario=script('freeze');pdf=folder/'synthetic.pdf';write_pdf(pdf);scenario['pdf_path']=str(pdf)
        seq=[('locate',selection()),('extract',observation()),('vision',observation()),
             ('extract',{'action':'select_pages','selection':run_selection()}),('extract',observation()),('vision',observation())]
        scenario['model_script']=[{'stage':stage,'response':response,'id':f'pack-{i}',
            'usage':{'prompt_tokens':100,'completion_tokens':10,'total_tokens':110}} for i,(stage,response) in enumerate(seq)]
        scenario['reference_script']=[alternate_reference(),alternate_reference()]
        result,services=run_with_services(SUBJECT,scenario,folder/'run')
        state=load(result['state_file']);trace=load(result['trace_file']);visions=[r for r in trace['requests'] if r['stage']=='vision']
        self.assertEqual(state['status'],'stopped');self.assertFalse(state.get('review'))
        self.assertEqual(len(visions),2);self.assertNotEqual(visions[0]['session_id'],visions[1]['session_id'])
        self.assertEqual([r['stage'] for r in trace['requests']],['locate','extract','vision','extract','extract','vision'])
        prepared=load(result['prepared_file']);images={im['physical_page']:im['sha256'] for im in prepared['images']}
        import base64
        for req,pages in zip(visions,([1],[1,2])):
            parts=load(req['request_path'])['messages'][1]['content']
            actual=[hashlib.sha256(base64.b64decode(p['image_url']['url'].split(',',1)[1])).hexdigest()
                    for p in parts if p.get('type')=='image_url']
            self.assertEqual(sorted(actual),sorted(images[page] for page in pages))
        events=trace['external_evaluations'];self.assertEqual(len(events),2)
        self.assertNotEqual(events[0]['candidate_id'],events[1]['candidate_id'])
        self.assertEqual(load(events[0]['candidate_path']),load(events[1]['candidate_path']))
        proof=load(result['proof_file']);self.assertEqual(proof['selected_pages'],[1,2])
        self.assertEqual(proof['image_source'],'page_image_hashes')
        self.assertEqual(proof['candidate_id'],state['current']['candidate_id'])
        at_new_pack=services['model_receipts'][4]['projection']
        for gate in ('internal','external'):self.assertFalse(at_new_pack['state']['current'][gate]['passed'])
        self.assertEqual(at_new_pack['proof']['selected_pages'],[1,2])
        self.assertFalse(at_new_pack['proof']['vision_hash'])

    def test_08_vision_cannot_cite_unsent_image(self):
        from .services import run_with_services
        folder=OUTPUT/'unsent-image';folder.mkdir(parents=True,exist_ok=True)
        scenario=script('freeze');pdf=folder/'synthetic.pdf';write_pdf(pdf,texts=(TEXT,TEXT));scenario['pdf_path']=str(pdf)
        unseen=observation();unseen['scope_evidence']['page']=2
        for key in ('current_column_evidence','prior_column_evidence'):
            for item in unseen[key]:item['page']=2
        for row in unseen['rows']:row['value_page']=row['unit_page']=2
        seq=[('locate',selection()),('extract',observation()),('vision',unseen),('vision',unseen)]
        scenario['model_script']=[{'stage':stage,'response':value,'id':f'unsent-{i}',
            'usage':{'prompt_tokens':100,'completion_tokens':10,'total_tokens':110}} for i,(stage,value) in enumerate(seq)]
        result,services=run_with_services(SUBJECT,scenario,folder/'run')
        state=load(result['state_file']);trace=load(result['trace_file'])
        self.assertEqual(state['status'],'stopped');self.assertFalse(state.get('review'))
        self.assertFalse(state['current']['internal']['passed'])
        self.assertEqual(len(services['model_receipts']),4);self.assertEqual(services['reference_receipts'],[])
        visions=[r for r in trace['requests'] if r['stage']=='vision']
        self.assertEqual(len({r['session_id'] for r in visions}),1)
        self.assertEqual(load(result['proof_file'])['selected_pages'],[1])

    def test_08_uncertain_selection_clears_live_proofs(self):
        from .services import run_with_services
        folder=OUTPUT/'uncertain-pack';folder.mkdir(parents=True,exist_ok=True)
        scenario=script('freeze');pdf=folder/'synthetic.pdf';write_pdf(pdf);scenario['pdf_path']=str(pdf)
        uncertain=selection();uncertain['status']='uncertain'
        seq=[('locate',selection()),('extract',observation()),('vision',observation()),
             ('extract',uncertain),('locate',{'action':'search_fulltext','query':'合并利润表','offset':0})]
        scenario['model_script']=[{'stage':stage,'response':value,'id':f'uncertain-{i}',
            'usage':{'prompt_tokens':100,'completion_tokens':10,'total_tokens':110}} for i,(stage,value) in enumerate(seq)]
        scenario['model_script'][-1]['usage']=None  # Stop after observing the next real request boundary.
        scenario['reference_script']=[alternate_reference()]
        result,services=run_with_services(SUBJECT,scenario,folder/'run')
        self.assertEqual(len(services['model_receipts']),5);self.assertEqual(len(services['reference_receipts']),1)
        projection=services['model_receipts'][-1]['projection']
        for gate in ('internal','external'):self.assertFalse(projection['state']['current'][gate]['passed'])
        self.assertEqual(projection['proof']['selected_pages'],[])
        self.assertEqual(projection['proof']['image_hashes'],{})
        self.assertFalse(projection['proof']['vision_hash'])
        self.assertGreaterEqual(projection['state']['counters']['model_requests'],4)
        state=load(result['state_file']);self.assertEqual(state['status'],'stopped');self.assertFalse(state.get('review'))

    def test_08_failed_tools_deliver_current_error(self):
        from .services import run_with_services
        bad_selection=selection();bad_selection['anchors'][0]['quote']='NOT_PRINTED_ON_PAGE'
        pairs=[({'action':'search_fulltext','query':'合并利润表','offset':0},{'action':'search_fulltext','query':'','offset':0}),
               ({'action':'read_pages','pages':[1]},{'action':'read_pages','pages':[999]}),
               ({'action':'select_pages','selection':selection()},{'action':'select_pages','selection':bad_selection})]
        for number,(good,bad) in enumerate(pairs):
            with self.subTest(tool=good['action']):
                folder=OUTPUT/f'failed-tool-{number}';folder.mkdir(parents=True,exist_ok=True)
                scenario=script('freeze');pdf=folder/'synthetic.pdf';write_pdf(pdf);scenario['pdf_path']=str(pdf)
                later='extract' if good['action']=='select_pages' else 'locate'
                seq=[('locate',good),(later,bad),(later,{'action':'search_fulltext','query':'合并利润表','offset':0})]
                scenario['model_script']=[{'stage':stage,'response':value,'id':f'failed-tool-{number}-{i}',
                    'usage':{'prompt_tokens':100,'completion_tokens':10,'total_tokens':110}} for i,(stage,value) in enumerate(seq)]
                scenario['model_script'][-1]['usage']=None;scenario['reference_script']=[]
                result,services=run_with_services(SUBJECT,scenario,folder/'run')
                self.assertEqual(len(services['model_receipts']),3);self.assertEqual(services['reference_receipts'],[])
                before=services['model_receipts'][1]['request']['messages'];after=services['model_receipts'][2]['request']['messages']
                added=after[len(before):];delivered='\n'.join(text_leaves([m['content'] for m in added if m['role']=='user']))
                errors=SUBJECT.dispatch([good,bad],RUN_PAGES,'extract')['failures'];self.assertTrue(errors)
                for error in errors:self.assertIn(error['code'],delivered,'current failed tool must not replay an earlier success')
                self.assertEqual(load(result['state_file'])['counters']['failed_gate_evaluations'],0)

    def test_08_timeout_preserves_existing_state(self):
        from .services import run_with_services
        folder=OUTPUT/'timeout';folder.mkdir(parents=True,exist_ok=True)
        scenario=script('freeze');pdf=folder/'synthetic.pdf';write_pdf(pdf);scenario['pdf_path']=str(pdf)
        scenario['model_script'][0]['delay_seconds']=3;scenario['reference_script']=[]
        result,services=run_with_services(SUBJECT,scenario,folder/'run',wait_timeout_seconds=1)
        state=load(result['state_file'])
        self.assertEqual(state['status'],'interrupted');self.assertFalse(state.get('review'))
        self.assertTrue(state['latest_failure'])
        received=len(services['model_receipts']);self.assertLessEqual(received,1)
        self.assertEqual(services['reference_receipts'],[])
        ledger=load(result['ledger_file']);reserved=len(ledger['requests'])
        self.assertIn(reserved,{received,1});self.assertEqual(state['counters']['model_requests'],reserved)
        if reserved:
            self.assertIn('unknown',json.dumps(ledger).lower(),'interrupted reserved/send outcome has unknown usage, not zero or permanent pending')

    def test_08_retrieval_is_bounded_without_candidate_failures(self):
        from .services import run_with_services
        folder=OUTPUT/'retrieval-budget';folder.mkdir(parents=True,exist_ok=True)
        scenario=script('freeze');pdf=folder/'synthetic.pdf';write_pdf(pdf);scenario['pdf_path']=str(pdf)
        scenario['model_script']=[{'stage':'locate','response':{'action':'search_fulltext','query':'合并利润表','offset':0},
            'id':f'retrieval-{i}', 'usage':{'prompt_tokens':100,'completion_tokens':10,'total_tokens':110}} for i in range(6)]
        scenario['reference_script']=[]
        result,services=run_with_services(SUBJECT,scenario,folder/'run')
        state=load(result['state_file'])
        self.assertEqual(state['status'],'stopped');self.assertFalse(state.get('review'))
        self.assertEqual(len(services['model_receipts']),6)
        self.assertEqual(state['counters']['source_actions'],6)
        self.assertEqual(state['counters']['failed_gate_evaluations'],0)
        self.assertEqual(state['counters']['feedback_emitted'],0)
        self.assertEqual(services['reference_receipts'],[])
        self.assertIn('source',json.dumps(state['latest_failure']).lower())

    def test_08_corrupt_freeze_stops_before_model(self):
        folder=OUTPUT/'corrupt-freeze';folder.mkdir(parents=True,exist_ok=True)
        scenario=script('freeze');pdf=folder/'synthetic.pdf';write_pdf(pdf);scenario['pdf_path']=str(pdf)
        def corrupt(task_dir):
            path=Path(task_dir)/'program/app/contracts.py'
            path.write_text(path.read_text()+"\n# corrupt-freeze-canary\n")
        from .services import run_with_services
        result, services=run_with_services(SUBJECT,scenario,folder/'run',corrupt)
        state=load(result['state_file'])
        self.assertEqual(state['status'],'stopped');self.assertFalse(state.get('review'))
        self.assertEqual(services['model_receipts'],[])
        self.assertIn('freeze',json.dumps(state['latest_failure']).lower())

    def test_08_frozen_execution(self):
        importlib.import_module('app.contracts')  # Exercise an already-cached authoring module.
        targets=[PROJECT/'app/contracts.py',PROJECT/'prompts/runtime/extract.md',PROJECT/'contracts/workflow.json']
        saved={p:p.read_bytes() for p in targets}
        def mutate(task_dir):
            targets[0].write_text("raise RuntimeError('MUTABLE_WORKSPACE_USED')\n")
            targets[1].write_text('MUTABLE_PROMPT_CANARY')
            targets[2].write_text('{"MUTABLE_CONFIG_CANARY":true}')
        try:
            result=self.run_case('freeze',mutate)
            program=Path(result['task_dir'])/'program'
            for path,content in saved.items():self.assertEqual((program/path.relative_to(PROJECT)).read_bytes(),content)
        finally:
            for path,content in saved.items():path.write_bytes(content)


def main():
    global SUBJECT,PROJECT,THROUGH,OUTPUT
    p=argparse.ArgumentParser();p.add_argument('--project',type=Path,default=Path.cwd());p.add_argument('--through',type=int,choices=(0,5,6,7,8),default=8);p.add_argument('--output',type=Path)
    args=p.parse_args();PROJECT=args.project.resolve();THROUGH=args.through
    OUTPUT=(args.output or PROJECT/'tests/output/public-acceptance').resolve();OUTPUT.mkdir(parents=True,exist_ok=True)
    sys.path.insert(0,str(PROJECT))
    if THROUGH>=5:
        module=importlib.import_module('app.acceptance');SUBJECT=module.create_subject(PROJECT)
    suite=unittest.TestSuite()
    for name in unittest.defaultTestLoader.getTestCaseNames(Acceptance):
        phase=int(name.split('_')[1])
        if phase<=THROUGH:suite.addTest(Acceptance(name))
    result=unittest.TextTestRunner(verbosity=2).run(suite)
    receipt={'synthetic_only':True,'ok':result.wasSuccessful(),'tests':result.testsRun,'failures':len(result.failures),'errors':len(result.errors),'through':THROUGH,
             'network_guard':'process-level, inherited by Python workers; not an OS security sandbox'}
    (OUTPUT/'summary.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(receipt,ensure_ascii=False));return 0 if result.wasSuccessful() else 1

if __name__=='__main__':raise SystemExit(main())
