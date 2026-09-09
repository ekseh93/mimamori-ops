import importlib.util
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch


@unittest.skipUnless(importlib.util.find_spec("boto3"), "install requirements-dev.txt for release tests")
class ReleaseTests(unittest.TestCase):
    def setUp(self):
        self.client = MagicMock()
        self.client.get_alias.side_effect = [
            {"FunctionVersion": "1", "RevisionId": "before"}, {"FunctionVersion": "2"}]
        self.client.get_function_configuration.return_value = {"RevisionId": "latest"}
        self.client.publish_version.return_value = {"Version": "2"}
        self.client.update_alias.return_value = {"RevisionId": "after"}
        self.client.invoke.side_effect = [self.good(), self.good()]

    @staticmethod
    def good():
        return {"Payload": io.BytesIO(json.dumps({"ok": True, "mode": "configuration-only"}).encode())}

    def test_candidate_failure_leaves_live_alias_unchanged(self):
        from scripts.release import release
        self.client.invoke.side_effect = [{"FunctionError": "Unhandled",
                                          "Payload": io.BytesIO(b'{"ok":false}')}]
        with self.assertRaises(RuntimeError):
            release(self.client, "test", rollback="2")
        self.client.update_alias.assert_not_called()

    def test_post_promotion_failure_restores_previous_alias(self):
        from scripts.release import release
        self.client.invoke.side_effect = [self.good(), OSError("failure")]
        with self.assertRaises(OSError):
            release(self.client, "test", rollback="2")
        self.assertEqual(self.client.update_alias.call_args.kwargs["FunctionVersion"], "1")
        self.assertEqual(self.client.update_alias.call_args.kwargs["RevisionId"], "after")

    def test_successful_release_pins_zip_hash(self):
        from scripts.release import release
        with tempfile.TemporaryDirectory() as tmp, patch("scripts.release.Path.write_text"):
            archive = Path(tmp) / "lambda.zip"
            archive.write_bytes(b"test-artifact")
            result = release(self.client, "test", archive=archive)
        self.assertEqual(result["live_version"], "2")
        self.assertIn("CodeSha256", self.client.publish_version.call_args.kwargs)
        self.assertEqual(self.client.update_function_code.call_args.kwargs["RevisionId"], "latest")

    def test_rejects_unpublished_rollback(self):
        from scripts.release import release
        with self.assertRaises(ValueError):
            release(self.client, "test", rollback="$LATEST")
