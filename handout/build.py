from pathlib import Path
import hashlib
import html
import json
import re
import subprocess
import zipfile


ROOT = Path(__file__).resolve().parents[1]
HERE = Path(__file__).resolve().parent
LESSON = json.loads((HERE / "lesson.json").read_text())
e = html.escape


def inline(text):
    text = e(text)
    text = re.sub(r"`([^`]+)`", r"<code>\1</code>", text)
    return re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r'<a href="\2">\1</a>', text)


def listing(items, ordered=False):
    tag = "ol" if ordered else "ul"
    return f"<{tag}>" + "".join(f"<li>{inline(x)}</li>" for x in items) + f"</{tag}>"


def prompt_block(text, ident, title):
    return (f'<div class="prompt-block"><div class="prompt-heading"><h3>{e(title)}</h3>'
            f'<button type="button" data-copy="{ident}">复制 Prompt</button></div>'
            f'<pre id="{ident}">{e(text)}</pre></div>')


def chapter(step, index):
    picture = ""
    if step.get("image"):
        picture = (f'<figure class="chapter-image"><img src="{step["image"]}" loading="lazy" '
                   f'alt="{e(step["image_alt"])}"><figcaption>{e(step["image_caption"])}</figcaption></figure>')
    checkboxes = "".join(
        f'<label><input type="checkbox" data-check="{step["id"]}-{i}"><span>{inline(x)}</span></label>'
        for i, x in enumerate(step["checks"]))
    operations = ""
    if step.get('operations'):
        operations = '<details class="repair"><summary>以后怎样启动、停止、重新打开？</summary><p>下面的话也发给 OpenCode，不需要你自己使用终端。</p>'
        operations += ''.join(prompt_block(x['prompt'], 'operation-'+x['id'], x['title']) for x in step['operations'])
        operations += '</details>'
    return f'''<section class="chapter" id="{step['id']}">
<div class="chapter-head"><span class="chapter-num">{index}</span><h2>{e(step['title'])}</h2></div>
<p class="chapter-question">{e(step['aim'])}</p>
<h3>现在怎么做</h3>{listing(step['actions'], True)}{picture}
{prompt_block(step['prompt'], 'prompt-'+step['id'], '发给 OpenCode')}
<div class="learner-card expected"><h3>你应看到</h3>{listing(step['expected'])}</div>
<p class="files"><b>文件与数据：</b>{inline(step['files'])}</p>
<div class="self-check"><h3>确认后再继续</h3>{checkboxes}</div>
<details class="repair"><summary>卡住时，发送这条修复 Prompt</summary>
{prompt_block(step['repair'], 'repair-'+step['id'], '只修复当前步骤')}</details>
{operations}
</section>'''


