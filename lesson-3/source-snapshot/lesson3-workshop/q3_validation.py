"""Build independent first and expanded checks from one source-reviewed corpus."""
import hashlib
import json
from pathlib import Path
import shutil
from pypdf import PdfReader

FIELDS=['notice_kind','report_period','notice_number','related_notice_number','meeting_date','start_time','end_time',
        'previous_meeting_date','previous_start_time','previous_end_time','question_deadline_date','question_deadline_time']


def create(output,staging,support,app,lesson,archive):
    target=staging/'validation-corpus';(target/'pdfs').mkdir(parents=True)
    def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
    def rows(path):return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
    def save(path,value):path.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n')
    def jsonl(path,values):path.write_text(''.join(json.dumps(row,ensure_ascii=False)+'\n' for row in values))
    small=['1225615375','1225639820'];inputs=[];gold=[];sources=[];suites={'small':small,'templates':[],'changes':[]}
    seed_inputs={row['id']:row for row in rows(support/'input.jsonl')}
    seed_gold={row['id']:row for row in rows(support/'teacher-gold.jsonl')}
    seed_sources={row['id']:row for row in json.loads((support/'sources.json').read_text())}
    for identity in small:
        row=seed_sources[identity];path=support/row['pdf_path'];shutil.copy2(path,target/'pdfs'/path.name)
        inputs.append(seed_inputs[identity]);gold.append(seed_gold[identity]);sources.append(row)
    expansion=lesson/'04-tests/market-expansion-2026-10-31';provenance={}
    for suite,directory in [('templates',expansion/'new-template-pilot'),('changes',expansion/'heldout-source-review')]:
        gold_dir=directory/'evidence-format-v2' if suite=='changes' else directory
        frozen=json.loads((gold_dir/'gold-freeze.json').read_text())
        for relative,expected in frozen.get('files',{}).items():
            if sha(gold_dir/relative)!=expected:raise ValueError('Frozen gold changed: '+relative)
        by_id={row['id']:row for row in rows(gold_dir/'candidate-gold.jsonl')}
        allowances=json.loads((gold_dir/'gold-allowances.json').read_text())
        provenance[suite]={'gold_sha256':sha(gold_dir/'candidate-gold.jsonl'),'freeze_sha256':sha(gold_dir/'gold-freeze.json'),
                           'gold_status':frozen['status']}
        for item in json.loads((directory/'items.json').read_text()):
            identity=item['id'];source=Path(item['pdf_path']);expected=by_id[identity]['source_pdf_sha256']
            if sha(source)!=expected or expected!=item['pdf_sha256']:raise ValueError('Source mismatch '+identity)
            dest=target/'pdfs'/(identity+'.pdf');shutil.copy2(source,dest)
            input_row={key:item[key] for key in ['id','stock_code','publication_date','title','pdf_sha256']}
            input_row['text']='\n'.join(f'[PAGE {i}]\n{page}' for i,page in enumerate(item['pages'],1))
            inputs.append(input_row)
            expected_values={key:by_id[identity]['result'][key] for key in FIELDS}
            value={'id':identity,'source_pdf_sha256':expected,'expected':expected_values,
                   'source_reference':by_id[identity]['result'],
                   'allowed_participation_urls':allowances.get('participation_url_allowed_values',{}).get(identity,[by_id[identity]['result']['participation_url']])}
            kinds=allowances.get('notice_kind_allowed_values',{}).get(identity)
            if kinds:value['allowed_field_values']={'notice_kind':kinds}
            gold.append(value);suites[suite].append(identity)
            sources.append({'id':identity,'title':item['title'],'stock_code':item['stock_code'],'publication_date':item['publication_date'],
                'source_url':item.get('pdf_url') or item.get('url'),'pdf_path':'pdfs/'+identity+'.pdf',
                'sha256':sha(dest),'physical_pages':len(PdfReader(dest).pages)})
    core=[row['id'] for row in gold]
    edge_provenance=append_formats(target,lesson,inputs,gold,sources)
    suites['edge_cases']=edge_provenance.pop('ids')
    provenance['edge_cases']=edge_provenance
    ids=[row['id'] for row in gold]
    if len(ids)!=25 or len(set(ids))!=25:raise ValueError('Expected 25 distinct current-quarter sources')
    suites['core']=core
    suites['expanded']=suites['templates']+suites['changes']+suites['edge_cases']
    suites['all']=ids
    groups={
        'small':{'label':'两家公司起步','ids':suites['small'],'evaluation_role':'original_small_sample'},
        'templates':{'label':'不同公告模板','ids':suites['templates'],'evaluation_role':'original_template_pilot'},
        'changes':{'label':'原通知、延期与普通通知对照','ids':suites['changes'],'evaluation_role':'original_heldout'},
        'edge_cases':{'label':'扩围疑难样例','ids':suites['edge_cases'],'evaluation_role':'posthoc_regression'},
    }
    jsonl(target/'input.jsonl',inputs);jsonl(target/'teacher-gold.jsonl',gold);save(target/'sources.json',sources)
    for name in ['evidence.py','check_gold.py','requirements.txt','output.schema.json']:
        shutil.copy2(support/name,target/name)
    (target/'README.md').write_text(README,encoding='utf-8')
    save(target/'manifest.json',{'gold_status':'candidate; independently source-reviewed; teacher sign-off pending',
        'records':len(gold),'physical_pages':sum(row['physical_pages'] for row in sources),'suites':suites,'groups':groups,
        'evaluation_basis':'One classroom validation bundle; original 18 and 7 posthoc cases retain separate provenance. Combined regression pass is not fresh blind accuracy.',
        'provenance':provenance,'files':{str(p.relative_to(target)):sha(p) for p in sorted(target.rglob('*')) if p.is_file()}})
    return {stage:publish_stage(stage,target,output,staging,groups,provenance,archive)
            for stage in ('initial','expanded')}


