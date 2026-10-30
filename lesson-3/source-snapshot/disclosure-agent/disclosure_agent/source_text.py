"""Source-bound participation excerpts and deadline terminology."""
import hashlib
from pathlib import Path
import re

from pypdf import PdfReader


def participation_excerpts(notice):
    """Quote the participation section by physical page, only from the bound PDF."""
    if "participation_evidence" in notice:
        return notice["participation_evidence"]
    path = notice.get("pdf_path")
    if not path:
        return []
    try:
        if hashlib.sha256(Path(path).read_bytes()).hexdigest() != notice.get("pdf_sha256"):
            return []
        result, started = [], False
        for page, source in enumerate(PdfReader(path).pages, 1):
            text = source.extract_text() or ""
            if not started:
                heading = re.search(r"投资者参[加与]方式", text)
                if not heading:
                    continue
                started = True
                text = text[heading.end():]
            end = re.search(r"(?m)^\s*[一二三四五六七八九十]+[、．.]\s*\S", text)
            quote = text[:end.start() if end else None].strip()
            if quote:
                result.append({"page": page, "quote": quote})
            if end:
                break
        return result
    except Exception:
        return []


def _deadline_role(text):
    registration = "预报名截止" if "预报名" in text else "报名截止" if "报名" in text else None
    question = bool(re.search(r"提问|问题征集|征集.{0,4}问题|提交.{0,4}问题", text))
    if registration and question:
        return None
    return registration or ("提问截止" if question else None)


def deadline_label(notice):
    quote = (notice.get("extraction", {}).get("deadline_evidence") or {}).get("quote", "")
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
