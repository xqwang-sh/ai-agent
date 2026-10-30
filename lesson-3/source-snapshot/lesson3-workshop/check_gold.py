"""Grade saved raw extraction only. This program never calls a model."""
import argparse
import hashlib
import json
from pathlib import Path
import re
from urllib.parse import urlsplit, urlunsplit

from evidence import validate_evidence

ROOT = Path(__file__).resolve().parent


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def rows(path):
    result = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        if not isinstance(row, dict) or not isinstance(row.get("id"), str) or row["id"] in result:
            raise ValueError("Each row needs one unique string id")
        result[row["id"]] = row
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--actual", type=Path, required=True, help="Original output JSONL, one {id,result} per notice")
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--suite", default="all", help="Current-quarter suite: small, templates, changes, expanded or all")
    args = parser.parse_args()
    if args.report.resolve() == args.actual.resolve() or args.report.resolve().is_relative_to(ROOT):
        raise ValueError("Save the report outside this package and do not overwrite original output")
    manifest = json.loads((ROOT / "manifest.json").read_text())
    for relative, expected in manifest["files"].items():
        path = (ROOT / relative).resolve()
        if not path.is_relative_to(ROOT) or digest(path) != expected:
            raise ValueError("Validation package changed: " + relative)
    gold, inputs, actual = rows(ROOT / "teacher-gold.jsonl"), rows(ROOT / "input.jsonl"), rows(args.actual)
    full_gold=gold
    suites=manifest.get('suites',{'all':list(gold)})
    if args.suite not in suites:raise ValueError('Unknown suite: '+args.suite)
    gold={identity:full_gold[identity] for identity in suites[args.suite]}
    details = []
    for identity, expected in gold.items():
        value = actual.get(identity, {}).get("result")
        fields = [key for key, target in expected["expected"].items() if not isinstance(value, dict) or key not in value or value[key] not in expected.get('allowed_field_values',{}).get(key,[target])]
        source = inputs[identity]
        pages = re.split(r"\[PAGE \d+\]\n", source["text"])[1:]
        evidence = validate_evidence(value, pages, source) if isinstance(value, dict) else ["missing_original_result"]
        def normalize_url(url):
            if url is None:return None
            parts=urlsplit(url)
            return urlunsplit((parts.scheme,parts.netloc,parts.path or '/',parts.query,parts.fragment))
        participation=[]
        if 'allowed_participation_urls' in expected and isinstance(value,dict):
            if normalize_url(value.get('participation_url')) not in [normalize_url(url) for url in expected['allowed_participation_urls']]:
                participation=['participation_url_not_current_entry']
        details.append({"id": identity, "pass": not fields and not evidence and not participation, "participation_errors":participation, "field_errors": fields, "evidence_errors": evidence})
    unknown = sorted(set(actual) - set(full_gold))
    passed = sum(row["pass"] for row in details)
    report = {"status": "pass" if passed == len(gold) and not unknown else "fail", "records": len(gold), "passed": passed, "unexpected_ids": unknown, "gold_status": manifest["gold_status"], "actual_sha256": digest(args.actual), "gold_sha256": digest(ROOT / "teacher-gold.jsonl"), "validator_sha256": digest(ROOT / "evidence.py"), "results": details, "note": "Grade original outputs. Human corrections must be saved separately. Program checks do not replace reading the source PDF."}
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: report[key] for key in ["status", "records", "passed", "unexpected_ids"]}, ensure_ascii=False))
    return 0 if report["status"] == "pass" else 2


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError, KeyError, TypeError) as error:
        raise SystemExit("Validation failed: " + str(error))
