"""Use lesson two's handout structure for the announcement-agent workshop."""
from html import escape
from html.parser import HTMLParser
import re

import markdown


class PlainText(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts = []

    def handle_data(self, value):
        self.parts.append(value)

    def handle_endtag(self, tag):
        if tag in {"p", "li"}:
            self.parts.append("\n")


def md(value):
    result = markdown.markdown(value.strip(), extensions=["tables", "fenced_code", "attr_list"])
    result = result.replace("<table>", '<table class="process-table">')
    return re.sub(r"(<table\b.*?</table>)", r'<div class="table-scroll" tabindex="0" aria-label="表格，可横向滚动">\1</div>', result, flags=re.S)


def split_sections(source, level=2):
    chunks = re.split(r"(?m)^" + "#" * level + r" (.+)\n", source)
    return chunks[0].strip(), [(chunks[i].strip(), chunks[i + 1].strip()) for i in range(1, len(chunks), 2)]


def render(source, *, asset_prefix="assets/", back="../index.html"):
    lead, sections = split_sections(source)
    title = re.search(r"^# (.+)$", lead, re.M).group(1)
    intro = re.sub(r"^# .+\n", "", lead, count=1).strip()
    paragraphs = intro.split("\n\n")
    is_lesson = title == "从零搭建公告事件智能体"
    prompt_index = 0

    def prompts(text, purpose="需求或反馈"):
        nonlocal prompt_index
        value = md(text)

        def box(match):
            nonlocal prompt_index
            prompt_index += 1
            plain = PlainText()
            plain.feed(match.group(1))
            identity = "prompt-" + str(prompt_index)
            return '<div class="prompt-box"><div class="prompt-toolbar"><span>按自己的进度调整，再发给编程Agent</span><button type="button" class="copy" data-copy="' + identity + '" aria-label="复制第' + str(prompt_index) + '句' + purpose + '">复制这句</button></div><pre id="' + identity + '">' + escape("".join(plain.parts).strip()) + '</pre></div>'

        return re.sub(r"<blockquote>\s*(.*?)\s*</blockquote>", box, value, flags=re.S)

    nav, body = [], []
    if is_lesson:
        subtitle = paragraphs.pop(0)
        body.append('<header id="top"><p class="eyebrow">第三讲 · 从巨潮公告到事件日历</p><h1>' + escape(title) + '</h1><p class="subtitle">' + escape(subtitle) + '</p>' + md("\n\n".join(paragraphs)) + '<div class="downloads"><a href="' + back + '">← 讲座主页</a><a href="example/index.html">查看公告事件智能体成品 ↗</a><a class="primary" href="lesson3-starter.zip" download>下载起步材料包</a><a href="#step-0">从第0步开始 ↘</a><a href="PROMPTS.md" download>短需求与反馈</a><a href="lesson.md" download>Markdown讲义</a></div><p class="small">从自己的新目录开始。原公告由Agent取得，验证材料与教师参考按进度另行使用。</p></header>')
    else:
        body.append('<header id="top"><p class="eyebrow">第三讲 · 教师备课参考</p><h1>' + escape(title) + '</h1>' + md(intro) + '<div class="downloads"><a href="' + back + '">← 返回讲义</a></div></header>')

    intro_ids = ["workflow-map", "start"]
    for index, (heading, content) in enumerate(sections):
        step = re.match(r"第(\d+)步[：:]\s*(.+)", heading)
        if step:
            number, step_title = step.groups()
            identity = "step-" + number
            nav.append('<a href="#' + identity + '"><span>' + number + '</span>' + escape(step_title) + '</a>')
            goal, blocks = split_sections(content, 3)
            parts = dict(blocks)
            body.append('<section class="step" id="' + identity + '"><div class="step-title"><span class="step-number">' + number + '</span><div><span class="eyebrow">搭建步骤 ' + number + '</span><h2>' + escape(step_title) + '</h2></div></div><div class="goal">' + md(goal) + '</div><div class="actions"><h3>现在怎么做</h3>' + md(parts.get("现在怎么做", "")) + '</div>' + prompts(parts.get("发给你的Agent", ""), "需求") + '<div class="checkpoint"><div><h3>应该看到</h3>' + md(parts.get("应该看到", "")) + '</div><div><h3>确认后再继续</h3>' + md(parts.get("确认后再继续", "")) + '</div></div>')
            if parts.get("最终验收"):
                body.append('<div class="acceptance"><h3>最终验收</h3>' + md(parts["最终验收"]) + '</div>')
            body.append('<div class="files"><span>本步产物</span>' + md(parts.get("本步产物", "")) + '</div><details class="repair"><summary>本步没做好？看反馈例子</summary>' + prompts(parts.get("卡住时", ""), "反馈") + '</details><label class="completion"><input type="checkbox" data-complete="' + identity + '">我已打开结果并核对这一步</label></section>')
        elif is_lesson and index < len(intro_ids):
            identity = intro_ids[index]
            nav.append('<a href="#' + identity + '">' + ("整体步骤" if index == 0 else "课前准备与材料") + '</a>')
            if identity != "start":
                body.append('<section class="' + ("overview" if identity == "workflow-map" else "intro") + '" id="' + identity + '"><h2>' + escape(heading) + '</h2>' + md(content) + '</section>')
            else:
                opening, blocks = split_sections(content, 3)
                parts = dict(blocks)
                prep = [(key, value) for key, value in blocks if key not in {"分清材料的用途", "这次跟做怎样推进"}]
                body.append('<section class="intro" id="start"><h2>' + escape(heading) + '</h2>' + md(opening) + '<section id="materials-guide"><h3 class="prepare-title">先认识材料包</h3>' + md(parts.get("分清材料的用途", "")) + '</section><h3 class="prepare-title">打开自己的新项目</h3><ol class="preparation">' + ''.join('<li><h3>' + escape(key) + '</h3>' + md(value) + '</li>' for key, value in prep) + '</ol><div class="cadence"><strong>跟做方式</strong>' + md(parts.get("这次跟做怎样推进", "")) + '</div></section>')
        else:
            identity = ("extensions" if "完成主线" in heading else "help" if "卡住时" in heading else "references") if is_lesson else "report-" + str(index)
            nav.append('<a href="#' + identity + '">' + escape(heading) + '</a>')
            body.append('<section class="section" id="' + identity + '"><h2>' + escape(heading) + '</h2>' + prompts(content) + '</section>')
    step_count = sum(bool(re.match(r"第\d+步[：:]", heading)) for heading, _ in sections)
    progress = '<div class="reading-status">自己的搭建进度<strong id="completion-count">0 / ' + str(step_count) + ' 步</strong><p>勾选只记录你已检查哪一步。原文、测试和真实运行记录才是验收依据。</p></div>' if is_lesson else ""
    return '<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta name="description" content="从投研需求出发，搭建有展示产品、能自主取数和定时更新的公告事件智能体。"><title>' + escape(title) + ' · 第三讲</title><link rel="stylesheet" href="' + asset_prefix + 'handout.css"><link rel="stylesheet" href="' + asset_prefix + 'lesson3.css"><script src="' + asset_prefix + 'handout.js" defer></script></head><body><a class="skip" href="#content">跳到讲义</a><aside class="sidebar"><a class="brand" href="#top"><span class="brand-mark">ae</span><span>公告事件智能体<small>第三讲 · 实操讲义</small></span></a><nav aria-label="讲义目录">' + ''.join(nav) + '</nav>' + progress + '</aside><main id="content">' + ''.join(body) + '<footer>先实际做出一小步，再检查和迭代。保留原始来源、模型失败与运行记录。</footer></main><p id="copy-status" role="status" aria-live="polite"></p></body></html>'
