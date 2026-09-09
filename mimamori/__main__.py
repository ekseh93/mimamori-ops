import argparse
import json
import time
from datetime import datetime
from pathlib import Path

from mimamori.core import Observation, process
from mimamori.probe import probe, validate_target
from mimamori.report import render_report
from mimamori.storage import DynamoStore, SQLiteStore


def timestamp(value):
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("use a timezone, e.g. 2026-09-01T00:00:00Z")
    return int(parsed.timestamp())


def write(path, content):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(content, encoding="utf-8")
    print(f"Written: {path}")


def main():
    parser = argparse.ArgumentParser(description="Mimamori Ops: monitoring and Japanese reports")
    sub = parser.add_subparsers(dest="command", required=True)
    demo = sub.add_parser("demo")
    demo.add_argument("--output", default="artifacts/local/demo.md")
    check = sub.add_parser("check")
    check.add_argument("--id", required=True)
    check.add_argument("--url", required=True)
    check.add_argument("--db", default="data/local.db")
    report = sub.add_parser("report")
    report.add_argument("--id", required=True)
    source = report.add_mutually_exclusive_group()
    source.add_argument("--db", default="data/local.db")
    source.add_argument("--table", help="AWS DynamoDB table; uses the configured AWS SDK profile")
    report.add_argument("--start", required=True)
    report.add_argument("--end", required=True)
    report.add_argument("--output", default="artifacts/local/report.md")
    estimate = sub.add_parser("estimate")
    estimate.add_argument("--targets", type=int, default=5)
    estimate.add_argument("--interval", type=int, choices=[5], default=5)
    args = parser.parse_args()
    if args.command == "demo":
        store, alerts = SQLiteStore(":memory:"), []
        start = timestamp("2026-09-01T00:00:00Z")
        for index, ok in [(0, True), (1, False), (2, False), (3, True), (4, True),
                          (6, True), (7, True), (8, True), (9, True)]:
            observation = Observation("demo-site", start + index * 300, ok,
                                      120 if ok else 5000, "ok" if ok else "timeout",
                                      200 if ok else None, 60 if ok else None)
            process(store, observation, alerts.append)
        content = render_report("demo-site", store.samples("demo-site", start, start + 3000),
                                start, start + 3000, simulated=True)
        content += "\n## 模擬通知（外部送信なし）\n\n```json\n" + json.dumps(alerts, indent=2) + "\n```\n"
        write(args.output, content)
        store.close()
    elif args.command == "check":
        store = SQLiteStore(args.db)
        observation = probe(args.id, args.url, int(time.time()) // 300 * 300)
        saved = process(store, observation, lambda a: print(json.dumps(a)))
        print(json.dumps({"saved": saved, "reason": observation.reason, "ok": observation.ok}))
        store.close()
    elif args.command == "report":
        validate_target(args.id, "https://example.com/")
        start, end = timestamp(args.start), timestamp(args.end)
        # Validate before issuing a potentially large DynamoDB query.
        if end - start > 40 * 86400:
            raise ValueError("report period is limited to 40 days")
        render_report(args.id, [], start, end)
        store = DynamoStore(args.table) if args.table else SQLiteStore(args.db)
        write(args.output, render_report(args.id, store.samples(args.id, start, end), start, end))
        if isinstance(store, SQLiteStore):
            store.close()
    else:
        if not 1 <= args.targets <= 5:
            parser.error("the MVP supports 1-5 targets")
        requests = args.targets * 30 * 24 * 60 // args.interval
        print(json.dumps({"days": 30, "checks": requests, "lambda_requests": requests,
              "lambda_gb_seconds_assuming_256mb_2s": requests * .25 * 2,
              "lambda_gb_seconds_at_60s_timeout": requests * .25 * 60,
              "note": "Usage estimate only; retries, shared allowance and other service costs excluded"}, indent=2))


if __name__ == "__main__":
    main()