def append_formats(target, lesson, inputs, expected, sources):
    directory = lesson / '04-tests/market-expansion-2026-10-31/reviewed-format-sources-v5'
    def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
    frozen = json.loads((directory / 'gold-freeze.json').read_text())
    if sha(directory / 'candidate-gold.jsonl') != frozen['gold_sha256'] or sha(directory / 'items.json') != frozen['items_sha256']:
        raise ValueError('Frozen expansion regression inputs changed')
    gold = {row['id']: row for row in (json.loads(line) for line in (directory / 'candidate-gold.jsonl').read_text().splitlines())}
    ids = []
    for item in json.loads((directory / 'items.json').read_text())['items']:
        identity = item['id']; source = Path(item['pdf_path']); reference = gold[identity]
        ids.append(identity)
        pages_path = Path(item['pages_path'])
        if sha(source) != reference['source_pdf_sha256'] or sha(pages_path) != item['pages_sha256']:
            raise ValueError('Source PDF changed: ' + identity)
        pages = json.loads(pages_path.read_text())
        destination = target / 'pdfs' / (identity + '.pdf'); shutil.copy2(source, destination)
        inputs.append({**{key: item[key] for key in ('id', 'stock_code', 'publication_date', 'title', 'pdf_sha256')},
                       'text': '\n'.join(f'[PAGE {index}]\n{page}' for index, page in enumerate(pages, 1))})
        expected.append({'id': identity, 'source_pdf_sha256': reference['source_pdf_sha256'],
                         'expected': {key: reference['result'][key] for key in FIELDS},
                         'source_reference': reference['result'],
                         'allowed_participation_urls': [reference['result']['participation_url']]})
        sources.append({'id': identity, 'title': item['title'], 'stock_code': item['stock_code'],
                        'publication_date': item['publication_date'], 'source_url': item.get('pdf_url') or item['url'],
                        'pdf_path': 'pdfs/' + identity + '.pdf', 'sha256': sha(destination), 'physical_pages': len(pages)})
    return {'ids':ids,'gold_sha256':frozen['gold_sha256'],
            'freeze_sha256':sha(directory/'gold-freeze.json'),'gold_status':frozen['status'],
            'basis':'posthoc source-only regression additions; not a fresh blind benchmark'}


