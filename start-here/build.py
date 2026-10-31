"""Build the concept-first handout and export identical distribution copies."""
from hashlib import sha256
from html import escape
import argparse
import json
from pathlib import Path
import shutil

from bs4 import BeautifulSoup
import markdown

ROOT = Path(__file__).resolve().parent
SITE = ROOT.parent


def render():
    document = BeautifulSoup(markdown.markdown(
        (ROOT / 'handout.md').read_text(encoding='utf-8'),
        extensions=['tables', 'fenced_code', 'attr_list', 'md_in_html'],
        output_format='html5',
    ), 'html.parser')
    title = document.h1.extract()
    title['id'] = 'page-title'
    body = BeautifulSoup('', 'html.parser')
    intro, nav = [], []
    part = topic = None
    for node in list(document.contents):
        if node.name in ('h2', 'h3'):
            identifier = node['id']
            del node['id']
            is_part = node.name == 'h2'
            nav.append('<a class="' + ('nav-part' if is_part else 'nav-topic') + '" href="#' + identifier + '">' + escape(node.get_text()) + '</a>')
            section = body.new_tag('section', attrs={
                'id': identifier,
                'class': 'part' if is_part else 'section topic',
            })
            section.append(node)
            if is_part:
                body.append(section)
                part, topic = section, None
            else:
                part.append(section)
                topic = section
        elif part is None:
            intro.append(str(node))
        else:
            (topic if topic is not None else part).append(node)
    for section in body.select('.topic'):
        first_paragraph = section.find('p', recursive=False)
        if first_paragraph:
            first_paragraph['class'] = ['goal']
    for index, pre in enumerate(body.find_all('pre'), 1):
        code = pre.code
        language = code.get('class', ['language-text'])[0].removeprefix('language-')
        label = {
            'prompt': '复制后发给你自己的 Agent',
            'terminal': '复制这一行到本机系统终端',
            'csv': 'CSV 格式说明，虚构记录',
            'json': 'JSON 格式说明，虚构记录',
        }.get(language, '示例文字')
        wrapper = body.new_tag('div', attrs={'class': 'prompt-box'})
        toolbar = body.new_tag('div', attrs={'class': 'prompt-toolbar'})
        span = body.new_tag('span')
        span.string = label
        button = body.new_tag('button', attrs={'class': 'copy', 'type': 'button', 'data-copy': f'copy-{index}', 'aria-label': f'复制第{index}段文字：{label}'})
        button.string = '复制文字'
        toolbar.extend([span, button])
        pre['id'] = f'copy-{index}'
        pre.wrap(wrapper)
        wrapper.insert(0, toolbar)
    for table in body.find_all('table'):
        table.wrap(body.new_tag('div', attrs={'class': 'table-scroll', 'tabindex': '0', 'role': 'region', 'aria-label': '对照表，可左右滚动'}))
        for th in table.find_all('th'):
            th['scope'] = 'col'
    css = (SITE / 'lesson-2/assets/handout.css').read_text() + '\n' + (ROOT / 'assets/onboarding.css').read_text()
    script = (ROOT / 'assets/onboarding.js').read_text()
    return '''<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="description" content="先理解模型调用、Harness、Agent、数据 API 与文档格式，再选择已有工具，按需准备工作目录、环境和服务。">
<title>零基础必看入门 · 金融智能体系列讲座</title><style>''' + css + '''</style></head><body>
<a class="skip" href="#content">跳到讲义</a>
<aside class="sidebar"><a class="brand" href="#top"><span class="brand-mark">0</span><span>零基础必看入门<small>金融智能体系列 · 课前必做</small></span></a>
<nav aria-label="讲义目录">''' + ''.join(nav) + '''</nav>
<p class="sidebar-note">先读概念，再按需操作。<br>已有工具可以继续沿用。</p></aside>
<main id="content"><header id="top"><p class="eyebrow">课前必做 · 先理解，再动手</p>''' + str(title) + ''.join(intro) + '''
<div class="downloads"><a class="primary" href="#concepts">先读概念</a><a href="#practice-tools">选择我的工具</a><a href="handout.md" download>下载 Markdown 讲义</a><button id="print-handout" class="print-button" type="button">打印或保存为 PDF</button></div></header>
''' + str(body) + '''
<footer><p>工具选择仅保存在当前浏览器，用于显示相应说明。本页不接收 API Key，不发起模型或金融数据请求。</p><p><a href="https://suibe-ai-agent.netlify.app/">返回系列讲座主页</a></p></footer>
</main><div id="copy-status" role="status" aria-live="polite"></div><script>''' + script + '</script></body></html>\n'


def export(destination):
    target = destination / '01-handouts'
    target.mkdir(parents=True, exist_ok=True)
    records = []
    for name in ['index.html', 'handout.md']:
        source = ROOT / name
        shutil.copyfile(source, target / name)
        records.append({'source': f'publication/ai-agent/start-here/{name}', 'destination': f'00-getting-started/01-handouts/{name}', 'sha256': sha256(source.read_bytes()).hexdigest()})
    (destination / '06-preparation').mkdir(parents=True, exist_ok=True)
    (destination / '06-preparation/export-manifest.json').write_text(json.dumps({'source_branch': 'docs/zero-basics-intro', 'files': records}, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--export-to', type=Path)
    args = parser.parse_args()
    (ROOT / 'index.html').write_text(render(), encoding='utf-8')
    if args.export_to:
        export(args.export_to.resolve())
    print('Built start-here/index.html' + (' and exported handout copies' if args.export_to else ''))
