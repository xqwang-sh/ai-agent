"""Current-quarter evaluation suites, separate from frozen historical regression data."""
import hashlib
import json
from pathlib import Path
import shutil
from pypdf import PdfReader

FIELDS=['notice_kind','report_period','notice_number','related_notice_number','meeting_date','start_time','end_time',
        'previous_meeting_date','previous_start_time','previous_end_time','question_deadline_date','question_deadline_time']


def create(output,staging,historical,app,lesson,archive):
    target=staging/'lesson3-q3-validation';(target/'pdfs').mkdir(parents=True)
    def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
    def rows(path):return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
    def save(path,value):path.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n')
    def jsonl(path,values):path.write_text(''.join(json.dumps(row,ensure_ascii=False)+'\n' for row in values))
    small=['1225615375','1225639820'];inputs=[];gold=[];sources=[];suites={'small':small,'templates':[],'changes':[]}
    old_inputs={row['id']:row for row in rows(historical/'input.jsonl')}
    old_gold={row['id']:row for row in rows(historical/'teacher-gold.jsonl')}
    old_sources={row['id']:row for row in json.loads((historical/'sources.json').read_text())}
    for identity in small:
        row=old_sources[identity];path=historical/row['pdf_path'];shutil.copy2(path,target/'pdfs'/path.name)
        inputs.append(old_inputs[identity]);gold.append(old_gold[identity]);sources.append(row)
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
    ids=[row['id'] for row in gold]
    if len(set(ids))!=18:raise ValueError('Expected 18 distinct current-quarter sources')
    suites['expanded']=suites['templates']+suites['changes'];suites['all']=ids
    jsonl(target/'input.jsonl',inputs);jsonl(target/'teacher-gold.jsonl',gold);save(target/'sources.json',sources)
    for name in ['evidence.py','check_gold.py','requirements.txt','output.schema.json']:
        shutil.copy2(historical/name,target/name)
    (target/'README.md').write_text('''# 本期三季度独立核验包

18份原件，40物理页。2份小样本为伊利、嘉和美康；8份新模板含沪深北和合并报告期；另8份包括健之佳、尚太科技的真实原通知与延期。每份保留PDF、全文、原链接、指纹和候选标准。只有包含2026年三季度的说明会进入本包；历史其他报告期另在原回归包中。

先让自己的Agent从巨潮取回原件、保存第一次模型原答，再使用本包评分。不要把teacher-gold.jsonl、source_reference或差异报告送给提取模型。候选标准虽经独立逐页核验，仍待任课教师抽查签认。

原始结果整理为每行{id,result}的actual.jsonl。字段遵循output.schema.json，可做保留原值的字段名转换。首次只验2份，不要求为旧半年报做生产提取：

```sh
python3 -m pip install -r requirements.txt
python3 check_gold.py --suite small --actual /path/to/actual.jsonl --report /path/to/small-report.json
```

扩大范围后先跑templates的8份，再跑changes的8份。--suite expanded评分新增16份，--suite all评分全部18份。范围内缺记录、字段错、证据不成立均失败；同一答案的人为改写不算模型通过。日期明确的延期可标为postponed或change，前提是原通知关系及新旧日期时段均正确，允许值在第一次模型测试前已经冻结。

每条证据须是本页连续原文。仅截止句真实跨相邻两页时允许parts，每段仍分别引用本页原文，且程序严格检查前页页尾到后页页首，没有跳过正文。不得用省略号或合成quote拼接。程序评分还需配合看PDF与操作产品，不能证明全市场普遍准确率。

本包评分不调用模型；原文件或标准指纹改变会拒绝评分。报告放到本包之外。字段、用量及实际模型ID按原始调用保存；服务未返回用量时写未知，不能当零。历史12份/35页包仅作隔离组件回归，不应把它的全部记录要求施加到当前三季度生产查询。
''')
    save(target/'manifest.json',{'gold_status':'candidate; independently source-reviewed; teacher sign-off pending',
        'records':len(gold),'physical_pages':sum(row['physical_pages'] for row in sources),'suites':suites,
        'provenance':provenance,'files':{str(p.relative_to(target)):sha(p) for p in sorted(target.rglob('*')) if p.is_file()}})
    archive(target,output/'lesson3-q3-validation.zip')
    return target


def create_formats(output, staging, historical, lesson, archive):
    directory = lesson / '04-tests/market-expansion-2026-10-31/reviewed-format-sources-v5'
    target = staging / 'lesson3-expansion-checks'
    (target / 'pdfs').mkdir(parents=True)
    def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
    frozen = json.loads((directory / 'gold-freeze.json').read_text())
    if sha(directory / 'candidate-gold.jsonl') != frozen['gold_sha256'] or sha(directory / 'items.json') != frozen['items_sha256']:
        raise ValueError('Frozen expansion regression inputs changed')
    gold = {row['id']: row for row in (json.loads(line) for line in (directory / 'candidate-gold.jsonl').read_text().splitlines())}
    inputs, expected, sources = [], [], []
    for item in json.loads((directory / 'items.json').read_text())['items']:
        identity = item['id']; source = Path(item['pdf_path']); reference = gold[identity]
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
    for name, rows in [('input.jsonl', inputs), ('teacher-gold.jsonl', expected)]:
        (target / name).write_text(''.join(json.dumps(row, ensure_ascii=False) + '\n' for row in rows))
    (target / 'sources.json').write_text(json.dumps(sources, ensure_ascii=False, indent=2) + '\n')
    for name in ('evidence.py', 'check_gold.py', 'requirements.txt', 'output.schema.json'):
        shutil.copy2(historical / name, target / name)
    (target / 'README.md').write_text('''# 扩围后追加的回归检查

7份原件、15物理页，均为本公司2026年三季度说明会。包含地区集体业绩说明会、不同公告编号、图片封面及原件自身的年份异文。每份标准由另一名审查者只读原PDF形成，之后才与模型结果比较，仍待教师签认。

这组根据扩围中已出现的问题补充，不是新的前瞻留出测试，不并入原18份的首次成绩。先保留自己的原始提取，再运行 python3 check_gold.py --actual /path/to/actual.jsonl --report /path/to/report.json。评分不调用模型，禁止将答案或差异送给提取模型。原件北方稀土的2029页眉及中科的图片封面均保留，不能修改PDF或重编号物理页来通过。
''')
    files = {str(path.relative_to(target)): sha(path) for path in sorted(target.rglob('*')) if path.is_file()}
    (target / 'manifest.json').write_text(json.dumps({'gold_status': frozen['status'], 'records': len(expected),
        'physical_pages': sum(row['physical_pages'] for row in sources), 'basis': 'posthoc source-only regression additions; not a fresh blind benchmark',
        'gold_freeze_sha256': sha(directory / 'gold-freeze.json'), 'files': files}, ensure_ascii=False, indent=2) + '\n')
    archive(target, output / 'lesson3-expansion-checks.zip')
    return target
