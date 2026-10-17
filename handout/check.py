from hashlib import sha256
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote, urlsplit
import json
import re
import subprocess
import zipfile

import build


ROOT = Path(__file__).resolve().parents[1]


class Page(HTMLParser):
    def __init__(self):
        super().__init__()
        self.ids = []
        self.links = []
        self.copies = []
        self.h1 = 0

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if 'id' in attrs:
            self.ids.append(attrs['id'])
        if 'data-copy' in attrs:
            self.copies.append(attrs['data-copy'])
        if tag == 'h1':
            self.h1 += 1
        for attr in ['href', 'src']:
            if attr in attrs:
                self.links.append(attrs[attr])


def check():
    assert (ROOT / 'handout.html').read_text() == build.render_html(), 'Regenerate handout.html'
    assert (ROOT / 'PROMPTS.md').read_text() == build.render_markdown(True), 'Regenerate PROMPTS.md'
    assert (ROOT / 'handout/讲义.md').read_text() == build.render_markdown(), 'Regenerate Markdown handout'
    page = Page()
    page.feed((ROOT / 'handout.html').read_text())
    assert page.h1 == 1
    assert len(page.ids) == len(set(page.ids)), 'Duplicate anchors'
    expected_copies = len(build.LESSON['steps']) * 2 + 1 + sum(len(s.get('operations', [])) for s in build.LESSON['steps'])
    assert len(page.copies) == expected_copies and all(x in page.ids for x in page.copies)
    for link in page.links:
        url = urlsplit(link)
        if url.scheme or url.netloc:
            continue
        path = ROOT / unquote(url.path or 'handout.html')
        assert path.exists(), f'Missing link: {link}'
        if url.fragment and path.suffix == '.html':
            target = Page()
            target.feed(path.read_text())
            assert url.fragment in target.ids, f'Missing anchor: {link}'
    for step in build.LESSON['steps']:
        for field in ['aim','actions','prompt','expected','checks','repair','files']:
            assert step[field], f'Missing {field}: {step["id"]}'
        assert step['prompt'] in (ROOT / 'PROMPTS.md').read_text()
        assert step['repair'] in (ROOT / 'PROMPTS.md').read_text()
        for operation in step.get('operations', []):
            assert operation['prompt'] in (ROOT / 'PROMPTS.md').read_text()

    p = build.product_contract()
    with zipfile.ZipFile(ROOT / 'lesson-one-materials.zip') as z:
        assert not z.testzip()
        names = z.namelist()
        assert len(names) == len(set(names)) == 14
        assert all(name.startswith('earnings-workflow/') and '..' not in Path(name).parts for name in names)
        manifest = json.loads(z.read('earnings-workflow/checks/manifest.json'))
        for filename, digest in manifest['files'].items():
            assert sha256(z.read('earnings-workflow/' + filename)).hexdigest() == digest, filename
        assert len(manifest['files']) == len(names) - 1
        for local, packed in [('netlify/data/report-pages-60-75.txt','data/report-pages-60-75.txt'), ('assets/lesson-one-history.json','history/lesson-one-history.json')]:
            assert (ROOT / local).read_bytes() == z.read('earnings-workflow/' + packed)
        window = z.read('earnings-workflow/data/report-pages-60-75.txt').decode()
        assert list(map(int,re.findall(r'=== 第 (\d+) 页 ===',window))) == list(range(60,76))
        contract = json.loads(z.read('earnings-workflow/contracts/workflow.json'))
        assert contract['model'] == p['MODEL']
        assert list(contract['metrics']) == p['METRICS']
        assert [a['id'] for a in contract['approaches']] == p['APPROACHES']
        assert contract['tool_definitions'] == p['tools']
        for filename, content in p['prompts'].items():
            assert z.read('earnings-workflow/prompts/runtime/' + filename).decode().strip() == content
        reference = json.loads(z.read('earnings-workflow/checks/case-reference.json'))
        assert reference['window_sha256'] == sha256(window.encode()).hexdigest()
        for filename in p['prompts']:
            text = z.read('earnings-workflow/prompts/runtime/' + filename).decode()
            assert 'case-reference' not in text and '344815421' not in text and '67' not in text
        recomputed = json.loads(z.read('earnings-workflow/checks/history-recomputed.json'))
        assert recomputed == p['recomputed']
        assert recomputed['yoy-baseline-api']['grade']['score'] == '2/5'
        synthetic = json.loads(z.read('earnings-workflow/checks/synthetic-cases.json'))
        source = json.dumps({'contract':contract,'reference':reference,'synthetic':synthetic},ensure_ascii=False)
        script = r'''
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {gradeOutput, requirePrevious, historicalResult, executeTool} from './assets/lesson-one-workflow.mjs';
const {contract,reference,synthetic} = JSON.parse(readFileSync(0,'utf8'));
const history = JSON.parse(readFileSync('assets/lesson-one-history.json','utf8'));
const parents = {'locator-thinking-api':{...historicalResult(history,'locator-thinking-api'),kind:'current'}, 'unit-api':{...historicalResult(history,'unit-api'),kind:'current'}};
for (const a of contract.approaches) {
  if (!a.parent) continue;
  requirePrevious(a.id,parents[a.parent]);
  assert.throws(() => requirePrevious(a.id,null));
  assert.throws(() => requirePrevious(a.id,{...parents[a.parent],kind:'history'}));
  assert.throws(() => requirePrevious(a.id,{...parents[a.parent],approach:a.input_field === 'raw_values' ? 'locator-baseline-api':'unit-baseline-api'}));
}
const located = gradeOutput('locator-thinking-api',{...reference.location,values:reference.raw_values});
assert.equal(located.section,'pass'); assert.equal(located.table,'pass'); assert.equal(located.score,'5/5');
assert.equal(gradeOutput('unit-api',reference.unit_values).score,'5/5');
assert.equal(gradeOutput('yoy-api',reference.yoy_values).score,'5/5');
for (const c of synthetic.cases) {
  if (c.expect_error && (c.current === null || c.current === '')) continue;
  const result = executeTool(c.tool,c,{[c.metric]:{current:c.current,prior:c.prior}});
  if (c.expect_error) assert.ok(result.startsWith('tool_error'));
  else if (c.tool === 'convert_units') assert.deepEqual(JSON.parse(result),c.expected);
  else assert.equal(result,c.expected);
}
console.log('Product contract, parent checks, reference values and synthetic calculations passed');
'''
        subprocess.run(['node','--input-type=module','-e',script], input=source, text=True, cwd=ROOT, check=True)
    for filename in ['PROMPTS.md','handout/SETUP.md','PUBLIC_DATA_GUIDE.md']:
        text = (ROOT / filename).read_text()
        for label, target in re.findall(r'\[([^\]]+)\]\(([^)]+)\)', text):
            url = urlsplit(target)
            if not url.scheme and not url.netloc:
                assert (ROOT / filename).parent.joinpath(unquote(url.path)).exists(), (filename,label,target)
    print(f'Generated content, {expected_copies} copy targets, links and 14-file archive passed')


if __name__ == '__main__':
    check()