def publish_stage(stage,corpus,output,staging,groups,provenance,archive):
    names=['small'] if stage=='initial' else ['templates','changes','edge_cases']
    chosen={key:groups[key] for key in names}
    ids=[identity for group in chosen.values() for identity in group['ids']]
    target=staging/('lesson3-'+stage+'-check');(target/'pdfs').mkdir(parents=True)
    rows=lambda name:[json.loads(line) for line in (corpus/name).read_text().splitlines() if line.strip()]
    for name in ['input.jsonl','teacher-gold.jsonl']:
        values=[row for row in rows(name) if row['id'] in ids]
        (target/name).write_text(''.join(json.dumps(row,ensure_ascii=False)+'\n' for row in values))
    sources=[row for row in json.loads((corpus/'sources.json').read_text()) if row['id'] in ids]
    for row in sources:shutil.copy2(corpus/row['pdf_path'],target/row['pdf_path'])
    for name in ['evidence.py','check_gold.py','requirements.txt','output.schema.json']:shutil.copy2(corpus/name,target/name)
    (target/'sources.json').write_text(json.dumps(sources,ensure_ascii=False,indent=2)+'\n')
    title='首次核验包' if stage=='initial' else '扩围核验包'
    scope='伊利、嘉和美康两家公司，共2份公告、6个PDF物理页。完成两家公司取数和第一次提取后使用。' if stage=='initial' else '扩围后的23份公告、49个PDF物理页。完成全A股2026年三季度、会议日期10至11月的数据处理后使用。包含不同模板8份，原通知、延期与普通通知对照8份，疑难样例7份。'
    details='先用本包检查会议时段、截止事项与连续引文。通过后再扩大范围，届时使用单独的扩围核验包。' if stage=='initial' else '本包已含健之佳、尚太两组原通知与延期，集体业绩说明会、招商轮船的特殊编号、中科蓝讯的图片封面、北方国际的年份异文等样例。修复后重跑，保留首次结果。疑难7份仍是事后回归样例，不改写原18份首轮成绩，也不构成新的盲测。'
    (target/'README.md').write_text('# '+title+'\n\n'+scope+'\n\n'+details+'\n\n'+STAGE_README,encoding='utf-8')
    sha=lambda path:hashlib.sha256(path.read_bytes()).hexdigest()
    manifest={'stage':stage,'gold_status':'candidate; independently source-reviewed; teacher sign-off pending','records':len(ids),'physical_pages':sum(row['physical_pages'] for row in sources),'suites':{'all':ids,**{key:group['ids'] for key,group in chosen.items()}},'groups':chosen,'provenance':{key:provenance[key] for key in names if key in provenance},'evaluation_basis':'Independent stage package; default all grades only this package. Frozen source fields retained, posthoc history not relabelled.','files':{str(p.relative_to(target)):sha(p) for p in sorted(target.rglob('*')) if p.is_file()}}
    (target/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n')
    archive(target,output/(target.name+'.zip'))
    return target


README = 'Internal source corpus: 25 distinct Q3 notices, 55 physical pages. Classroom delivery uses independent initial (2) and expanded (23) checks. Original gold, input and PDF values remain unchanged.'

STAGE_README = """## 包里有什么

pdfs/保存本阶段原始公告，input.jsonl保存带物理页编号的全文。teacher-gold.jsonl是候选标准和依据，需教师抽查确认。check_gold.py和evidence.py负责评分；output.schema.json约定字段格式；sources.json和manifest.json保留原链接、页数、指纹和分组来源。

## 怎样核验

先让自己的Agent从巨潮取回原件，保存第一次模型原答，再用本包检查对应的样本。原始结果每行一个{id,result}，只选本包公告，不能把整个市场所有记录都当成本包输入。字段结构可做保留原值的转换，缺值或错值不手工补成正确答案后计为模型通过。提取模型不接收teacher-gold、source_reference或评分差异。

两个阶段都用相同命令，不用选择范围参数：

```sh
python3 -m pip install -r requirements.txt
python3 check_gold.py --actual /path/to/actual.jsonl --report /path/to/report.json
```

程序默认核验本包全部记录，缺记录、重复ID、字段错或引文不成立都不能算通过。本包可独立解压评分，不依赖另一个核验包。评分不调用模型，报告存到包外，保留每轮原答、实际模型、提示词、错误与用量，供4B、9B和27B比较。

## 检查范围

自动比较以会议日期和起止时间、截止时间、公告与改期关系等12个关键字段及其证据为主，已标注的参与网址另核验。完整提问预征集区间、报名事项和全部参与路径对照PDF人工检查。爬虫覆盖、更正后更新同一事件、日历操作与真实定时触发还要实际验收。

候选标准及引用保留原来源，不将修复后的结果计为首轮模型成绩。原件、标准或评分文件的指纹改变会拒绝评分。引用须来自所标物理页连续原文；真实跨相邻页的截止句按每页分别引用，不用拼接引文冒充连续正文。
"""
