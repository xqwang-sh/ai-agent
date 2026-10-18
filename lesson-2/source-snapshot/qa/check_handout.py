"""Verify full prompt parity, local assets and the answer-free classroom kit."""
from decimal import Decimal, ROUND_HALF_UP
import hashlib
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
            'all_31_full_prompts_match_source':page.pre==expected and len(expected)==31,
            'copy_targets_match':set(page.targets)==set(expected) and len(page.targets)==len(expected),
            'nine_sequential_steps':[s['number'] for s in d['steps']]==list(map(str,range(9))),
            'no_author_machine_paths':not re.search(r'/Users/|OneDrive|xqwang|codex://',raw),
            'no_external_runtime_assets':all(not x.startswith(('http:','https:','//')) for x in page.resources),
            'local_assets_exist':all((ROOT/x).is_file() for x in page.resources),
            'anchors_resolve':all(x[1:] in page.ids for x in page.links if x.startswith('#')),
            'downloads_exist':all((ROOT/x).is_file() for x in page.links if x and not x.startswith(('#','https:','http:'))),
            'all_main_prompts_in_markdown':all(s['prompt'] in (ROOT/'讲义.md').read_text() and s['prompt'] in (ROOT/'PROMPTS.md').read_text() for s in d['steps'])}
    with zipfile.ZipFile(ROOT/'earnings-review-materials.zip') as z:
        names=z.namelist()
        checks['archive_integrity']=z.testzip() is None
        acceptance_names={'earnings-review/'+n for n in json.loads(z.read('earnings-review/MATERIALS.json'))['acceptance_hashes']}
        checks['no_application_or_secret_files']=not any((Path(n).suffix in ('.py','.js','.html','.env') and n not in acceptance_names) or '/app/' in n or 'runtime/jobs' in n or 'TEACHER_ANSWER' in n for n in names)
        checks['public_acceptance_matches_source']=all(z.read(n)==(ROOT/'source/acceptance'/Path(n).relative_to('earnings-review/acceptance')).read_bytes() for n in acceptance_names)
        checks['strong_context_schema']=all(k in json.loads(z.read('earnings-review/contracts/observation.schema.json'))['required'] for k in ('scope_evidence','current_column_evidence','prior_column_evidence'))
        checks['production_composition_required']='TaskRunner' in z.read('earnings-review/acceptance/README.md').decode() and 'test_08_production_composition' in z.read('earnings-review/acceptance/checks.py').decode()
        checks['six_full_pdf_inputs']=sum(n.lower().endswith('.pdf') for n in names)==6
        manifest=json.loads(z.read('earnings-review/reports/SOURCES.json'))
        checks['all_pdf_hashes_match']=all(hashlib.sha256(z.read('earnings-review/reports/'+m['filename'])).hexdigest()==m['sha256'] for m in manifest)
        checks['four_generic_runtime_prompts']=sum(n.startswith('earnings-review/prompts/runtime/') and n.endswith('.md') for n in names)==4
        policy=json.loads(z.read('earnings-review/contracts/workflow.json'))
        checks['two_explicit_model_presets']=policy['presets']['qwen9']['vision_model']==policy['presets']['qwen27']['vision_model'] and policy['presets']['qwen9']['text_model']!=policy['presets']['qwen27']['text_model']
        examples=json.loads(z.read('earnings-review/contracts/check_examples.json'))
        checks['synthetic_usage_sum']=sum(x['total_tokens'] for x in examples['usage_cases']['receipts'])==examples['usage_cases']['expected_total_tokens']
        checks['synthetic_rounding']=all((Decimal(x['reference_yuan']).quantize(Decimal('0.1'),rounding=ROUND_HALF_UP)==Decimal(x['pdf_original']))==x['match'] for x in examples['precision_cases'])
        taskbook=z.read('earnings-review/TASKBOOK.md').decode()
        checks['anchor_contract_matches_runtime']='anchors每项含page、原文quote和purpose' in taskbook and '每项含page、quote、purpose' in z.read('earnings-review/prompts/runtime/locate.md').decode()
    with zipfile.ZipFile(ROOT/'EarningsReview-第二讲讲义包.zip') as z:
        checks['share_bundle_integrity']=z.testzip() is None
        checks['share_bundle_matches_final_handout']=z.read('earnings-review-lesson2/index.html')==(ROOT/'index.html').read_bytes() and z.read('earnings-review-lesson2/earnings-review-materials.zip')==(ROOT/'earnings-review-materials.zip').read_bytes()
    result={'ok':all(checks.values()),'passed':sum(checks.values()),'total':len(checks),'checks':checks,'prompt_count':len(expected),'main_steps':len(d['steps']),'archive_file_count':len(names)}
    save(ROOT/'qa/content-checks.json',result)
    print(json.dumps(result,ensure_ascii=False,indent=2))
    raise SystemExit(0 if result['ok'] else 1)


if __name__=='__main__':main()
