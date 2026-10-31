"""Source-bound participation excerpts and deadline terminology."""
import hashlib
from html import escape
from pathlib import Path
import re
from urllib.parse import urlsplit

from pypdf import PdfReader


def participation_excerpts(notice):
    """Quote the participation section by physical page, only from the bound PDF."""
    if "participation_evidence" in notice and not notice.get("pdf_path"):
        return notice["participation_evidence"]
    path = notice.get("pdf_path")
    if not path:
        return []
    try:
        if hashlib.sha256(Path(path).read_bytes()).hexdigest() != notice.get("pdf_sha256"):
            return []
        pages = [source.extract_text() or "" for source in PdfReader(path).pages]
        primary, supplemental, started, finished, section = [], [], False, False, None
        for page, text in enumerate(pages, 1):
            for sentence in re.finditer(r"[^。！？]+(?:[。！？]|$)", text):
                finish = sentence.end()
                terminal = re.search(r"(?m)^[ \t]*(?:[一二三四五六七八九十\d]+[、．.][ \t]*)?(?:联系人|联系方式|联系电话|咨询办法|其他事项|特此公告|参加人员|出席人员|出席本次[^\n]{0,16}人员)", sentence.group())
                if terminal:
                    finish = sentence.start() + terminal.start()
                quote = text[sentence.start():finish].strip()
                compact = re.sub(r"\s+", "", quote)
                access = re.search(r"投资者可|登录|登陆|访问|扫码|扫描|扫一扫|搜索|微信公众号|小程序|参会电话|拨打|报名|电话外呼", compact)
                questions = re.search(r"提问|问题征集|征集.{0,20}问题|预先提供", compact) and re.search(r"通过|邮箱|访问|页面|链接|小程序|平台", compact)
                if not access and not questions:
                    continue
                if re.search(r"回看|上次|前次|此前|(?:召开|结束)后.*(?:查看|回放)|查看.{0,40}(?:召开情况|主要内容)", compact):
                    continue
                if quote:
                    supplemental.append((page, sentence.start(), finish))
            if finished:
                continue
            begin = 0
            if not started:
                heading = re.search(
                    r"(?m)^[ \t]*(?:(?P<section>[一二三四五六七八九十]+|\d+)[、．.]|[（(][一二三四五六七八九十\d]+[）)])?[ \t]*"
                    r"(?:投\s*资\s*者\s*)?(?:报\s*名\s*及\s*)?(?:参\s*加|参\s*与|参\s*会)\s*(?:方\s*式|办\s*法)(?=[ \t]*(?:[:：]|$))[ \t]*[:：]?[ \t]*", text)
                if not heading:
                    continue
                started = True
                section = heading.group("section")
                begin = heading.end()
            body = text[begin:]
            siblings = list(re.finditer(r"(?m)^[ \t]*([一二三四五六七八九十]+|\d+)[、．.][ \t]*(\S[^\n]*)", body))
            end = next((candidate for candidate in siblings if _participation_section_ends(section, candidate)), None)
            closing = re.search(r"(?m)^[ \t]*特此公告[。．.]?[ \t]*$", body)
            limits = [match.start() for match in (end, closing) if match]
            finish = begin + min(limits) if limits else len(text)
            if text[begin:finish].strip():
                primary.append((page, begin, finish))
            finished = bool(limits)
        if not primary and not supplemental:
            for page, text in enumerate(pages, 1):
                heading = re.search(r'(?m)^[ \t]*([一二三四五六七八九十\d]+)[、．.][ \t]*'
                                    r'会\s*议\s*(?:召\s*开\s*)?方\s*式[ \t]*[:：]', text)
                if not heading:
                    continue
                body = text[heading.end():]
                following = list(re.finditer(r'(?m)^[ \t]*([一二三四五六七八九十\d]+)[、．.][ \t]*(\S[^\n]*)', body))
                end = next((candidate for candidate in following if _participation_section_ends(heading[1], candidate)), None)
                closing = re.search(r'(?m)^[ \t]*特此公告[。．.]?[ \t]*$', body)
                limits = [match.start() for match in (end, closing) if match]
                primary.append((page, heading.end(), heading.end() + min(limits) if limits else len(text)))
                break
        return _merge_participation_spans(pages, primary, supplemental)
    except Exception:
        return []


def _printed_urls(text):
    compact = re.sub(r"\s+", "", text)
    urls = re.findall(r"https?://[A-Za-z0-9._~:/?#@!$&()*+,;=%-]+", compact)
    return {re.sub(r"^https?://", "", url.rstrip(".,;:)/")) for url in urls}


