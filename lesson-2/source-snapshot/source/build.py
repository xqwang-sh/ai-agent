"""Generate the prompt-led handout and answer-free classroom archive."""
from html import escape
import json
from pathlib import Path
import stat
import zipfile

from prepare_materials import main as prepare, write

ROOT = Path(__file__).resolve().parents[1]
DATA = json.loads((ROOT / 'source/lesson.json').read_text())


def e(value):
    return escape(str(value), quote=True)


def paragraphs(values):
    return ''.join('<p>' + e(v) + '</p>' for v in values)


def items(values, tag='ul'):
    return '<' + tag + '>' + ''.join('<li>' + e(v) + '</li>' for v in values) + '</' + tag + '>'


def prompt(identifier, content, label='复制后发给你的编程 Agent'):
    return f'<div class="prompt-box"><div class="prompt-toolbar"><span>{e(label)}</span><button type="button" class="copy" data-copy="{e(identifier)}" aria-label="复制{e(identifier)}">复制 Prompt</button></div><pre id="{e(identifier)}">{e(content)}</pre></div>'


def step_html(step):
    after = '<h3>点击后，发这条查看本轮运行</h3>' + prompt('prompt-after-click',step['after_click_prompt']) if step.get('after_click_prompt') else ''
    return f'''<section class="step" id="{e(step['id'])}"><div class="step-title"><span class="step-number">{e(step['number'])}</span><div><span class="eyebrow">搭建步骤 {e(step['number'])}</span><h2>{e(step['title'])}</h2></div></div><p class="goal">{e(step['goal'])}</p><div class="actions"><h3>现在怎么做</h3>{items(step['actions'],'ol')}</div>{prompt('prompt-main-'+step['number'],step['prompt'])}{after}<div class="checkpoint"><div><h3>应该看到</h3>{items(step['expected'])}</div><div><h3>确认后再继续</h3>{items(step['checks'])}</div></div><p class="files"><span>本步产物</span> {' · '.join('<code>'+e(p)+'</code>' for p in step['files'])}</p><details class="repair"><summary>本步没做好？复制修复 Prompt</summary>{prompt('prompt-repair-'+step['number'],step['repair'])}</details><label class="completion"><input type="checkbox" data-complete="{e(step['id'])}">我已按检查点确认这一步</label></section>'''


def extension_html(extension, index):
    return f'<section class="extension" id="{e(extension["id"])}"><h3>{e(extension["title"])}</h3><p>{e(extension["why"])}</p>{prompt("prompt-extension-"+str(index),extension["prompt"])}<div class="extension-check"><strong>怎么检查</strong>{items(extension["checks"])}</div></section>'


def overview_html(overview):
    nodes = ''
    for i,p in enumerate(overview['nodes']):
        failure = '<a class="process-failure" href="#feedback-loop">不通过 → 补证分支</a>' if p['kind'] == 'check' else ''
        edge = '<span class="process-edge">'+e(p.get('next','继续'))+' ↓</span>' if i < len(overview['nodes'])-1 else ''
        nodes += f'<li class="process-{e(p["kind"])}" id="flow-{e(p["id"])}"><div class="process-node"><span class="process-owner">{e(p["owner"])}</span><strong>{e(p["label"])}</strong>{failure}</div>{edge}</li>'
    table = '<div class="table-scroll" tabindex="0" aria-label="逐步流程说明，可横向滚动"><table class="process-table"><thead><tr><th>步骤</th><th>谁执行</th><th>输入、操作与输出</th></tr></thead><tbody>' + ''.join(f'<tr><th scope="row">{i+1}．{e(p["label"])}</th><td>{e(p["owner"])}</td><td>{e(p["work"])}</td></tr>' for i,p in enumerate(overview['steps'])) + '</tbody></table></div>'
    branch = f'<aside class="feedback-branch" id="feedback-loop"><h3>{e(overview["feedback_title"])}</h3>{items(overview["feedback_steps"],"ol")}<p>{e(overview["feedback_note"])}</p><a href="#flow-locate">↖ 回到检索、读页与补证</a></aside>'
    return f'<section class="overview" id="workflow-map" aria-labelledby="overview-title"><h2 id="overview-title">{e(overview["title"])}</h2><p>{e(overview["lead"])}</p><div class="process-legend"><span>程序执行</span><span>模型请求</span><span>检查关卡</span></div><div class="process-layout"><ol class="process-diagram" aria-label="从 PDF 到复盘的程序与模型流程">{nodes}</ol>{branch}</div><p class="small">{e(overview["calls_note"])}</p><h3>每一步具体做什么</h3>{table}<p>{e(overview["delivery_note"])}</p><p>{e(overview["mapping_note"])}</p></section>'


