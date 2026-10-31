"""Build a standalone handout from the single Markdown source."""
from hashlib import sha256
from html import escape
import argparse
import json
from pathlib import Path
import re
import shutil

from bs4 import BeautifulSoup
import markdown

ROOT = Path(__file__).resolve().parent
SITE = ROOT.parent


def render():
    document = BeautifulSoup(markdown.markdown(
        (ROOT / 'handout.md').read_text(encoding='utf-8'),
        extensions=['tables', 'fenced_code'],
        output_format='html5',
    ), 'html.parser')
    title = document.h1.extract()
    title['id'] = 'page-title'
    sections = []
    current = None
    intro = []
    for node in list(document.contents):
        if node.name == 'h2':
            heading = node.get_text()
            match = re.match(r'第(\d+)步：', heading)
            identifier = 'step-' + match.group(1) if match else {
                '先知道怎样才算准备好了': 'before',
                '卡住时，先看是哪一层出了问题': 'help',
                '官方入口与核对说明': 'sources',
            }[heading]
            current = {'id': identifier, 'heading': heading, 'number': match.group(1) if match else None, 'nodes': []}
            sections.append(current)
            node.extract()
        elif current is None:
            intro.append(str(node))
        else:
            current['nodes'].append(str(node))
    rendered = []
    nav = []
    for section in sections:
        number, heading, identifier = section['number'], section['heading'], section['id']
        nav.append('<a href="#' + identifier + '">' + ('<span>' + number + '</span>' if number else '') + escape(heading if not number else heading.split('：', 1)[1]) + '</a>')
        if number:
            heading_html = '<div class="step-title"><span class="step-number">' + number + '</span><div><span class="eyebrow">课前操作 ' + number + '</span><h2>' + escape(heading.split('：', 1)[1]) + '</h2></div></div>'
            completion = '<label class="completion"><input type="checkbox" data-complete="' + identifier + '" data-title="' + escape(heading, quote=True) + '">我已按本步方法亲自核对。没有做到的仍记为待完成。</label>'
        else:
            heading_html = '<h2>' + escape(heading) + '</h2>'
            completion = ''
        rendered.append('<section class="' + ('step' if number else 'section') + '" id="' + identifier + '">' + heading_html + ''.join(section['nodes']) + completion + '</section>')
    body = BeautifulSoup(''.join(rendered), 'html.parser')
    for index, pre in enumerate(body.find_all('pre'), 1):
        code = pre.code
        language = next(iter(code.get('class', ['language-text'])), 'language-text').removeprefix('language-')
        label = {'prompt': '复制后发给 OpenCode', 'terminal': '复制这一行到系统终端', 'text': '自己创建文件时参考的文字', 'csv': 'CSV 格式示例，虚构记录', 'json': 'JSON 格式示例，虚构记录'}.get(language, '示例文字')
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
<meta name="description" content="面向只用过 Office、没有编程经验的教师。安装工具、连接模型与数据服务，逐步亲自检查文件、PDF 和网页。无需练习包。">
<title>零基础必看入门 · 金融智能体系列讲座</title><style>''' + css + '''</style></head><body>
<a class="skip" href="#content">跳到讲义</a>
<aside class="sidebar"><a class="brand" href="#top"><span class="brand-mark">0</span><span>零基础必看入门<small>金融智能体系列 · 课前必做</small></span></a>
<nav aria-label="讲义目录">''' + ''.join(nav) + '''</nav>
<div class="reading-status"><span>本人已核对的步骤</span><strong id="completion-count">0 / 10 步</strong><p>勾选仅记进度。<br>按每步方法检查实际结果。</p></div></aside>
<main id="content"><header id="top"><p class="eyebrow">第一至三讲之前，从自己的电脑开始</p>''' + str(title) + ''.join(intro) + '''
<div class="downloads"><a href="https://suibe-ai-agent.netlify.app/">返回系列讲座主页</a><a class="primary" href="#step-1">从第1步开始</a><a href="handout.md" download>下载 Markdown 讲义</a><button id="print-handout" class="print-button" type="button">打印或保存为 PDF</button></div></header>
''' + str(body) + '''
<div class="manual-record"><p>正式课前记录与未完成项按第10步保存在自己的电脑上。网页勾选仅记本人阅读进度，不替代实际文件和连接记录。</p></div>
<footer><p>讲义中的操作由老师用本人电脑与账号完成。本站不接收或保存密钥，不发送模型或数据请求，不收集自查结果。</p></footer>
</main><div id="copy-status" role="status" aria-live="polite"></div><script>''' + script + '</script></body></html>\n'


def export(destination):
    target = destination / '01-handouts'
    target.mkdir(parents=True, exist_ok=True)
    records = []
    for name in ['index.html', 'handout.md']:
        source = ROOT / name
        output = target / name
        shutil.copyfile(source, output)
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