def render_html():
    l = LESSON
    nav = ''.join(f'<a href="#{s["id"]}" data-nav="{s["id"]}">{i}　{e(s["short"])}</a>' for i, s in enumerate(l['steps']))
    actors = ''.join(f'<div class="card"><h3>{e(x["title"])}</h3><p>{e(x["body"])}</p></div>' for x in l['actors'])
    stages = ''.join(f'<div class="workflow-stage"><span class="stage-index">{i+1}</span><h3>{e(s["title"])}</h3>'
                     f'<p class="stage-rows">{e(s["rows"])}</p><p><b>输入</b>{e(s["input"])}</p>'
                     f'<p>{e(s["work"])}</p><p class="stage-output">{e(s["output"])}</p></div>' for i, s in enumerate(l['stages']))
    deps = ''.join('<tr>' + ''.join(f'<td>{inline(x)}</td>' for x in row) + '</tr>' for row in l['dependencies'])
    evals = ''.join(f'<li><b>{e(x[0])}</b><span>{e(x[1])}</span></li>' for x in l['evals'])
    chapters = ''.join(chapter(s, i) for i, s in enumerate(l['steps']))
    return f'''<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="description" content="第一讲教师实操讲义：用 OpenCode 逐步搭建财报 workflow，回放历史结果，并使用个人硅基流动 Key 按 02→04→06 运行。">
<meta name="theme-color" content="#59595f"><title>{e(l['title'])} · 教师实操讲义</title>
<link rel="stylesheet" href="handout/handout.css"><script src="handout/handout.js" defer></script></head>
<body><header class="topbar"><div class="topbar-inner"><a class="brand" href="index.html">AI 金融智能体 · 第一讲</a>
<nav class="toplinks" aria-label="材料导航"><a href="demo.html">现场产品 ↗</a><a href="lesson-one-materials.zip" download>下载实操材料 ↗</a></nav></div></header>
<div class="shell"><aside class="sidebar" aria-label="讲义目录"><nav>
<a href="#start" data-nav="start" aria-current="true">这次做出什么</a><a href="#workflow" data-nav="workflow">先看 workflow</a>
<a href="#dependencies" data-nav="dependencies">前后数据依赖</a><a href="#tour" data-nav="tour">先在成品里走一遍</a>
<a href="#prepare" data-nav="prepare">准备项目</a><span class="sidebar-label">跟着做 · 第 0–7 步</span>{nav}
<a href="#finish" data-nav="finish">完成标准</a></nav><p class="side-note">逐条发 Prompt，等 Agent 写文件、运行检查，再由你核对页面。先搭通主线，再加入对照。</p></aside>
<main><header class="hero" id="start"><h1>把一份半年报，<br>做成可复核的简报。</h1>
<p class="byline">{e(l['presenter'])} · {e(l['affiliation'])}</p>
<p class="doc-meta">第一讲教师实操讲义 · 更新 {l['updated']}</p>
<div class="hero-actions"><a href="#tour">先看成品怎么用</a><a href="lesson-one-materials.zip" download>下载实操材料</a><button type="button" id="print">打印讲义</button></div></header>
<section class="intro" id="purpose"><h2>跟着做出一个能运行的产品</h2><p>{e(l['lead'])}</p>
<div class="goal-box"><b>完成后你会得到</b><p>{e(l['goal'])}</p></div><p>{e(l['scope'])}</p></section>
<section class="intro" id="workflow"><h2>这是一个 workflow</h2><p>{e(l['workflow_intro'])}</p>
<div class="workflow-map" aria-label="三个阶段，主线 02 到 04 到 06">{stages}</div>
<p class="mainline">主线 <b>02 → 04 → 06</b><span>原值 → 换算结果 → 同比与候选简报</span></p>
<h3>分清编程 Agent、workflow 和运行模型</h3><div class="actors">{actors}</div></section>
<section class="intro" id="dependencies"><h2>下一步究竟读取哪一份结果？</h2><p>{e(l['dependency_note'])}</p>
<div class="table-wrap" tabindex="0" role="region" aria-label="历史与本次输入依赖，窄屏可横向滚动"><table class="dependency-table">
<caption>六行做法与输入来源</caption><thead><tr><th scope="col">产品行号</th><th scope="col">历史查看</th><th scope="col">本次 Run</th></tr></thead><tbody>{deps}</tbody></table></div>
<p class="callout">{e(l['rerun'])}</p><h3>五项 Evals 检查什么</h3><ol class="eval-list">{evals}</ol><p>{e(l['eval_note'])}</p></section>
<section class="intro" id="tour"><h2>先看线上参考成品</h2><p>先打开<a href="demo.html#evals">现场产品的 Evals</a>。这段在已经发布的成品网站操作；从第 0 步开始，才在你自己的电脑搭建新项目。只完成前两条历史查看，就可以进入准备部分。有 Key 时可选做下面的线上 Run；它的结果不会成为新建本地项目的本轮输入。</p>
{listing(l['tour'], True)}<p class="callout">{e(l['history_note'])}</p>
<p>个人运行 Key 在<a href="https://cloud.siliconflow.cn/" target="_blank" rel="noopener noreferrer">硅基流动控制台</a>管理。只填在网页的隐藏输入框，不发给编程 Agent。网页刷新会清空 Key 和本轮可用前序。</p></section>
<section class="intro" id="prepare"><h2>准备自己的项目</h2>
<p><a class="download-link" href="lesson-one-materials.zip" download>下载第一讲实操材料 · lesson-one-materials.zip</a></p>
<p class="callout">{e(l['build_run_note'])}</p><p>{e(l['word_help'])}</p>
{listing(l['prepare'], True)}<p>{e(l['kit_note'])}</p>
<pre class="file-tree">earnings-workflow/
  TASKBOOK.md
  AGENTS.md
  data/report-pages-60-75.txt
  contracts/workflow.json
  prompts/runtime/                 五份财报模型任务
  history/lesson-one-history.json  只读历史收据
  checks/                         检查参考表、合成案例、文件指纹</pre>
<p>正文中的主 Prompt 都发给 OpenCode。材料包中 prompts/runtime 的文本由做出来的程序发给财报模型，两类提示词用途不同。这里的“第 0–7 步”是搭建步骤，产品中的“01–06”是运行行号。</p>
<h3>每一步都按这个顺序操作</h3>{listing(l['send_flow'], True)}
<p><a href="#environment">准备好后，从第 0 步开始</a>。没有看到文件列表时，让 Agent 列出文件即可；这份讲义不要求你先学会读代码。</p>
<p>准备细节见<a href="handout/SETUP.md">准备工作</a>；所有主 Prompt 和修复 Prompt 也可从<a href="PROMPTS.md">提示词附录</a>复制。</p></section>
{chapters}
<section class="finish" id="finish"><h2>完成标准</h2>{listing(l['finish'])}
<h3>还有问题时，先找第一处失败</h3>{prompt_block(l['rescue'], 'prompt-rescue', '通用排查 Prompt')}
<p>本讲先完成固定报告文字窗口的处理。需要扩展到完整 PDF、独立视觉和同花顺比对时，继续<a href="lesson-2/">第二讲</a>。数据与核验范围见<a href="PUBLIC_DATA_GUIDE.md">第一讲数据说明</a>。</p></section>
<details class="sources"><summary>材料与参考</summary><ul>
<li><a href="demo.html">已上线第一讲产品</a></li><li><a href="handout/讲义.md">Markdown 讲义</a>、<a href="PROMPTS.md">提示词附录</a>、<a href="lesson-one-materials.zip">实操材料包</a></li>
<li><a href="https://opencode.ai/docs/">OpenCode 官方文档</a>与<a href="https://opencode.ai/docs/providers/">模型连接说明</a>。不同版本界面可能有差异，按已安装版本操作。</li>
<li><a href="https://cloud.siliconflow.cn/">硅基流动控制台</a>。不在讲义中预设价格、充值额或免费额度。</li></ul>
<p>外部工具操作入口核对于 {l['updated']}。运行字段、依赖、工具与提示词以本产品和材料包约定为准。</p></details>
<footer class="footer"><p>{e(l['title'])} · {e(l['presenter'])} · {e(l['affiliation'])}</p><p>五项检查通过后仍是候选简报，交由本人复核。第一讲的固定案例检查不代替第二讲的独立取证与核验。</p></footer>
</main></div><div class="toast" id="toast" role="status" aria-live="polite"></div></body></html>'''


