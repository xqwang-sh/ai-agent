"""Build a draft lesson, separate materials and a public projection of real runs."""
from __future__ import annotations

import argparse
import ast
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
from html import escape
import json
from pathlib import Path
import re
import shutil
import sys
import zipfile

import markdown
from pypdf import PdfReader

ROOT = Path(__file__).resolve().parent
LESSON = ROOT.parents[1]
APP = ROOT.parent / "disclosure-agent"
EVIDENCE = LESSON / "04-tests/implementation-2026-10-30"
OLD = LESSON / "06-preparation/cninfo-exploration-2026-10-28"
sys.path.insert(0, str(APP))
from disclosure_agent.runner import load_publication, render_calendar


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def jsonl(path):
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def write_jsonl(path, values):
    path.write_text("".join(json.dumps(value, ensure_ascii=False) + "\n" for value in values), encoding="utf-8")


def public(value):
    if isinstance(value, str):
        return value.replace(str(LESSON), "[local lesson]").replace(str(Path.home()), "[user home]")
    if isinstance(value, dict):
        return {key: public(item) for key, item in value.items()}
    if isinstance(value, list):
        return [public(item) for item in value]
    return value


def page(source, target, asset_prefix="assets/", back="../index.html"):
    md = markdown.Markdown(extensions=["tables", "fenced_code", "toc", "attr_list"], extension_configs={"toc": {"toc_depth": "2-2"}})
    body = md.convert(source)
    title = re.search(r"^# (.+)$", source, re.MULTILINE).group(1)
    shell = f'''<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta name="description" content="从投研业务需求开始，搭建从巨潮自主取数、提取、核验和定时运行的公告Agent。"><title>{escape(title)} · 第三讲</title><link rel="stylesheet" href="{asset_prefix}handout.css"><script src="{asset_prefix}handout.js" defer></script></head><body><a class="skip" href="#content">跳到正文</a><aside class="sidebar"><a class="brand" href="#content">公告与事件日历<small>第三讲 · 需求对话与迭代</small></a><nav aria-label="讲义目录">{md.toc}</nav><a class="back" href="{back}">返回课程</a></aside><main id="content"><div class="edition">LOCAL AGENT WORKSHOP · 2026-10-30</div><div class="toolbar"><a href="{asset_prefix}../lesson3-starter.zip">起步材料</a><a href="{asset_prefix}../lesson3-validation.zip">独立验证材料</a><a href="{asset_prefix}../PROMPTS.md">短需求与反馈</a></div><p class="copy-status" id="copy-status" role="status" aria-live="polite"></p>{body}<footer>实际结果与历史测试分开记录。示例页不会在线调用模型，密钥只交给你自己的本机运行环境。</footer></main></body></html>'''
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(shell, encoding="utf-8")


def archive(directory, target):
    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as z:
        for file in sorted(directory.rglob("*")):
            if file.is_file():
                z.write(file, str(Path(directory.name) / file.relative_to(directory)))


def source_files():
    root_files = {"AGENTS.md", "INTERFACES.md", "README.md", "requirements.txt", "config.json", "config-adaptive.json", "run_agent.py", ".gitignore"}
    for file in sorted(APP.rglob("*")):
        relative = file.relative_to(APP)
        included = relative.as_posix() in root_files or relative.parts[0] in {"disclosure_agent", "prompts", "tests"}
        if included and file.is_file() and (file.suffix in {".py", ".json", ".md", ".txt"} or file.name == ".gitignore") and not any(part in {"runtime", "__pycache__", ".pytest_cache", ".git"} for part in relative.parts):
            yield file