def material_guide_html(guide):
    rows = ''.join('<tr><th scope="row"><code>'+e(item['path'])+'</code></th><td>'+e(item['contents'])+'</td><td>'+e(item['use'])+'</td></tr>' for item in guide['items'])
    return '<section id="materials-guide" aria-labelledby="materials-title"><h2 id="materials-title">'+e(guide['title'])+'</h2><p>'+e(guide['lead'])+'</p><div class="table-scroll" tabindex="0" aria-label="材料包内容与用途，可横向滚动"><table class="process-table"><thead><tr><th>文件或文件夹</th><th>里面是什么</th><th>这次怎么用</th></tr></thead><tbody>'+rows+'</tbody></table></div>'+items(guide['notes'])+'</section>'


def render_html():
    d = DATA
    nav = '<a href="#readiness">开始前，确认准备</a><a href="#workflow-map">先看程序与模型流程</a><a href="#start">本讲项目与材料</a><a href="#materials-guide">认识材料包</a>' + ''.join(f'<a href="#{s["id"]}"><span>{s["number"]}</span>{e(s["title"])}</a>' for s in d['steps']) + '<a href="#extensions">扩展验证</a><a href="#help">卡住时</a><a href="#finish">交付检查</a><a href="#runtime-prompts">运行时提示词</a>'
    roles = ''.join(f'<div><h3>{e(r["who"])}</h3><p>{e(r["task"])}</p></div>' for r in d['roles'])
    flow = '<ol class="flow">' + ''.join(f'<li><span class="owner">{e(s["owner"])}</span><strong>{e(s["label"])}</strong><p>{e(s["work"])}</p></li>' for s in d['flow']) + '</ol>'
    preparation = ''.join(f'<li><label><input type="checkbox"><span>{e(p["title"])}。{e(p["body"])}</span></label></li>' for p in d['preparation'])
    trouble = ''.join(f'<details><summary>{e(t["symptom"])}</summary><p>{e(t["action"])}</p>{prompt("prompt-help-"+str(i),t["prompt"])}</details>' for i,t in enumerate(d['troubleshooting']))
    runtime = '<ul>' + ''.join(f'<li>第 {step} 步生成 <code>prompts/runtime/{e(name)}</code></li>' for name, step in d['mainline_protocol']['runtime_prompt_generation'].items()) + '</ul>'
    example = json.loads((ROOT / 'source/verified-example.json').read_text())
    table = '<table><thead><tr><th>阶段</th><th>模型 tokens</th><th>阶段耗时</th><th>调用</th></tr></thead><tbody>' + ''.join(f'<tr><td>{e(s["label"])}</td><td>{s["tokens"]:,}</td><td>{s["elapsed_seconds"]:.3f} 秒</td><td>{s["calls"]}</td></tr>' for s in example['stages']) + '</tbody></table>'
    source_links = ''.join(f'<li><a href="{e(s["url"])}" target="_blank" rel="noopener">{e(s["title"])} ↗</a><span>{e(s["note"])}</span></li>' for s in d['sources'])
    return f'''<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta name="description" content="{e(d['subtitle'])}"><title>{e(d['title'])} · 第二讲</title><link rel="stylesheet" href="assets/handout.css"><script src="assets/handout.js" defer></script></head><body>
<a class="skip" href="#content">跳到讲义</a><aside class="sidebar"><a class="brand" href="#top"><span class="brand-mark">er</span><span>Earnings Review<small>第二讲 · 实操讲义</small></span></a><nav aria-label="讲义目录">{nav}</nav><div class="reading-status"><span>我的搭建记录</span><strong id="completion-count">0 / 9 步</strong><p>勾选只记录学习进度，<br>不代表财务核验通过。</p></div></aside>
<main id="content"><header id="top"><p class="eyebrow">从本地 PDF 到可核验的复盘网页</p><h1>{e(d['title'])}</h1><p class="subtitle">{e(d['subtitle'])}</p><p>{e(d['lead'])}</p><div class="downloads"><a href="https://suibe-ai-agent.netlify.app/start-here/">零基础必看入门</a><a class="primary" href="earnings-review-materials.zip" download>下载实操材料包</a><a href="#step-0">从第 0 步开始 ↘</a><a href="PROMPTS.md" download>全部 Prompt</a><a href="讲义.md" download>Markdown 讲义</a></div><p class="small">{e(d['materials'])}</p></header>
<section class="intro" id="readiness"><h2>开始前，确认这几项</h2><p>先读<a href="https://suibe-ai-agent.netlify.app/start-here/">零基础必看入门</a>，完成工具、工作目录、运行环境和服务授权的相关准备。做过的不用重做，逐项确认后继续读下面的讲义。</p><ul class="readiness-checks">{preparation}</ul><p>暂缺服务授权时，可以先搭建离线模块，第 8 步真实运行前补齐。第 0 步会分别核对离线开发和真实运行条件。准备已确认，就从<a href="#workflow-map">程序与模型怎样配合</a>继续。</p></section>
{overview_html(d['overview'])}
<section class="intro" id="start"><h2>先分清谁在搭建，谁在运行</h2><div class="roles">{roles}</div><p>{e(d['fixed'])}</p><h3 class="flow-heading">同一流程在网页中的六个运行步骤</h3>{flow}<details class="success"><summary>做到什么程度算完成</summary>{items(d['success'])}</details>{material_guide_html(d['material_guide'])}<h2 class="prepare-title">打开本讲项目</h2><p>{e(d['project_setup'])}</p><details class="success"><summary>使用 OpenCode 时，本讲的参考模型档位</summary><p>{e(d['coding_profile_note'])}</p></details><div class="cadence"><strong>跟做方式</strong><p>{e(d['cadence'])}</p></div></section>
{''.join(step_html(s) for s in d['steps'])}
<section class="section" id="extensions"><p class="eyebrow">核心程序完成后</p><h2>继续验证，而不是急着扩大功能</h2><p>下面按需要选做。先保留已完成的程序和真实回执，再扩展样本、模型或失败路径。</p>{''.join(extension_html(x,i) for i,x in enumerate(d['extensions']))}</section>
<section class="section" id="help"><h2>卡住时，把这一条发给 Agent</h2><p>不用先猜技术原因。让 Agent 读取当前项目和真实日志，明确问题后再修改。</p><div class="help">{trouble}</div></section>
<section class="section" id="finish"><h2>交付前，逐条检查</h2>{items(d['checklist'])}<p class="stop-rule">{e(d['stopRule'])}</p><h3>一份完整运行账本长什么样</h3><p>以下是 {e(example['date'])} 课前顺丰 27B 示例，非学习者当前运行结果。两层均为 10/10，共 {example['usage']['requests']} 次模型调用，{example['usage']['total_tokens']:,} tokens，流程 {example['workflow_seconds']:.3f} 秒。包含一次文本续跑和两次视觉续跑。不同运行可能成功、补证或停止，消耗也会变化。</p><div class="table-scroll">{table}</div><p class="small">阶段耗时累计该阶段记录的调用与程序操作；总流程还含阶段切换等开销。编程 Agent 开发对话的 tokens 与产品运行账本分开统计。</p><figure><a href="assets/earnings-review-example.jpg" target="_blank"><img src="assets/earnings-review-example.jpg" alt="顺丰课前示例，显示真实六阶段、97440 tokens、两层10/10与最终复盘" loading="lazy"></a><figcaption>示例产品截图，可点击放大。学习者的页面以自己的运行结果为准。</figcaption></figure></section>
<section class="section" id="runtime-prompts"><h2>附录：第5–7步生成运行时提示词</h2><p>前面每步的大框发给你的编程 Agent。它按任务书与 contracts 生成下列文件，并接入程序实际发给财报模型的请求。初始材料包不预置这四份文件；生成后会随本轮程序一起冻结保存。</p>{runtime}<details><summary>依赖与本地文件约定</summary><p>Python 使用项目虚拟环境（这个项目独立的一套 Python 运行环境，不影响电脑里其他 Python），安装 pypdf。页图可以用已有 Poppler 工具或由 Agent 选择合适的本机实现，必须记录渲染器及版本。当前示例在 macOS 实跑，Windows 需要适配启动和文件锁，不能把 Unix 代码原样照搬。</p><p>同花顺 CLI 的当前安装包为 @hithink-tech/hithink-finance-cli，本机已核对的版本要求 Node.js ≥22.12.0。若已安装先检查，不为课堂重装。让 Agent 读取当前 schema 与官方内置帮助，认证使用隐藏输入，结果原样落盘。</p><p>财报服务从服务端读取自己的 API Key。编程 Agent 的订阅或登录不自动赋予这个程序 API 权限。模型 ID、图像支持、额度与数据权限以账号实际检查为准，不用离线测试代替授权验证。</p></details></section>
<footer><h2>参考与验证范围</h2><ul class="sources">{source_links}</ul><p>接口与文档核对日期：{e(d['updated'])}。</p><p>{e(d['limits'])}</p><p>本地实操材料。程序运行使用自己的模型与数据服务授权。</p></footer><div id="copy-status" role="status" aria-live="polite"></div></main></body></html>'''


