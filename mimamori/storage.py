"""SQLite for zero-cost practice; DynamoDB for the same state machine in AWS."""

import json
import sqlite3
from pathlib import Path

from mimamori.core import initial_state


class SQLiteStore:
    def __init__(self, path):
        if str(path) != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(path)
        self.db.execute("CREATE TABLE IF NOT EXISTS state (id TEXT PRIMARY KEY, body TEXT)")
        self.db.execute("CREATE TABLE IF NOT EXISTS samples "
                        "(id TEXT, slot INTEGER, body TEXT, PRIMARY KEY(id, slot))")

    def state(self, target_id):
        row = self.db.execute("SELECT body FROM state WHERE id=?", (target_id,)).fetchone()
        return json.loads(row[0]) if row else initial_state()

    def commit(self, previous, updated, observation):
        target_id = observation["target_id"]
        with self.db:
            self.db.execute("BEGIN IMMEDIATE")
            if self.state(target_id) != previous:
                return False
            self.db.execute("INSERT INTO samples VALUES (?, ?, ?)",
                            (target_id, observation["slot"], json.dumps(observation)))
            self.db.execute("INSERT OR REPLACE INTO state VALUES (?, ?)",
                            (target_id, json.dumps(updated)))
        return True

    def ack(self, target_id, old):
        new = dict(old, pending=None)
        with self.db:
            self.db.execute("UPDATE state SET body=? WHERE id=? AND body=?",
                            (json.dumps(new), target_id, json.dumps(old)))

    def samples(self, target_id, start, end):
        rows = self.db.execute("SELECT body FROM samples WHERE id=? AND slot>=? AND slot<? "
                               "ORDER BY slot", (target_id, start, end))
        return [json.loads(row[0]) for row in rows]

    def close(self):
        self.db.close()


class DynamoStore:
    def __init__(self, table_name, client=None):
        if client is None:
            import boto3
            from botocore.config import Config
            client = boto3.client("dynamodb", config=Config(
                connect_timeout=3, read_timeout=5,
                retries={"mode": "standard", "total_max_attempts": 3}))
        self.client, self.table = client, table_name

    @staticmethod
    def key(target_id, sort):
        return {"pk": {"S": target_id}, "sk": {"S": sort}}

    def state(self, target_id):
        item = self.client.get_item(TableName=self.table, Key=self.key(target_id, "STATE"),
                                    ConsistentRead=True).get("Item")
        return json.loads(item["body"]["S"]) if item else initial_state()

    def commit(self, previous, updated, observation):
        target_id, slot = observation["target_id"], observation["slot"]
        state_item = {**self.key(target_id, "STATE"), "body": {"S": json.dumps(updated)}}
        state_put = {"TableName": self.table, "Item": state_item,
                     "ConditionExpression": "attribute_not_exists(pk)"}
        if previous["last_slot"] != -1:
            state_put.update(ConditionExpression="body = :old",
                             ExpressionAttributeValues={":old": {"S": json.dumps(previous)}})
        sample_item = {**self.key(target_id, f"O#{slot:012d}"),
                       "body": {"S": json.dumps(observation)},
                       "expires_at": {"N": str(slot + 40 * 86400)}}
        try:
            self.client.transact_write_items(TransactItems=[{"Put": state_put}, {"Put": {
                "TableName": self.table, "Item": sample_item,
                "ConditionExpression": "attribute_not_exists(pk)"}}])
        except self.client.exceptions.TransactionCanceledException as exc:
            reasons = exc.response.get("CancellationReasons", [])
            codes = {r.get("Code") for r in reasons} - {None, "None"}
            if codes == {"ConditionalCheckFailed"}:
                return False
            raise
        return True

    def ack(self, target_id, old):
        try:
            self.client.update_item(TableName=self.table, Key=self.key(target_id, "STATE"),
                UpdateExpression="SET body = :new", ConditionExpression="body = :old",
                ExpressionAttributeValues={":new": {"S": json.dumps(dict(old, pending=None))},
                                           ":old": {"S": json.dumps(old)}})
        except self.client.exceptions.ConditionalCheckFailedException:
            pass

    def samples(self, target_id, start, end):
        if end <= start:
            return []
        args = {"TableName": self.table, "ConsistentRead": True,
                "KeyConditionExpression": "pk = :id AND sk BETWEEN :start AND :end",
                "ExpressionAttributeValues": {":id": {"S": target_id},
                    ":start": {"S": f"O#{start:012d}"}, ":end": {"S": f"O#{end - 1:012d}"}}}
        rows = []
        while True:
            page = self.client.query(**args)
            rows.extend(json.loads(item["body"]["S"]) for item in page["Items"])
            if not page.get("LastEvaluatedKey"):
                break
            args["ExclusiveStartKey"] = page["LastEvaluatedKey"]
        return rows