def materials(output, staging):
    starter = staging / "lesson3-starter"
    starter.mkdir(parents=True)
    write_json(starter / "sources.json", {"source": "https://www.cninfo.com.cn/", "query_page": "https://www.cninfo.com.cn/new/commonUrl/pageOfSearch?url=disclosure/list/search", "companies": [{"code": "600887", "name": "伊利股份"}, {"code": "688246", "name": "嘉和美康"}]})
    (starter / "README.md").write_text("# 第三讲起步\n\n在自己的英文空目录打开编程Agent，先表达业务需求：我们投研团队要跟踪伊利和嘉和美康的业绩说明会，安排参会和准备问题。想要一个会定时查巨潮、更新会议日历的助手。先和我聊清楚需求。\n\n先核对公司、范围、时间与结果位置，再从真实查询做第一小步。这里没有成品程序、PDF或标准答案。密钥保存在自己的用户级配置中，不粘进代码、网页或共享记录。\n", encoding="utf-8")
    archive(starter, output / "lesson3-starter.zip")
    validation = staging / "lesson3-validation"
    (validation / "pdfs").mkdir(parents=True)
    inputs = jsonl(EVIDENCE / "model-pilot/input.jsonl")
    gold = jsonl(EVIDENCE / "teacher-gold.jsonl")
    new = json.loads((EVIDENCE / "live-source-probe/new-notice.json").read_text())
    inputs.append({key: new[key] for key in ["id", "stock_code", "publication_date", "title", "pdf_sha256"]} | {"text": "\n".join(f"[PAGE {i}]\n{text}" for i, text in enumerate(new["pages"], 1))})
    gold.append(json.loads((EVIDENCE / "new-source-gold.json").read_text()))
    sources = []
    by_id = {row["id"]: row for row in inputs}
    for row in gold:
        identity = row["id"]
        candidates = list((OLD / "pdfs").glob(identity + "-*.pdf")) if identity != new["id"] else [Path(new["pdf_path"])]
        if len(candidates) != 1 or sha(candidates[0]) != row["source_pdf_sha256"]:
            raise ValueError("Unverified source PDF: " + identity)
        path = validation / "pdfs" / (identity + ".pdf")
        shutil.copy2(candidates[0], path)
        source = by_id[identity]
        sources.append({"id": identity, "title": source["title"], "stock_code": source["stock_code"], "publication_date": source["publication_date"], "source_url": "https://static.cninfo.com.cn/finalpage/" + source["publication_date"] + "/" + identity + ".PDF", "pdf_path": "pdfs/" + identity + ".pdf", "sha256": sha(path), "physical_pages": len(PdfReader(path).pages)})
    write_jsonl(validation / "input.jsonl", inputs)
    write_jsonl(validation / "teacher-gold.jsonl", gold)
    write_json(validation / "sources.json", sources)
    shutil.copy2(APP / "prompts/output.schema.json", validation / "output.schema.json")
    tree = ast.parse((APP / "disclosure_agent/extract.py").read_text())
    needed = {"compact", "_date_in", "_time_in", "_source_period", "_meeting_span", "validate_evidence"}
    code = "import json, re\nfrom datetime import date, datetime\nfrom pathlib import Path\nimport jsonschema\nSCHEMA=json.loads((Path(__file__).parent/'output.schema.json').read_text())\nACTIVE_KINDS={'initial','change','postponed','cancelled'}\n\n"
    code += "\n\n".join(ast.unparse(node) for node in tree.body if isinstance(node, ast.FunctionDef) and node.name in needed) + "\n"
    (validation / "evidence.py").write_text(code, encoding="utf-8")
    shutil.copy2(ROOT / "check_gold.py", validation / "check_gold.py")
    (validation / "requirements.txt").write_text("jsonschema>=4.20,<5\n")
    (validation / "README.md").write_text("# 独立验证包\n\n在第一次提取后再使用。12份历史公告、35物理页，用于测试，不代表实时查询。原始模型输入只用原PDF或input.jsonl中的全文，不能将teacher-gold.jsonl或评分差异送给提取模型。候选标准由独立读源和交叉核验形成，待任课教师签字确认，先抽查后冻结自己的确认版本。11份用于原模型比较，第12份为2026-10-30新取得的嘉和三季度通知。\n\n将原始输出整理为每行{\"id\":\"公告ID\",\"result\":{...}}的actual.jsonl，字段遵循output.schema.json。不要人工改答案后称模型通过。\n\n```sh\npython3 -m pip install -r requirements.txt\npython3 check_gold.py --actual /path/to/actual.jsonl --report /path/to/report.json\n```\n\n12条关键字段和证据全部通过才返回pass，缺记录或重复ID失败。评分程序不调用模型，验证包指纹改变则拒绝评分。program checks不能替代人工看原文。sources.json保存每份公告的原链接、物理页数和PDF指纹。修改候选标准前保留原版本，说明原因并重建指纹。\n", encoding="utf-8")
    write_json(validation / "manifest.json", {"gold_status": "candidate; source reviewed by independent agents and cross-checked; teacher sign-off pending", "records": len(sources), "physical_pages": sum(row["physical_pages"] for row in sources), "files": {str(file.relative_to(validation)): sha(file) for file in sorted(validation.rglob("*")) if file.is_file()}})
    archive(validation, output / "lesson3-validation.zip")
    reference = staging / "lesson3-teacher-reference" / "disclosure-agent"
    for source in source_files():
        target = reference / source.relative_to(APP)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
    write_json(reference.parent / "source-manifest.json", {str(file.relative_to(reference)): sha(file) for file in reference.rglob("*") if file.is_file()})
    archive(reference.parent, output / "lesson3-teacher-reference.zip")
    return validation


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--staging", type=Path, required=True)
    args = parser.parse_args()
    output, staging = args.output.resolve(), args.staging.resolve()
    if output.exists() and any(output.iterdir()):
        raise ValueError("Build to a new empty output directory")
    if staging.exists() and any(staging.iterdir()):
        raise ValueError("Build to a new empty staging directory")
    output.mkdir(parents=True, exist_ok=True)
    staging.mkdir(parents=True, exist_ok=True)
    shutil.copytree(ROOT / "assets", output / "assets")
    lesson = (ROOT / "lesson.md").read_text()
    (output / "lesson.md").write_text(lesson, encoding="utf-8")
    prompts = re.findall(r"^> (.+)$", lesson, re.MULTILINE)
    (output / "PROMPTS.md").write_text("# 课堂短需求与反馈\n\n按自己的实际进度选择和修改，不要一次性全部发送。\n\n" + "\n\n".join(f"{i}. {text}" for i, text in enumerate(prompts, 1)) + "\n", encoding="utf-8")
    page(lesson, output / "index.html")
    materials(output, staging)
    state, summary = load_publication(APP / "runtime/live")
    state = deepcopy(state)
    for record in state["notices"].values():
        for key in ["pdf_path", "model_receipts"]:
            record.pop(key, None)
    public_summary = public(summary)
    html = render_calendar(state, public_summary, output / "example")
    html = html.replace("<h1>投研业绩说明会日历</h1>", '<h1>投研业绩说明会日历</h1><p><strong>冻结实跑示例 · 2026-10-30</strong> · <a href="../index.html">返回讲义</a> · 本页只展示当次结果，不在线执行。</p>')
    (output / "example").mkdir()
    (output / "example/index.html").write_text(html, encoding="utf-8")
    write_json(output / "example/summary.json", public_summary)
    write_json(output / "example/events.json", public(list(state["events"].values())))
    evidence = output / "evidence"
    evidence.mkdir()
    for name in ["model-comparison.json", "final-model-evidence-validation-v4.json", "new-source-check.json", "final-code-review-v3.json", "validation-package-pass-v1.json", "validation-package-reject-v1.json"]:
        write_json(evidence / name, public(json.loads((EVIDENCE / name).read_text())))
    for name in ["schedule-real-model-execution.json", "schedule-real-model-summary.json", "schedule-claim-binding-execution.json", "schedule-final-execution.json", "schedule-release-execution.json"]:
        write_json(evidence / name, public(json.loads((EVIDENCE / name).read_text())))
    write_json(evidence / "fresh-build-completion.json", public(json.loads((LESSON / "04-tests/fresh-build-2026-10-30/completion.json").read_text())))
    report = (ROOT / "report.md").read_text()
    (evidence / "report.md").write_text(report, encoding="utf-8")
    page(report, evidence / "report.html", "../assets/", "../index.html")
    snapshot = output / "source-snapshot"
    for source in source_files():
        target = snapshot / "disclosure-agent" / source.relative_to(APP)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
    workshop_sources = [file for file in ROOT.rglob("*") if file.is_file() and "__pycache__" not in file.parts]
    for source in workshop_sources:
        target = snapshot / "lesson3-workshop" / source.relative_to(ROOT)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
    (snapshot / "README.md").write_text("# 第三讲来源快照\n\n仅供审阅与来源核对，维护源在本地课程03-disclosure-calendar/03-source。参考Agent可独立安装，使用说明见disclosure-agent/README.md。讲义构建还需要本地04-tests中的原始证据与06-preparation中的来源PDF，发布库快照不包含私人运行日志。先修改维护源再单向生成，不在快照上形成第二套编辑源。\n", encoding="utf-8")
    write_json(output / "publication.json", {"status": "review candidate; production deployment unchanged", "created_at": datetime.now(timezone.utc).isoformat(), "source_owner": "finance-agent-course/03-disclosure-calendar/03-source", "reference_run_id": summary["run_id"], "scope": "lesson-3 only; static projection; no credentials or online model execution", "files": {str(file.relative_to(output)): sha(file) for file in sorted(output.rglob("*")) if file.is_file()}, "source_files": {**{"lesson3-workshop/" + str(file.relative_to(ROOT)): sha(file) for file in workshop_sources}, **{"disclosure-agent/" + str(file.relative_to(APP)): sha(file) for file in source_files()}}})
    print(json.dumps({"output": str(output), "validation": str(staging / "lesson3-validation"), "reference_run": summary["run_id"], "files": len(list(output.rglob("*")))}, ensure_ascii=False))


if __name__ == "__main__":
    main()