def _merge_participation_spans(pages, primary, supplemental):
    compact_primary = re.sub(r"\s+", "", "".join(pages[page - 1][begin:end] for page, begin, end in primary))
    primary_urls = _printed_urls(compact_primary)
    route_cues = ("手机端", "网络端", "英文会议", "中文会议", "同声传译", "审核", "短信", "电话外呼", "小程序", "微信公众号", "参会电话", "会议密码", "提问", "问题征集", "预报名", "报名", "点击", "选择", "搜索", "发送", "邮箱")
    candidates = list(primary)
    for page, begin, end in supplemental:
        text = pages[page - 1][begin:end]
        compact = re.sub(r"\s+", "", text)
        if compact_primary and compact in compact_primary:
            continue
        if any(p == page and start <= begin and finish >= end for p, start, finish in primary):
            continue
        urls = _printed_urls(text)
        if primary and urls and urls <= primary_urls and not any(cue in compact and cue not in compact_primary for cue in route_cues):
            continue
        candidates.append((page, begin, end))
    merged = []
    for page, begin, end in sorted(candidates):
        if merged and merged[-1][0] == page and begin <= merged[-1][2]:
            merged[-1] = (page, merged[-1][1], max(end, merged[-1][2]))
        else:
            merged.append((page, begin, end))
    result, seen = [], set()
    for page, begin, end in merged:
        quote = pages[page - 1][begin:end].strip()
        key = re.sub(r"\s+", "", quote)
        if key and key not in seen:
            seen.add(key)
            result.append({"page": page, "quote": quote})
    return result


def _participation_section_ends(section, candidate):
    number, title = candidate.groups()
    if section:
        if section.isdigit() != number.isdigit():
            return False
        if section.isdigit():
            return int(number) > int(section)
        numbers = {"一": 1, "二": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7,
                   "八": 8, "九": 9, "十": 10, "十一": 11, "十二": 12}
        return numbers.get(number, 0) > numbers.get(section, 99)
    return bool(re.search(r"联系|咨询|其他事项|特别提示|风险提示", title))


def participation_html(excerpts):
    """Display every visible participation step, linking only printed web URLs."""
    paragraphs, current = [], ""
    for excerpt in excerpts:
        lines = excerpt.get("quote", "").strip().splitlines()
        if lines and lines[0].strip() == str(excerpt.get("page")):
            lines.pop(0)
        if lines and lines[-1].strip() == str(excerpt.get("page")):
            lines.pop()
        for index, line in enumerate(lines):
            line = re.sub(r"(?<=[\u3400-\u9fff])[ \t]+(?=[\u3400-\u9fff])", "", line.strip())
            line = re.sub(r'^[\uf06c\uf0b7]\s*', '', line)
            if (index < 3 or index >= len(lines) - 3) and re.fullmatch(r"(?:第\s*\d+\s*页[，,\s]*(?:共\s*\d+\s*页)?|\S{1,16}董事会公告)", line):
                continue
            if not line:
                continue
            starts = re.match(r"(?:[（(][一二三四五六七八九十\d]+[）)]|路径\s*\d+\s*[：:]|\d+[、．.])", line)
            if current and (starts or re.search(r"[。！？；]$", current)):
                paragraphs.append(current)
                current = ""
            current += line
    if current:
        paragraphs.append(current)

    def link_text(text):
        result, position = [], 0
        for match in re.finditer(r"https?://[A-Za-z0-9._~:/?#@!$&()*+,;=%-]+", text):
            url = match.group().rstrip(".,;:)")
            parsed = urlsplit(url)
            result.append(escape(text[position:match.start()]))
            if parsed.scheme in {"https", "http"} and parsed.hostname:
                result.append('<a href="' + escape(url, quote=True) + '" target="_blank" rel="noopener">' + escape(url) + '</a>')
            else:
                result.append(escape(url))
            position = match.start() + len(url)
        result.append(escape(text[position:]))
        return "".join(result)

    rendered = []
    for paragraph in paragraphs:
        heading = bool(re.fullmatch(r"[（(][一二三四五六七八九十\d]+[）)][^。！？；：:]{1,35}", paragraph))
        tag = "h4" if heading else "p"
        rendered.append("<" + tag + ">" + link_text(paragraph) + "</" + tag + ">")
    return "".join(rendered)


def _deadline_role(text):
    registration = "预报名截止" if "预报名" in text else "报名截止" if "报名" in text else None
    question = bool(re.search(r"提问|问题征集|征集.{0,4}问题|提交.{0,4}问题", text))
    if registration and question:
        return None
    return registration or ("提问截止" if question else None)


def deadline_label(notice):
    evidence=notice.get("extraction", {}).get("deadline_evidence") or {}
    quote = evidence.get("quote", "") or ''.join(part['quote'] for part in evidence.get('parts',[]))
    direct = _deadline_role(quote)
    if direct:
        return direct
    needle = re.sub(r"\s+", "", quote)
    if not needle:
        return "截止时间"
    for excerpt in participation_excerpts(notice):
        text = re.sub(r"\s+", "", excerpt["quote"])
        start = text.find(needle)
        if start < 0:
            continue
        headings = list(re.finditer(r"[（(][一二三四五六七八九十0-9]+[）)]", text[:start]))
        begin = headings[-1].start() if headings else start
        end = re.search(r"[（(][一二三四五六七八九十0-9]+[）)]", text[start + len(needle):])
        segment = text[begin:start + len(needle) + end.start() if end else None]
        role = _deadline_role(segment)
        if role:
            return role
    return "截止时间"


def event_deadline_label(event, notices):
    for identity in reversed(event.get("source_ids", [])):
        notice = notices.get(identity, {})
        value = notice.get("extraction", {})
        if value.get("question_deadline_date") == event.get("question_deadline_date"):
            label = deadline_label(notice)
            if label != "截止时间":
                return label
    return "截止时间"
