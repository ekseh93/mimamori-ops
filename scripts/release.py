"""Code-only release/rollback; explicit workflow or CLI invocation changes AWS."""

import argparse
import base64
import hashlib
import json
from pathlib import Path

import boto3


def smoke(client, function, version):
    response = client.invoke(FunctionName=function, Qualifier=version,
                             Payload=b'{"action":"health"}')
    body = json.loads(response["Payload"].read())
    if response.get("FunctionError") or not body.get("ok") or body.get("mode") != "configuration-only":
        raise RuntimeError("configuration smoke failed; check CloudWatch with authorized access")


def release(client, function, archive=None, rollback=None):
    before = client.get_alias(FunctionName=function, Name="live")
    previous = before["FunctionVersion"]
    if rollback:
        if not rollback.isdigit():
            raise ValueError("rollback requires a numeric published version")
        version = rollback
    else:
        payload = Path(archive).read_bytes()
        digest = base64.b64encode(hashlib.sha256(payload).digest()).decode()
        latest = client.get_function_configuration(FunctionName=function)
        client.update_function_code(FunctionName=function, ZipFile=payload, Publish=False,
                                    RevisionId=latest["RevisionId"])
        client.get_waiter("function_updated_v2").wait(FunctionName=function)
        current = client.get_function_configuration(FunctionName=function)
        published = client.publish_version(FunctionName=function, CodeSha256=digest,
                                            RevisionId=current["RevisionId"])
        version = published["Version"]
        client.get_waiter("function_active_v2").wait(FunctionName=function, Qualifier=version)
    smoke(client, function, version)
    moved = client.update_alias(FunctionName=function, Name="live", FunctionVersion=version,
                                 RevisionId=before["RevisionId"])
    try:
        smoke(client, function, "live")
        final = client.get_alias(FunctionName=function, Name="live")
        if final["FunctionVersion"] != version:
            raise RuntimeError("alias verification failed")
    except Exception:
        # Optimistic concurrency prevents overwriting another operator's newer release.
        client.update_alias(FunctionName=function, Name="live", FunctionVersion=previous,
                            RevisionId=moved["RevisionId"])
        raise
    result = {"previous_version": previous, "live_version": version,
              "smoke": "configuration-only; scheduled observation and email receipt still need verification"}
    Path("build").mkdir(exist_ok=True)
    Path("build/release.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result))
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--function", required=True)
    choice = parser.add_mutually_exclusive_group(required=True)
    choice.add_argument("--zip")
    choice.add_argument("--rollback")
    args = parser.parse_args()
    release(boto3.client("lambda", region_name="ap-northeast-1"), args.function, args.zip, args.rollback)