def markdown():
    d=DATA
    overview=d['overview']
    out=['# '+d['title'],d['edition'],d['lead'],'## 开始前，确认这几项',
         '先读[零基础必看入门](https://suibe-ai-agent.netlify.app/start-here/)，完成相关准备。做过的不用重做，逐项确认后继续读下面的讲义。',
         '\n'.join('- [ ] '+p['title']+'。'+p['body'] for p in d['preparation']),
         '暂缺服务授权时，可以先搭建离线模块，第 8 步真实运行前补齐。第 0 步会分别核对离线开发和真实运行条件。',
         '## '+overview['title'],overview['lead']]
    diagram=['flowchart TD']
    for p in overview['nodes']:
        label=p['owner']+'：'+p['label']
        diagram += [f'    {p["id"]}{{"{label}"}}' if p['kind']=='check' else f'    {p["id"]}["{label}"]']
    for a,b in zip(overview['nodes'],overview['nodes'][1:]):
        diagram += [f'    {a["id"]} -->|通过| {b["id"]}' if a['kind']=='check' else f'    {a["id"]} --> {b["id"]}']
    diagram += ['    feedback["程序交回失败原因和已有进度，不给答案或正确页码"]','    stopped["停止，保存失败原因与已有证据"]']
    for p in overview['nodes']:
        if p['kind']=='check': diagram += [f'    {p["id"]} -->|未通过且可补证| feedback']
    diagram += ['    feedback -->|文本候选补证| locate','    feedback -->|视觉自身补证| vision','    feedback -->|预算或停止条件触发| stopped']
    out += ['```mermaid\n'+'\n'.join(diagram)+'\n```',overview['calls_note'],'### 每一步具体做什么','| 步骤 | 谁执行 | 输入、操作与输出 |\n| --- | --- | --- |\n'+'\n'.join('| '+str(i+1)+'．'+p['label']+' | '+p['owner']+' | '+p['work']+' |' for i,p in enumerate(overview['steps'])),'### '+overview['feedback_title'],'\n'.join(str(i+1)+'. '+x for i,x in enumerate(overview['feedback_steps'])),overview['feedback_note'],overview['delivery_note'],overview['mapping_note'],'## 分清三个角色']
    out += ['- '+r['who']+'：'+r['task'] for r in d['roles']]
    out += [d['fixed'],'## 完成标准','\n'.join('- '+x for x in d['success']),'## 同一流程在网页中的六个运行步骤']
    out += ['- '+s['label']+' · '+s['owner']+'：'+s['work'] for s in d['flow']]
    guide=d['material_guide']
    out += ['## '+guide['title'],guide['lead'],'| 文件或文件夹 | 里面是什么 | 这次怎么用 |\n| --- | --- | --- |\n'+'\n'.join('| `'+item['path']+'` | '+item['contents']+' | '+item['use']+' |' for item in guide['items']),'\n'.join('- '+note for note in guide['notes'])]
    out += ['## 打开本讲项目',d['project_setup'],
            '<details><summary>使用 OpenCode 时，本讲的参考模型档位</summary>\n\n'+d['coding_profile_note']+'\n\n</details>']
    out += [d['cadence']]
    for s in d['steps']:
        out += ['## 第'+s['number']+'步：'+s['title'],s['goal'],'### 现在怎么做','\n'.join('- '+x for x in s['actions']),'### 发给你的编程 Agent','```text\n'+s['prompt']+'\n```']
        if s.get('after_click_prompt'):out += ['### 点击后，发这条查看本轮运行','```text\n'+s['after_click_prompt']+'\n```']
        out += ['### 应该看到','\n'.join('- '+x for x in s['expected']),'### 确认后再继续','\n'.join('- '+x for x in s['checks']),'本步产物：'+'、'.join('`'+f+'`' for f in s['files']),'### 修复Prompt','```text\n'+s['repair']+'\n```']
    out += ['## 扩展验证']
    for x in d['extensions']:
        out += ['### '+x['title'],x['why'],'```text\n'+x['prompt']+'\n```','\n'.join('- '+c for c in x['checks'])]
    out += ['## 卡住时']
    for x in d['troubleshooting']:
        out += ['### '+x['symptom'],x['action'],'```text\n'+x['prompt']+'\n```']
    out += ['## 交付检查','\n'.join('- [ ] '+x for x in d['checklist']),d['stopRule']]
    example=json.loads((ROOT/'source/verified-example.json').read_text())
    out += ['## 课前示例账本',f"{example['date']}顺丰27B示例，不是学习者当前结果。两层10/10，{example['usage']['requests']}次调用、{example['usage']['total_tokens']:,}tokens、{example['workflow_seconds']:.3f}秒。示例仅说明怎样读取账本，不保证下一次运行有相同结果或消耗。",
            '| 阶段 | 模型tokens | 阶段秒数 | 调用数 |\n| --- | ---: | ---: | ---: |\n'+'\n'.join('| '+s['label']+' | '+str(s['tokens'])+' | '+str(s['elapsed_seconds'])+' | '+str(s['calls'])+' |' for s in example['stages']),
            '阶段耗时累计已记录调用与操作，总流程另含切换开销；编程Agent开发对话的tokens另计。','## 第5–7步生成运行时提示词','编程 Agent 按任务书与 contracts 生成以下文件，再接入程序实际发给财报模型的请求。初始材料包不预置全文，生成后随本轮程序一起冻结保存。']
    out += [f'- 第 {step} 步生成 `prompts/runtime/{name}`。' for name, step in d['mainline_protocol']['runtime_prompt_generation'].items()]
    out += ['## 参考与验证范围','\n'.join('- ['+s['title']+']('+s['url']+')：'+s['note'] for s in d['sources']),d['limits']]
    return '\n\n'.join(out)+'\n'


