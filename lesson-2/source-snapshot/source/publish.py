"""Export teaching sources, or a separately sealed historical product projection."""
import argparse
import copy
import hashlib
import json
import re
import shutil
import stat
import sys
from pathlib import Path


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def writable(path):
    path.mkdir(parents=True, exist_ok=True)
    path.chmod(path.stat().st_mode | stat.S_IWUSR)


def write(path, content):
    writable(path.parent)
    if path.exists():
        path.chmod(path.stat().st_mode | stat.S_IWUSR)
    path.write_text(content, encoding="utf-8")


def save(path, data):
    write(path, json.dumps(data, ensure_ascii=False, indent=2) + "\n")


def transfer(source, target):
    writable(target.parent)
    if target.exists():
        target.chmod(target.stat().st_mode | stat.S_IWUSR)
    shutil.copyfile(source, target)


def function(js, name, replacement=""):
    pattern = rf"^(?:async )?function {name}\([^\n]*\) \{{\n.*?^\}}\n"
    output, count = re.subn(pattern, lambda _: replacement + "\n" if replacement else "", js, flags=re.M | re.S)
    assert count == 1, (name, count)
    return output


def export_handout(lesson, target):
    for name in ("index.html", "讲义.md", "PROMPTS.md", "earnings-review-materials.zip", "EarningsReview-第二讲讲义包.zip"):
        transfer(lesson / name, target / name)
    for asset in (lesson / "assets").iterdir():
        if asset.is_file():
            transfer(asset, target / "assets" / asset.name)
    html = (target / "index.html").read_text()
    html = html.replace('<div class="downloads">', '<div class="downloads"><a href="../">← 讲座主页</a><a href="earnings-review/">查看 Earnings Review 成品 ↗</a>', 1)
    html = html.replace('<a href="PROMPTS.md" download>', '<a href="EarningsReview-第二讲讲义包.zip" download>下载完整讲义包</a><a href="PROMPTS.md" download>', 1)
    write(target / "index.html", html)


def export_source_snapshot(lesson, target):
    paths = [lesson / "AGENTS.md", lesson / "README.md", *sorted((lesson / "source").glob("*.py")), *sorted((lesson / "source").glob("*.json")), lesson / "qa/check_handout.py"]
    for folder in (lesson / "source/acceptance", lesson / "materials/earnings-review/prompts/runtime"):
        paths.extend(p for p in sorted(folder.rglob('*')) if p.is_file() and p.suffix in ('.py', '.md') and '__pycache__' not in p.parts)
    records = []
    for source in paths:
        relative = source.relative_to(lesson)
        transfer(source, target / "source-snapshot" / relative)
        records.append({"path": str(relative), "sha256": digest(source), "bytes": source.stat().st_size})
    manifest = {"schema": 1, "canonical_owner": "finance_agent_workshop/lesson2-earnings-review", "purpose": "reviewable teaching source snapshot, not the learner application or a run freeze", "files": records}
    payload = json.dumps(records, sort_keys=True, separators=(',', ':')).encode()
    manifest['source_digest'] = hashlib.sha256(payload).hexdigest()
    save(target / "source-snapshot/SOURCE-SNAPSHOT.json", manifest)
    return manifest['source_digest']


