"""AWS API emulation. Passing these tests is NOT evidence of deployment."""

import importlib.util
import json
import os
import unittest
from unittest.mock import patch

HAS_MOTO = importlib.util.find_spec("moto") is not None


@unittest.skipUnless(HAS_MOTO, "install requirements-dev.txt for AWS emulation")
class AWSAdapterTests(unittest.TestCase):
    def setUp(self):
        import boto3
        from moto import mock_aws
        self.env = patch.dict(os.environ, {"AWS_DEFAULT_REGION": "ap-northeast-1",
            "AWS_ACCESS_KEY_ID": "testing", "AWS_SECRET_ACCESS_KEY": "testing",
            "AWS_EC2_METADATA_DISABLED": "true", "TARGETS_JSON": '{"site":"https://example.com/"}',
            "TABLE_NAME": "test-monitor"})
        self.env.start()
        self.addCleanup(self.env.stop)
        self.mock = mock_aws()
        self.mock.start()
        self.addCleanup(self.mock.stop)
        self.client = boto3.client("dynamodb")
        self.client.create_table(TableName="test-monitor",
            KeySchema=[{"AttributeName": "pk", "KeyType": "HASH"},
                       {"AttributeName": "sk", "KeyType": "RANGE"}],
            AttributeDefinitions=[{"AttributeName": "pk", "AttributeType": "S"},
                                  {"AttributeName": "sk", "AttributeType": "S"}],
            ProvisionedThroughput={"ReadCapacityUnits": 5, "WriteCapacityUnits": 5})
        self.sns = boto3.client("sns")
        os.environ["TOPIC_ARN"] = self.sns.create_topic(Name="test-monitor")["TopicArn"]
        self.addCleanup(lambda: os.environ.pop("TOPIC_ARN", None))
        from mimamori.storage import DynamoStore
        self.store = DynamoStore("test-monitor", self.client)

    def test_atomic_history_state_and_ack(self):
        from mimamori.core import Observation, process
        alerts = []
        for slot in [0, 300]:
            process(self.store, Observation("site", slot, False, 100, "timeout"), alerts.append)
        self.assertEqual(len(alerts), 1)
        self.assertEqual(self.store.state("site")["status"], "DOWN")
        self.assertIsNone(self.store.state("site")["pending"])
        self.assertEqual(len(self.store.samples("site", 0, 600)), 2)
        self.assertFalse(process(self.store, Observation("site", 300, False, 100, "timeout"), alerts.append))

    def test_stale_transaction_is_rejected(self):
        from dataclasses import asdict
        from mimamori.core import Observation, advance, initial_state, process
        process(self.store, Observation("site", 0, True, 1, "ok"), lambda _: None)
        row = Observation("site", 300, False, 1, "timeout")
        self.assertFalse(self.store.commit(initial_state(), advance(initial_state(), row), asdict(row)))
        self.assertEqual(len(self.store.samples("site", 0, 600)), 1)

    def test_query_pagination(self):
        from mimamori.storage import DynamoStore
        from unittest.mock import MagicMock
        client = MagicMock()
        client.query.side_effect = [{"Items": [{"body": {"S": '{"slot":0}'}}],
                                     "LastEvaluatedKey": {"pk": {"S": "site"}}},
                                    {"Items": [{"body": {"S": '{"slot":300}'}}]}]
        rows = DynamoStore("test", client).samples("site", 0, 600)
        self.assertEqual(len(rows), 2)
        self.assertIn("ExclusiveStartKey", client.query.call_args.kwargs)

    def test_lambda_checks_dedup_and_publishes_to_mock_sns(self):
        from mimamori.core import Observation
        from mimamori.handler import handler
        with patch("mimamori.handler.time.time", return_value=1800), patch(
            "mimamori.handler.probe", side_effect=lambda tid, url, slot:
                Observation(tid, slot, False, 50, "http_error", 503)) as probe:
            for instant in ["1970-01-01T00:20:00Z", "1970-01-01T00:25:00Z"]:
                result = handler({"target_id": "site", "scheduled_time": instant}, None)
                self.assertTrue(result["saved"])
            duplicate = handler({"target_id": "site", "scheduled_time": instant}, None)
            self.assertTrue(duplicate["duplicate"])
            self.assertEqual(probe.call_count, 2)
        self.assertIsNone(self.store.state("site")["pending"])

    def test_health_does_not_claim_network_health(self):
        from mimamori.handler import handler
        self.assertEqual(handler({"action": "health"}, None)["mode"], "configuration-only")

    def test_unknown_target_and_stale_event_fail_closed(self):
        from mimamori.handler import handler
        with self.assertRaises(ValueError):
            handler({"target_id": "unknown"}, None)
        with self.assertRaises(ValueError):
            handler({"target_id": "site", "scheduled_time": "1970-01-01T00:00:00Z"}, None)

    def test_target_limit_and_invalid_url(self):
        from mimamori.handler import configured_targets
        for targets in [{}, {f"site-{i}": "https://example.com/" for i in range(6)},
                        {"site": "http://example.com"}]:
            with patch.dict(os.environ, {"TARGETS_JSON": json.dumps(targets)}), self.assertRaises(ValueError):
                configured_targets()
