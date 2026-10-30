import argparse
import json
from pathlib import Path

from disclosure_agent import schedule
from disclosure_agent.runner import run


def main():
    parser = argparse.ArgumentParser(description="巨潮业绩说明会监控Agent")
    parser.add_argument("command", choices=["run", "tick", "schedule"])
    parser.add_argument("action", nargs="?", choices=["install", "status", "test", "pause", "resume"])
    parser.add_argument("--config", type=Path, default=Path(__file__).parent / "config.json")
    parser.add_argument("--workspace", type=Path, default=Path(__file__).parent / "runtime/live")
    parser.add_argument("--fixture", type=Path)
    parser.add_argument("--trigger", default="manual", choices=["manual", "scheduler"])
    parser.add_argument("--claim-id")
    parser.add_argument("--after-seconds", type=int, default=90)
    args = parser.parse_args()
    try:
        root = Path(__file__).resolve().parent
        if args.command == "run":
            result = run(args.config, args.workspace, args.trigger, args.fixture, claim_id=args.claim_id)
        elif args.command == "tick":
            result = schedule.tick(args.config, args.workspace, root)
        elif args.action == "install":
            result = schedule.install(args.config, args.workspace, root)
        elif args.action == "test":
            result = schedule.test_after(args.workspace, args.after_seconds)
        elif args.action in {"status", "pause", "resume"}:
            result = getattr(schedule, args.action)(args.workspace)
        else:
            parser.error("schedule需要install/status/test/pause/resume操作。")
        print(json.dumps(result, ensure_ascii=False))
        return 0 if result.get("status") in {None, "complete", "not_due", "paused", "already_claimed"} else 2
    except Exception as exc:
        print(json.dumps({"status": "failed", "error": type(exc).__name__ + ": " + str(exc)}, ensure_ascii=False))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