def render_markdown(prompts_only=False):
    l = LESSON
    lines = ['# ' + l['title'], '', '第一讲 · 教师实操讲义 · 更新 ' + l['updated'], '']
    if prompts_only:
        lines += ['主 Prompt 发给 OpenCode；prompts/runtime 中的任务由应用发给财报模型。先读 [教师实操讲义](handout.html)。搭建步骤 0–7 与产品运行行号 01–06 分开。', '',
                  '运行主线为 02 → 04 → 06。在线与本地 Run 都只使用本轮通过的前序，历史只读。', '']
    else:
        lines += [l['lead'], '', '## 完成后得到什么', '', l['goal'], '', l['scope'], '', '## 这是一个 workflow', '', l['workflow_intro'], '']
        for s in l['stages']:
            lines += ['### ' + s['title'], '', s['rows'], '', '输入：' + s['input'], '', s['work'], '', '输出：' + s['output'], '']
        lines += ['### 分清三个角色', '']
        for a in l['actors']:
            lines += ['- ' + a['title'] + '。' + a['body']]
        lines += ['', '## 前后数据依赖', '', l['dependency_note'], '', '| 产品行号 | 历史查看 | 本次 Run |', '| --- | --- | --- |']
        lines += ['| ' + ' | '.join(row) + ' |' for row in l['dependencies']]
        lines += ['', l['rerun'], '', '### 五项 Evals', '']
        lines += ['- ' + title + '。' + body for title, body in l['evals']]
        lines += ['', l['eval_note'], '', '## 先在成品中走一遍', '', '打开 https://suibe-ai-agent.netlify.app/demo#evals。', '']
        lines += [f'{i+1}. {x}' for i, x in enumerate(l['tour'])]
        lines += ['', l['history_note'], '', '## 准备自己的项目', '', '下载 https://suibe-ai-agent.netlify.app/lesson-one-materials.zip。', '']
        lines += [l['build_run_note'], '', l['word_help'], '']
        lines += [f'{i+1}. {x}' for i, x in enumerate(l['prepare'])]
        lines += ['', l['kit_note'], '', '主 Prompt 发给 OpenCode，prompts/runtime 发给财报运行模型。第 0–7 步是搭建步骤，01–06 是产品运行行号。', '']
        lines += ['### 每一步都按这个顺序操作', '']
        lines += [f'{i+1}. {x}' for i,x in enumerate(l['send_flow'])]
        lines += ['']
    for s in l['steps']:
        lines += ['## ' + s['title'], '', s['aim'], '', '### 现在怎么做', '']
        lines += [f'{i+1}. {x}' for i, x in enumerate(s['actions'])]
        lines += ['', '### 发给 OpenCode', '', '```text', s['prompt'], '```', '', '### 你应看到', '']
        lines += ['- ' + x for x in s['expected']]
        lines += ['', '### 确认后再继续', '']
        lines += ['- [ ] ' + x for x in s['checks']]
        lines += ['', '文件与数据：' + s['files'], '', '### 卡住时发送', '', '```text', s['repair'], '```', '']
        for operation in s.get('operations', []):
            lines += ['### ' + operation['title'], '', '发给 OpenCode，不需要自己使用终端。', '', '```text', operation['prompt'], '```', '']
    lines += ['## 通用排查 Prompt', '', '```text', l['rescue'], '```', '']
    if not prompts_only:
        lines += ['## 完成标准', ''] + ['- ' + x for x in l['finish']]
        lines += ['', '后续扩展见 [第二讲](https://suibe-ai-agent.netlify.app/lesson-2/)。第一讲数据范围见 [数据说明](https://suibe-ai-agent.netlify.app/PUBLIC_DATA_GUIDE.md)。', '']
    return '\n'.join(lines)