def publish_handout_only(lesson, target):
    publication_path = target / 'publication.json'
    publication = json.loads(publication_path.read_text())
    # The sealed historical example is an independent artifact and stays byte-identical.
    historical = {name: value for name, value in publication['files'].items() if name.startswith('earnings-review/')}
    assert historical and all(digest(target / name) == value for name, value in historical.items())
    export_handout(lesson, target)
    source_digest = export_source_snapshot(lesson, target)
    publication.update(handout_updated=json.loads((lesson/'source/lesson.json').read_text())['updated'], source_snapshot_digest=source_digest)
    publication['files'] = {str(p.relative_to(target)): digest(p) for p in sorted(target.rglob('*')) if p.is_file() and p.name != 'publication.json' and '__pycache__' not in p.parts}
    assert all(publication['files'][name] == value for name, value in historical.items())
    save(publication_path, publication)
    print(json.dumps({'output': str(target), 'mode': 'handout_only', 'historical_files_preserved': len(historical), 'source_digest': source_digest}, ensure_ascii=False))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--site", type=Path, required=True)
    parser.add_argument("--product", type=Path)
    parser.add_argument("--handout-only", action="store_true")
    parser.add_argument("--job")
    args = parser.parse_args()
    lesson = Path(__file__).resolve().parent.parent
    target = args.site.resolve() / "lesson-2"
    if args.handout_only:
        publish_handout_only(lesson, target)
        return
    if not args.product or not args.job:
        parser.error('--product and --job are required unless --handout-only is used')
    product = args.product.resolve()
    sys.path.insert(0, str(product))
    from product import JobStore

    store = JobStore(product)
    job = store.snapshot(args.job)
    assert job["status"] == "candidate_ready" and job["review"]
    assert all(job[k] == {"status": "matched", "matched": 10, "total": 10} for k in ("internal", "external"))
    catalog = store.catalog()
    certificate = json.loads((store.job_dir(args.job) / "verified.json").read_text())
    source_sha = {name: digest(product / "web" / name) for name in ("index.html", "style.css", "app.js")}

    export_handout(lesson, target)
    source_digest = export_source_snapshot(lesson, target)

    demo = target / "earnings-review"
    base = "/lesson-2/earnings-review/"
    data_base = base + "data/"
    published_job = copy.deepcopy(job)
    published_job["historical"] = True
    def asset_url(key):
        return data_base + ({"pdf": "report.pdf", "internal": "internal.json", "external": "external.json", "trace": "trace.json"}.get(key, key + ".png"))
    review = published_job["review"]
    for key, value in (("pdf_url", "pdf"), ("internal_url", "internal"), ("external_url", "external"), ("trace_url", "trace")):
        review[key] = asset_url(value)
    for item in review["evidence"]:
        item.update(pdf_url=asset_url("pdf") + "#page=" + str(item["page"]), image_url=asset_url("image-" + str(item["page"])))
    allowed_entry = ("id", "company", "short_name", "thscode", "period", "filename", "pages", "pdf_sha256")
    public_catalog = {"id": catalog["id"], "folder_path": "课堂报告集合 · 6 份原始 PDF", "entries": [{key: item[key] for key in allowed_entry} for item in catalog["entries"]], "excluded": []}
    from product import PRESETS
    budget = store.state("")["budget"]
    state = {"catalog": public_catalog, "default_report_id": job["report_id"], "presets": PRESETS, "jobs": [published_job], "budget": budget, "active_job_id": None}
    save(demo / "data/state.json", state)
    save(demo / "data/run.json", published_job)
    save(demo / "data/trace.json", {**published_job, "publication_note": "已核验运行的公开调用与反馈汇总。原始模型请求和回复保留在本地，不在此包中。"})
    for key in ("pdf", "internal", "external", *["image-" + str(item["page"]) for item in review["evidence"]]):
        source = store.artifact(job["id"], key)
        if key == "pdf":
            assert digest(source) == job["pdf_sha256"]
        transfer(source, demo / "data" / asset_url(key).split("/")[-1])

    html = (product / "web/index.html").read_text()
    html = html.replace('href="/style.css"', 'href="style.css"').replace('src="/app.js"', 'src="app.js"')
    html = html.replace('href="/" aria-label="Earnings Review 首页"', 'href="../../" aria-label="讲座主页"')
    html = html.replace('>当前文件夹<', '>课堂文件集合<')
    html = html.replace('>本地工作区<', '>第二讲 · 成品示例<').replace('只在点击运行后调用模型', '浏览示例不调用模型')
    html = html.replace('<span class="edition">2026 · 半年报</span>', '<a class="text-link" href="../">实操讲义 ↗</a>')
    html = html.replace('<div id="global-notice"', '<div class="publication-note"><strong>课前已核验示例 · 2026 年 10 月 16 日</strong><p>这里公开顺丰的真实运行结果、每步用量和证据。完整产品在本地扫描 PDF、调用模型与同花顺；按第二讲讲义搭建后，在自己的电脑上运行。</p><div><a href="../../">← 讲座主页</a><a href="../">跟着 Prompt 一步步搭建 ↗</a><a href="../earnings-review-materials.zip" download>下载六份报告与实操材料 ↓</a></div></div><div id="global-notice"', 1)
    html = html.replace('>运行模型<', '>本地运行预设<').replace('>新运行的预算与停止条件<', '>本地运行的预算与停止条件<')
    html = html.replace('<h3>从这一份报告开始</h3><p>点击“运行复盘”，查看证据定位、模型抄录和两层核验的真实过程。</p>', '<h3>这份报告尚无公开运行示例</h3><p>材料包包含这份原始 PDF。请按讲义搭建后在本地运行；此处不会套用其他公司的结果。</p><a class="text-link" href="../#step-0">开始搭建 ↗</a>')
    html = html.replace('下载完整记录 ↓', '下载调用与反馈汇总 ↓')
    html = re.sub(r'  <dialog id="folder-dialog".*?</dialog>\n', '', html)
    write(demo / "index.html", html)
    css = (product / "web/style.css").read_text() + '\n.publication-note{margin:0 0 25px;padding:20px 22px;background:var(--blue-soft,#dce8f2);border-radius:14px;line-height:1.65}.publication-note strong{font-size:14px}.publication-note p{font-size:14px;margin:8px 0 12px}.publication-note div{display:flex;flex-wrap:wrap;gap:10px 22px;font-size:13px}.publication-note a{color:inherit}.folder-button:disabled{opacity:1;cursor:default}\n'
    write(demo / "style.css", css)
    js = (product / "web/app.js").read_text()
    js = function(js, "api", '''async function api(path) {
  const name = path === '/api/state' ? 'state' : /^\\/api\\/jobs\\/[a-z0-9_-]+$/.test(path) ? 'run' : null;
  if (!name) throw new Error('此页面只提供已核验示例；请在本地启动完整产品。');
  const response = await fetch(`data/${name}.json`);
  if (!response.ok) throw new Error('暂时无法读取公开示例。');
  return response.json();
}''')
    js = re.sub(r'^function artifact\([^\n]+$', 'function artifact(jobId, key) { return new URL(`data/${({pdf:"report.pdf",internal:"internal.json",external:"external.json",trace:"trace.json"})[key] || key + ".png"}`, window.location.href).pathname; }', js, flags=re.M)
    for name in ("rememberIntent", "matchingIntent", "startRun", "openActiveJob", "pollCurrent"):
        js = function(js, name)
    js = function(js, "schedulePoll", "function schedulePoll() {}")
    js = function(js, "updateControls", '''function updateControls() {
  $('run-button').disabled = false;
  $('run-label').textContent = '按讲义在本地运行 ↗';
  $('run-caption').textContent = '公开页浏览历史示例，不发起模型请求';
  $('preset-select').disabled = false;
  $('folder-open').disabled = true;
  const preset = store.presets.find((p) => p.id === store.presetId);
  $('preset-description').textContent = preset ? `本地方案：文本 ${modelName(preset.text_model)} · 视觉 ${modelName(preset.vision_model)}。下方示例保留原运行模型。` : '';
}''')
    js = js.replace("<span>本地 PDF</span>", "<span>原始 PDF</span>")
    js = js.replace("'历史运行记录' : '本次运行'", "'课前示例运行记录' : '本次运行'")
    js = js.replace("这是此前真实运行的留存结果。查看记录不会触发新调用；点击“运行复盘”会创建一次新的运行。", "这是课前真实运行的留存结果，所有续跑计入下方合计。按讲义在本地运行后，可以生成自己的记录。")
    js = js.replace('本次流程耗时', '示例流程耗时').replace('含续跑与重试', '原运行含续跑与重试')
    js = js.replace("`/api/jobs/${encodeURIComponent(job.id)}/trace`", "artifact(job.id,'trace')")
    js = js[:js.index("$('run-button').addEventListener('click',startRun);")] + '''$('run-button').addEventListener('click',() => { window.location.href = '../#step-0'; });
for (const dialog of document.querySelectorAll('dialog')) dialog.addEventListener('click',(event) => { if (event.target === dialog) dialog.close(); });
refreshState(true).catch((error) => showNotice('global-notice',`暂时无法读取公开示例。${error.message}`,'error'));
'''
    write(demo / "app.js", js)
    save(target / "publication.json", {"schema": 1, "lesson": 2, "date": "2026-10-16", "source_snapshot_digest": source_digest, "handout_updated": json.loads((lesson/"source/lesson.json").read_text())["updated"], "mode": "static_verified_example_and_prompt_handout", "source_job": job["id"], "pdf_sha256": job["pdf_sha256"], "seal_sha256": certificate["seal_sha256"], "source_frontend_sha256": source_sha, "files": {str(p.relative_to(target)): digest(p) for p in sorted(target.rglob('*')) if p.is_file() and p.name != 'publication.json'}})
    print(json.dumps({"output": str(target), "sample": job["short_name"], "tokens": job["usage"]["total_tokens"], "files": len(list(target.rglob('*')))}, ensure_ascii=False))


if __name__ == "__main__":
    main()
