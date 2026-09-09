"""AWS adapter. Schedule events reference IDs, never supply arbitrary URLs."""

import json
import os
import time
from datetime import datetime

from mimamori.core import flush_pending, process
from mimamori.probe import probe, validate_target
from mimamori.storage import DynamoStore


def configured_targets():
    targets = json.loads(os.environ.get("TARGETS_JSON", "{}"))
    if not isinstance(targets, dict) or not 1 <= len(targets) <= 5:
        raise ValueError("configure 1-5 approved targets")
    for target_id, url in targets.items():
        validate_target(target_id, url)
    return targets


def handler(event, context):
    targets = configured_targets()
    if event.get("action") == "health":
        return {"ok": True, "target_count": len(targets), "mode": "configuration-only"}
    target_id = event["target_id"]
    if target_id not in targets:
        raise ValueError("target is not configured")
    scheduled = datetime.fromisoformat(event["scheduled_time"].replace("Z", "+00:00"))
    if scheduled.tzinfo is None:
        raise ValueError("scheduled time must have a timezone")
    epoch = int(scheduled.timestamp())
    if epoch > time.time() + 60 or epoch < time.time() - 900:
        raise ValueError("schedule event is outside the 15-minute processing window")
    slot = epoch // 300 * 300
    store = DynamoStore(os.environ["TABLE_NAME"])
    import boto3
    from botocore.config import Config
    sns = boto3.client("sns", config=Config(connect_timeout=3, read_timeout=5,
                       retries={"mode": "standard", "total_max_attempts": 3}))

    def notify(alert):
        label = "障害検知" if alert["status"] == "DOWN" else "復旧検知"
        sns.publish(TopicArn=os.environ["TOPIC_ARN"], Subject=f"[Mimamori] {label}: {target_id}",
                    Message=json.dumps(alert, ensure_ascii=False))

    flush_pending(store, target_id, notify)
    if store.state(target_id)["last_slot"] >= slot:
        return {"ok": True, "duplicate": True}
    observation = probe(target_id, targets[target_id], slot)
    saved = process(store, observation, notify)
    # Never log full URLs, bodies, headers, or exception messages from targets.
    print(json.dumps({"event": "check_complete", "target_id": target_id, "slot": slot,
                      "ok": observation.ok, "reason": observation.reason,
                      "latency_ms": observation.latency_ms, "saved": saved}))
    return {"ok": True, "saved": saved, "target_ok": observation.ok}