def product_contract():
    script = r'''
import { readFileSync } from 'node:fs';
import { MODEL, APPROACHES, METRICS, LOCATOR_PROMPT, promptFor, toolDefinition, historicalResult } from './assets/lesson-one-workflow.mjs';
const history = JSON.parse(readFileSync('assets/lesson-one-history.json', 'utf8'));
const values = Object.fromEntries(METRICS.map(x => [x, {current:2, prior:1}]));
const state = {raw_values:values, unit_values:values};
const prompts = {'locate.txt':LOCATOR_PROMPT};
for (const [file, id] of [['units-no-tool.txt','unit-baseline-api'], ['units-tool.txt','unit-api'], ['yoy-no-tool.txt','yoy-baseline-api'], ['yoy-tool.txt','yoy-api']]) {
  prompts[file] = promptFor(id, state).replace(JSON.stringify(values), '{{CHECKED_INPUT_JSON}}');
}
const recomputed = Object.fromEntries(APPROACHES.map(id => {
  const r = historicalResult(history, id);
  return [id, {grade:r.grade, caseStates:r.caseStates, input_from:r.input_from}];
}));
console.log(JSON.stringify({MODEL, APPROACHES, METRICS, prompts, tools:[...toolDefinition('convert_units'), ...toolDefinition('calculate_yoy')], recomputed}));
'''
    return json.loads(subprocess.check_output(['node', '--input-type=module', '-e', script], cwd=ROOT, text=True))


