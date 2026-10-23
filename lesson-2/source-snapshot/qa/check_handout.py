"""Verify full prompt parity, local assets and the answer-free classroom kit."""
from decimal import Decimal, ROUND_HALF_UP
import hashlib
import ast
from html.parser import HTMLParser
import json
from pathlib import Path
import re
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'source'))
from prepare_materials import save


class Page(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.ids=[];self.targets=[];self.links=[];self.resources=[];self.pre={};self.current=None;self.h1=0
    def handle_starttag(self,tag,attrs):
        a=dict(attrs)
        if 'id' in a:self.ids.append(a['id'])
        if tag=='h1':self.h1+=1
        if tag=='pre':self.current=a.get('id');self.pre[self.current]=''
        if 'data-copy' in a:self.targets.append(a['data-copy'])
        if tag=='a':self.links.append(a.get('href',''))
        if tag in ('script','img','link'):
            self.resources.append(a.get('src',a.get('href','')))
    def handle_endtag(self,tag):
        if tag=='pre':self.current=None
    def handle_data(self,data):
        if self.current:self.pre[self.current]+=data


def main():
    d=json.loads((ROOT/'source/lesson.json').read_text())
    page=Page();raw=(ROOT/'index.html').read_text();page.feed(raw)
    expected={}
    for s in d['steps']:
        expected['prompt-main-'+s['number']]=s['prompt']
        expected['prompt-repair-'+s['number']]=s['repair']
        if s.get('after_click_prompt'):expected['prompt-after-click']=s['after_click_prompt']
        assert all(s[k] for k in ('actions','goal','expected','checks','files','repair'))
    for i,x in enumerate(d['extensions']):expected['prompt-extension-'+str(i)]=x['prompt']
    for i,x in enumerate(d['troubleshooting']):expected['prompt-help-'+str(i)]=x['prompt']
    for p in (ROOT/'materials/earnings-review/prompts/runtime').glob('*.md'):expected['prompt-runtime-'+p.stem]=p.read_text()
    checks={'single_title':page.h1==1,'unique_ids':len(page.ids)==len(set(page.ids)),
            'all_full_prompts_match_source':page.pre==expected and len(expected)==len(d['steps'])*2+len(d['extensions'])+len(d['troubleshooting'])+4+sum(bool(s.get('after_click_prompt')) for s in d['steps']),
            'copy_targets_match':set(page.targets)==set(expected) and len(page.targets)==len(expected),
            'nine_sequential_steps':[s['number'] for s in d['steps']]==list(map(str,range(9))),
            'no_author_machine_paths':not re.search(r'/Users/|OneDrive|xqwang|codex://',raw),
            'no_external_runtime_assets':all(not x.startswith(('http:','https:','//')) for x in page.resources),
            'local_assets_exist':all((ROOT/x).is_file() for x in page.resources),
            'anchors_resolve':all(x[1:] in page.ids for x in page.links if x.startswith('#')),
            'downloads_exist':all((ROOT/x).is_file() for x in page.links if x and not x.startswith(('#','https:','http:'))),
            'all_main_prompts_in_markdown':all(s['prompt'] in (ROOT/'讲义.md').read_text() and s['prompt'] in (ROOT/'PROMPTS.md').read_text() for s in d['steps'])}
    protocol=d['mainline_protocol']
    coverage=json.loads((ROOT/'source/repair-coverage.json').read_text())
    methods={node.name for file in (ROOT/'source/acceptance').glob('*.py') for node in ast.walk(ast.parse(file.read_text())) if isinstance(node,(ast.FunctionDef,ast.AsyncFunctionDef))}
    layer_labels=('【环境护栏】','【本步任务】','【验收回路】','【完成与停止】')
    step_module={'0':'environment-check.json','1':'app/task_manager.py','2':'app/server.py','3':'app/pdf_tools.py','4':'app/model_client.py','5':'app/extract.py','6':'app/verify.py','7':'app/feedback.py','8':'web/task-view.mjs'}
    checks['nine_main_messages_without_observer']=protocol['development_messages']==9 and protocol['extra_repair_resume_or_observer_messages']==0 and not any(s.get('after_click_prompt') for s in d['steps'])
    checks['incremental_production_gates']=protocol.get('incremental_public_checks')==[1,1,3,6,6,11,16,35,35] and protocol.get('production_ready_by_step')==7
    checks['seven_layer_main_prompt_structure']=all(all(label in s['prompt'] for label in layer_labels) and step_module[s['number']] in s['prompt'] and 'python -m acceptance.checks --through '+s['number'] in s['prompt'] for s in d['steps'])
    checks['environment_guardrail_in_all_main_prompts']=all(s['prompt'].startswith('【环境护栏】') and 'runtime/step-'+s['number'] in s['prompt'] and '确认当前项目根目录' in s['prompt'] and '/tmp' in s['prompt'] for s in d['steps'])
    checks['patch_cases_carried_by_public_acceptance']='test_05_structured_source_binding' in d['steps'][5]['prompt'] and all(name in d['steps'][6]['prompt'] for name in ('test_06_structured_verification','test_06_frozen_execution','test_06_reference_cli_transport')) and 'test_07_http_frontend_restore' in d['steps'][7]['prompt'] and all(name in methods for name in ('test_05_structured_source_binding','test_06_structured_verification','test_06_frozen_execution','test_06_reference_cli_transport','test_07_http_frontend_restore'))
    checks['no_private_observation_dependency']=not any(name in s['prompt'] for s in d['steps'] for name in ('browser-observation.json','opencode-observation.json'))
    checks['declared_low_coding_profile_and_first_write_checkpoint']=d['mainline_protocol']['coding_profile']['variant']=='low' and '--variant low' in d['steps'][0]['prompt'] and '不额外发送测试对话' in d['preparation'][2]['body'] and '首次业务写入前' in d['steps'][5]['prompt'] and '全部11项' in d['steps'][5]['prompt']
    checks['vision_runtime_has_no_text_tool_hint']='按已有动作补证' not in (ROOT/'materials/earnings-review/prompts/runtime/vision.md').read_text() and '不调用文字检索、读页或换页动作' in (ROOT/'materials/earnings-review/prompts/runtime/vision.md').read_text()
    checks['canonical_financial_projection_and_actual_cards']=all(x in d['steps'][6]['prompt'] for x in ('review.normalizations','reviewCards(review)','review.summary或review.series','current_signed_yuan','ROUND_HALF_UP')) and 'reviewCards(review)' in d['steps'][8]['prompt']
    checks['header_boundary_precedes_validity']='structured_incomplete_header_case' in methods
    checks['complete_structural_header_chain']='structured_long_header_case' in methods
    checks['all_explicit_periods_are_certified']='structured_period_consistency_case' in methods
    checks['first_write_precedes_test_body_reads']=all(x in d['steps'][5]['prompt'] for x in ('首次业务写入前禁止读取acceptance测试体','最多两次','6000字符','立即运行through5','stderr','stdout')) and '原文写入AGENTS.md' in d['steps'][1]['prompt'] and '不要求提前通读acceptance源码' in d['steps'][0]['prompt'] and coverage['implementation_sequence']['main5_prewrite_read_calls_max']==2
    checks['period_certificate_shared_and_closed']='structured_year_period_case' in methods and 'structured_column_path_period_case' in methods and coverage['implementation_sequence']['failure_slice_targets_are_business_gates'] is False
    checks['every_period_declaration_in_fragment_is_covered']='structured_fragment_period_case' in methods
    checks['all_allowed_period_families_suffice_without_backup']='structured_sole_period_case' in methods and d['mainline_protocol']['implementation_sequence']['additional_period_pretest_reading_gate'] is False
    checks['complete_raw_titles_share_period_discovery']='structured_title_period_case' in methods
    checks['additional_structure_and_recovery_gates']=all(name in methods for name in ('test_02_frontend_restoration','test_05_structured_source_binding','test_06_structured_verification','test_06_reference_cli_transport','test_07_http_frontend_restore')) and all(row['main_steps'] and all(name in methods for name in row['public_tests']) for row in coverage['additional_regressions'])
    checks['ten_repairs_have_public_test_coverage']=set(row['repair'] for row in coverage['repairs'])==set(range(1,11)) and '2026-10-23' in coverage.get('mapping_note','') and all(row['main_steps'] and row['public_tests'] and all(0<=step<=8 for step in row['main_steps']) and all(name in methods for name in row['public_tests']) for row in coverage['repairs'])
    with zipfile.ZipFile(ROOT/'earnings-review-materials.zip') as z:
        names=z.namelist()
        checks['archive_integrity']=z.testzip() is None
        acceptance_names={'earnings-review/'+n for n in json.loads(z.read('earnings-review/MATERIALS.json'))['acceptance_hashes']}
        checks['no_application_or_secret_files']=not any((Path(n).suffix in ('.py','.js','.html','.env') and n not in acceptance_names) or '/app/' in n or 'runtime/jobs' in n or 'TEACHER_ANSWER' in n for n in names)
        checks['public_acceptance_matches_source']=all(z.read(n)==(ROOT/'source/acceptance'/Path(n).relative_to('earnings-review/acceptance')).read_bytes() for n in acceptance_names)
        checks['strong_context_schema']=all(k in json.loads(z.read('earnings-review/contracts/observation.schema.json'))['required'] for k in ('scope_evidence','current_column_evidence','prior_column_evidence'))
        checks['production_composition_required']='TaskRunner' in z.read('earnings-review/acceptance/README.md').decode() and 'test_07_production_composition' in z.read('earnings-review/acceptance/checks.py').decode()
        checks['six_full_pdf_inputs']=sum(n.lower().endswith('.pdf') for n in names)==6
        manifest=json.loads(z.read('earnings-review/reports/SOURCES.json'))
        checks['all_pdf_hashes_match']=all(hashlib.sha256(z.read('earnings-review/reports/'+m['filename'])).hexdigest()==m['sha256'] for m in manifest)
        checks['four_generic_runtime_prompts']=sum(n.startswith('earnings-review/prompts/runtime/') and n.endswith('.md') for n in names)==4
        policy=json.loads(z.read('earnings-review/contracts/workflow.json'))
        checks['two_explicit_model_presets']=policy['presets']['qwen9']['vision_model']==policy['presets']['qwen27']['vision_model'] and policy['presets']['qwen9']['text_model']!=policy['presets']['qwen27']['text_model']
        checks['header_boundary_precedes_validity'] &= policy['header_boundary']['recognition_independent_of_completeness'] is True
        checks['complete_structural_header_chain'] &= policy['header_chain']['complete_structural_metadata'] is True and policy['header_chain']['fixed_distance_limit'] is False
        checks['period_certificate_shared_and_closed'] &= policy['period_certificate']['single_closed_consumer_boundary'] is True and policy['period_certificate']['bare_date_cannot_produce_target'] is True
        checks['every_period_declaration_in_fragment_is_covered'] &= all(policy['period_certificate'][key] is True for key in ('every_declaration_span_covered_before_classification', 'fragment_can_contain_multiple_claims', 'good_claim_cannot_suppress_unresolved', 'duplicate_claim_records_preserved', 'uncovered_period_intent_blocks_acceptance'))
        checks['all_allowed_period_families_suffice_without_backup'] &= policy['period_certificate']['allowed_complete_families'] == ['month_range', 'date_range', 'end_duration'] and all(policy['period_certificate'][key] is True for key in ('optional_year_same_discovery_grammar', 'sole_family_sufficient_for_each_owner', 'missing_year_is_not_missing_day_or_duration'))
        checks['complete_raw_titles_share_period_discovery'] &= policy['period_certificate']['raw_title_and_metadata_share_discovery'] is True and policy['period_certificate']['first_title_prefix_shortcut'] is False
        checks['all_explicit_periods_are_certified'] &= policy['period_certificate']['every_claim_must_be_target_h1'] is True and policy['period_certificate']['discard_unparsed_claims'] is False
        examples=json.loads(z.read('earnings-review/contracts/check_examples.json'))
        checks['synthetic_usage_sum']=sum(x['total_tokens'] for x in examples['usage_cases']['receipts'])==examples['usage_cases']['expected_total_tokens']
        checks['synthetic_rounding']=all((Decimal(x['reference_yuan']).quantize(Decimal('0.1'),rounding=ROUND_HALF_UP)==Decimal(x['pdf_original']))==x['match'] for x in examples['precision_cases'])
        taskbook=z.read('earnings-review/TASKBOOK.md').decode()
        checks['anchor_contract_matches_runtime']='anchors每项含page、原文quote和purpose' in taskbook and '每项含page、quote、purpose' in z.read('earnings-review/prompts/runtime/locate.md').decode()
        checks['development_coverage_in_materials']=json.loads(z.read('earnings-review/contracts/development-checks.json'))==coverage
        checks['guarded_local_test_entry_in_materials']='earnings-review/acceptance/local_checks.py' in names and all('python -m acceptance.local_checks' in step['prompt'] for step in d['steps'][1:])
    with zipfile.ZipFile(ROOT/'EarningsReview-第二讲讲义包.zip') as z:
        checks['share_bundle_integrity']=z.testzip() is None
        checks['share_bundle_matches_final_handout']=z.read('earnings-review-lesson2/index.html')==(ROOT/'index.html').read_bytes() and z.read('earnings-review-lesson2/earnings-review-materials.zip')==(ROOT/'earnings-review-materials.zip').read_bytes()
    result={'ok':all(checks.values()),'passed':sum(checks.values()),'total':len(checks),'checks':checks,'prompt_count':len(expected),'main_steps':len(d['steps']),'archive_file_count':len(names)}
    save(ROOT/'qa/content-checks.json',result)
    print(json.dumps(result,ensure_ascii=False,indent=2))
    raise SystemExit(0 if result['ok'] else 1)


if __name__=='__main__':main()