def all_prompts():
    out=['# Earnings Review · 逐步搭建Prompt','主Prompt按0至8顺序发送，每步检查后再继续。扩展按需选做。运行时提示词在第5–7步生成，保存到项目prompts/runtime中。']
    for s in DATA['steps']:
        out += ['## 第'+s['number']+'步：'+s['title'],'```text\n'+s['prompt']+'\n```']
        if s.get('after_click_prompt'):out += ['### 点击后，查看本轮运行','```text\n'+s['after_click_prompt']+'\n```']
        out += ['### 本步修复','```text\n'+s['repair']+'\n```']
    for x in DATA['extensions']+DATA['troubleshooting']:
        out += ['## '+x.get('title',x.get('symptom')),'```text\n'+x['prompt']+'\n```']
    return '\n\n'.join(out)+'\n'


def zip_entry(archive, name, content):
    date = tuple(int(x) for x in DATA['updated'].split('-'))
    info = zipfile.ZipInfo(str(name), date + (0, 0, 0))
    info.compress_type = zipfile.ZIP_DEFLATED
    info.external_attr = 0o100644 << 16
    archive.writestr(info, content)


def main():
    prepare()
    write(ROOT/'index.html',render_html())
    write(ROOT/'讲义.md',markdown())
    write(ROOT/'PROMPTS.md',all_prompts())
    archive=ROOT/'earnings-review-materials.zip'
    ROOT.chmod(ROOT.stat().st_mode|stat.S_IWUSR)
    if archive.exists():archive.chmod(archive.stat().st_mode|stat.S_IWUSR)
    with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED) as z:
        project=ROOT/'materials/earnings-review'
        manifest=json.loads((project/'MATERIALS.json').read_text())
        paths=[project/'AGENTS.md',project/'TASKBOOK.md',project/'MATERIALS.json',project/'reports/SOURCES.json']
        paths += [project/'reports'/r['filename'] for r in manifest['pdfs']]
        paths += list((project/'contracts').glob('*.json'))
        paths += [project/name for name in manifest['acceptance_hashes']]
        for p in sorted(paths):
            assert p.is_file() and not p.is_symlink(),p
            zip_entry(z,p.relative_to(ROOT/'materials'),p.read_bytes())
    bundle=ROOT/'EarningsReview-第二讲讲义包.zip'
    if bundle.exists():bundle.chmod(bundle.stat().st_mode|stat.S_IWUSR)
    with zipfile.ZipFile(bundle,'w',zipfile.ZIP_DEFLATED) as z:
        for name in ['index.html','讲义.md','PROMPTS.md','earnings-review-materials.zip']:
            zip_entry(z,'earnings-review-lesson2/'+name,(ROOT/name).read_bytes())
        for p in sorted((ROOT/'assets').glob('*')):
            if p.is_file():zip_entry(z,'earnings-review-lesson2/assets/'+p.name,p.read_bytes())
        zip_entry(z,'earnings-review-lesson2/先读我.txt','解压后打开index.html阅读讲义，也可以阅读讲义.md。\n\n讲义里的主Prompt按第0至第8步发给你的编程 Agent（Codex、Claude Code、Cursor、Kimi Code 等任意一种，或 OpenCode 搭配 DeepSeek，都可以）。共同规则已放进项目AGENTS.md，每条主Prompt只写本步任务；自行修正公开检查失败，通过后再发下一条。仅0–8九条构成主线；折叠修复Prompt为人工诊断备用，不能用于证明九条主线已跑通。\n\nearnings-review-materials.zip是实操材料，再解压得到earnings-review文件夹。它的根目录下应有AGENTS.md、TASKBOOK.md、reports、contracts和acceptance。用你的编程 Agent 打开这个文件夹作为新项目，不要把讲义阅读目录当成应用项目。\n\n材料没有成品应用或预填财务答案，代码由自己的Agent分步搭建。运行时提示词不预置，第5步生成locate.md/extract.md，第6步生成vision.md，第7步生成feedback.md，保存在prompts/runtime并接入实际请求。环境、模型与同花顺授权在第0步检查。前面的合成检查不发生成请求；完整真实运行在第8步由学习者手动点击。\n')
    print(json.dumps({'main_steps':len(DATA['steps']),'copyable_prompts':len(DATA['steps'])*2+len(DATA['extensions'])+len(DATA['troubleshooting'])+sum('after_click_prompt' in s for s in DATA['steps']),'archive_bytes':archive.stat().st_size},ensure_ascii=False))


if __name__ == '__main__':main()