def materials():
    p = product_contract()
    source = ROOT / 'netlify/data/report-pages-60-75.txt'
    history_file = ROOT / 'assets/lesson-one-history.json'
    history = json.loads(history_file.read_text())
    source_hash = hashlib.sha256(source.read_bytes()).hexdigest()
    assert source_hash == history['window_sha256'], 'Report window and archive differ'
    assert all(x == 'pass' for x in p['recomputed']['yoy-api']['caseStates']), 'Main historical chain did not pass'
    locator = history['records']['locator-thinking-api']['parsed']
    reference = {
        'purpose':'只供固定案例检查器评分，不得作为当前财报模型任务输入。五项通过不等于独立外部核验。',
        'window_sha256':source_hash, 'location':{k:v for k,v in locator.items() if k != 'values'},
        'raw_values':locator['values'], 'unit_values':history['records']['unit-api']['parsed'],
        'yoy_values':history['records']['yoy-api']['parsed'],
    }
    labels = ['定位与提取 · 无 thinking', '定位与提取 · 有 thinking', '单位换算 · 无工具', '单位换算 · convert_units', '同比计算 · 无工具', '同比计算 · calculate_yoy']
    contract = {
        'schema':1, 'case':{'company':'比亚迪','security':'002594.SZ','current_period':'2026H1','prior_period':'2025H1', 'scope':'截至6月30日的六个月累计，合并口径', 'input':'data/report-pages-60-75.txt', 'physical_pages':[60,75], 'window_sha256':source_hash},
        'model':p['MODEL'], 'mainline':[p['APPROACHES'][i] for i in [1,3,5]],
        'approaches':[{'number':f'{i+1:02d}', 'id':id, 'label':labels[i],
                       'parent':None if i < 2 else p['APPROACHES'][1 if i < 4 else 3],
                       'input_field':None if i < 2 else 'raw_values' if i < 4 else 'unit_values',
                       'history_parent':None if i < 2 else p['APPROACHES'][1 if i < 4 else 3],
                       'thinking':i == 1, 'tool':None if i in [0,1,2,4] else 'convert_units' if i == 3 else 'calculate_yoy',
                       'invalidates':p['APPROACHES'][2:] if i == 1 else p['APPROACHES'][4:] if i == 3 else []}
                      for i,id in enumerate(p['APPROACHES'])],
        'live_dependency':'本轮当前页面会话中通过检查的精确前序。历史查看与本轮结果分开，无历史输入兜底；刷新需重跑前序。',
        'metrics':dict(zip(p['METRICS'], ['营业收入','营业成本','营业利润','归母净利润','基本每股收益'])),
        'locator_fields':['section_name','section_start_page','table_name','table_pages','current_period_header','prior_period_header','unit','values'],
        'locator_values':'values 恰含五项指标，每项含 current 与 prior；页码是物理页整数，原单位照录，缺失填 null，不计算。',
        'unit_output':'五项指标分别包含 current/prior 两期数值，金额为亿元，EPS为元/股。',
        'yoy_output':'五项指标分别为带 % 的两位小数字符串。输入必须为04已舍入的unit_values。',
        'tool_definitions':p['tools'],
        'rules':{'amount_divisor':100000,'amount_decimals':2,'eps_unit':'元/股','yoy_formula':'(current-prior)/prior*100','yoy_decimals':2,'zero_prior':'stop','missing_values':'stop; null/blank are not zero','tool_requirement':'五项都须发生有效调用，参数必须与精确父输入一致，程序执行后将结果交回模型。'},
        'checks':[{'number':i+1,'name':x[0].split('．',1)[1], 'rule':x[1]} for i,x in enumerate(LESSON['evals'])],
        'reference':'checks/case-reference.json 只供程序评分，不进入运行模型上下文。',
        'receipts':['kind','job_id','approach','parent_job_id','window_sha256','model','raw_output','parsed','grade','caseStates','workflowState','tool_calls','usage','usage_complete','elapsed_seconds'],
        'receipt_notes':'程序可用字段适配，但必须保留上述含义；不得有 apiKey。历史保存 recorded_grade 与原收据指纹，历史工具 usage_scope=last_response。',
        'credentials':'网页隐藏输入，仅页面与本次请求内存；不进存储、文件、日志或截图，不使用OpenCode登录文件或共享Key。',
    }
    synthetic = {
        'purpose':'仅测试响应与固定函数，不代表真实模型运行。不调用远程服务。',
        'cases':[
            {'name':'amount_both_periods','tool':'convert_units','metric':'revenue','current':200000,'prior':100000,'source_unit':'千元','expected':{'current':2,'prior':1}},
            {'name':'amount_rounding','tool':'convert_units','metric':'operating_profit','current':123456,'prior':234567,'source_unit':'千元','expected':{'current':1.23,'prior':2.35}},
            {'name':'eps_unchanged','tool':'convert_units','metric':'basic_eps','current':1.35,'prior':1.71,'source_unit':'元/股','expected':{'current':1.35,'prior':1.71}},
            {'name':'growth','tool':'calculate_yoy','metric':'revenue','current':120,'prior':100,'expected':'20.00%'},
            {'name':'decline','tool':'calculate_yoy','metric':'revenue','current':80,'prior':100,'expected':'-20.00%'},
            {'name':'formatting','tool':'calculate_yoy','metric':'revenue','current':2,'prior':3,'expected':'-33.33%'},
            {'name':'zero_prior','tool':'calculate_yoy','metric':'revenue','current':10,'prior':0,'expect_error':True},
            {'name':'null_is_not_zero','tool':'convert_units','metric':'revenue','current':None,'prior':100000,'source_unit':'千元','expect_error':True},
            {'name':'blank_is_not_zero','tool':'calculate_yoy','metric':'revenue','current':'','prior':100,'expect_error':True},
        ],
        'workflow_checks':['缺Key不发请求','缺本轮02时03/04停止','缺本轮04时05/06停止','历史与本轮分离','01不能代替02','03不能代替04','重跑02清空03/04/05/06','重跑04清空05/06','03不覆盖04','两期都评分','缺工具调用失败','错参数失败','usage跨调用累计','当前模型输入不含历史答案或检查参考表'],
    }
    def js(value):
        return (json.dumps(value, ensure_ascii=False, indent=2) + '\n').encode()
    files = {
        'data/report-pages-60-75.txt':source.read_bytes(),
        'history/lesson-one-history.json':history_file.read_bytes(),
        'contracts/workflow.json':js(contract),
        'checks/case-reference.json':js(reference),
        'checks/history-recomputed.json':js(p['recomputed']),
        'checks/synthetic-cases.json':js(synthetic),
    }
    for filename, prompt in p['prompts'].items():
        files['prompts/runtime/' + filename] = (prompt + '\n').encode()
    files['TASKBOOK.md'] = ('''# 第一讲：搭建 earnings-workflow

本目录是起始材料，不含成品应用。先读线上教师讲义，再逐步把主 Prompt 发给自己的编程 Agent。

目标是一个本地网页：Product 展示候选简报，Approaches 解释三个阶段，Evals 对照六行做法。主线为 02 → 04 → 06，后续必须使用本轮已通过的精确前序。

## 已提供的材料

- data/report-pages-60-75.txt：与现场产品完全相同的报告文字窗口，保留物理页边界。不是完整 PDF。
- contracts/workflow.json：案例、阶段、字段、工具、停止和重跑约定。
- prompts/runtime：五份财报任务模板。程序替换 {{CHECKED_INPUT_JSON}} 为本轮已检查前序的真实输入。01 与 02 共用 locate.txt，只改变 thinking。
- history/lesson-one-history.json：六条原始历史输出，供只读回放，不是本轮输入。
- checks/case-reference.json：固定案例评分参考，含案例答案，只给程序检查器，不给财报运行模型。
- checks/history-recomputed.json：历史链按当前规则复算的评分与前序关系。
- checks/synthetic-cases.json：工具与流程的离线检查，不消耗模型额度，结果不能称为真实 Run。
- checks/manifest.json：输入文件指纹。

## 工作边界

主线不下载 PDF、不接同花顺、不生成 PPT、不建立四 Agent 或定时任务。运行模型为 Qwen/Qwen3.5-4B，个人硅基流动 Key 只在网页隐藏输入。OpenCode 的编码模型与本程序授权分开。

先建立空网页，再接历史，再实现 02、04、06，最后加入 01、03、05 对照并验收。第3–6步由编程Agent运行离线检查，不要求本人现在填写财报Key。等程序定稿、服务重新启动后，第7步再由本人在同一页面连续真实运行02→04→06。程序负责工具、检查、数据依赖和停止；模型执行指定的定位、抄录与工具调用。五项检查通过仍是待人工复核的候选简报。

每步完成后，用普通中文报告实际保存的文件、实际检查结果、老师现在该点哪里，以及唯一下一步。启动、停止、重启由编程Agent执行，给出确认可访问的本机网址；不要把终端命令或进程编号当作老师必须自行执行的操作。后台改动后停止本项目旧服务再启动，不同时保留多个旧版本服务。

讲义：https://suibe-ai-agent.netlify.app/handout.html
现有产品：https://suibe-ai-agent.netlify.app/demo#evals
''').encode()
    files['AGENTS.md'] = ('''# 第一讲练习

- 先读取 TASKBOOK.md 和 contracts/workflow.json，按教师当前步骤逐层构建，不一次生成全部应用。
- data、history、checks 是只读材料。实际文件、指纹和失败结果必须保留，不通过改答案或改参考表使检查通过。
- 历史只用于回放，检查参考只用于固定案例评分。财报运行模型只能收到该阶段任务、实际报告窗口或本轮前序，以及当前工具返回。
- 在线 03/04 只读本轮通过的 02；05/06 只读本轮通过的 04。重跑正式前序清空对应下游，01/03不注册为父结果。
- 编程 Agent 不能索取 Key 或读取其私有登录凭据。个人 Key 由本人在网页隐藏输入，只在请求内存中使用。
- 第3–6步先实现模块并运行离线检查，第7步程序定稿后才由本人填写Key，连续真实运行02/04/06。未配置财报Key不阻止继续搭建。离线测试必须标明测试响应，不得冒充真实模型运行。未经本人网页运行，不登记真实验收通过。
- 每步结束用普通中文报告文件、实际检查、可点击的本机网址和下一步。启动、停止、重启由编程Agent操作，不让老师自行猜终端命令；改后台后停止本项目旧服务再启动，避免看旧端口。
''').encode()
    manifest = {'schema':1, 'case':'BYD 2026H1 vs 2025H1, prepared text window', 'files':{name:hashlib.sha256(data).hexdigest() for name,data in sorted(files.items())}}
    files['checks/manifest.json'] = js(manifest)
    with zipfile.ZipFile(ROOT / 'lesson-one-materials.zip', 'w', compression=zipfile.ZIP_DEFLATED) as z:
        for name, data in sorted(files.items()):
            info = zipfile.ZipInfo('earnings-workflow/' + name, (2026,10,17,0,0,0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            z.writestr(info, data)


if __name__ == '__main__':
    materials()
    (ROOT / 'handout.html').write_text(render_html(), encoding='utf-8')
    (ROOT / 'PROMPTS.md').write_text(render_markdown(True), encoding='utf-8')
    (HERE / '讲义.md').write_text(render_markdown(), encoding='utf-8')
    print('Generated handout.html, PROMPTS.md, handout/讲义.md and lesson-one-materials.zip')
