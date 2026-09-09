import unittest

from mimamori.core import Observation, advance, initial_state, process
from mimamori.storage import SQLiteStore


class IncidentTests(unittest.TestCase):
    def setUp(self):
        self.store = SQLiteStore(":memory:")
        self.addCleanup(self.store.close)
        self.alerts = []

    def sample(self, slot, ok, notifier=None):
        return process(self.store, Observation("site", slot, ok, 20, "ok" if ok else "timeout"),
                       notifier if notifier is not None else self.alerts.append)

    def test_incident_recovery_and_no_alert_storm(self):
        for slot, ok in [(0, True), (300, False), (600, False), (900, False),
                         (1200, True), (1500, True), (1800, True)]:
            self.sample(slot, ok)
        self.assertEqual([a["status"] for a in self.alerts], ["DOWN", "UP"])
        self.assertEqual(self.store.state("site")["status"], "UP")

    def test_initial_outage_is_detected(self):
        self.sample(0, False)
        self.sample(300, False)
        self.assertEqual(len(self.alerts), 1)

    def test_duplicate_and_out_of_order_dont_change_history(self):
        self.sample(300, True)
        self.assertFalse(self.sample(300, False))
        self.assertFalse(self.sample(0, False))
        self.assertEqual(len(self.store.samples("site", 0, 600)), 1)

    def test_missing_sample_breaks_streak(self):
        self.sample(0, False)
        self.sample(600, False)
        self.assertEqual(self.alerts, [])
        self.sample(900, False)
        self.assertEqual(len(self.alerts), 1)

    def test_notification_failure_survives_retry(self):
        self.sample(0, False)
        def fail(_):
            raise OSError("simulated notification outage")
        with self.assertRaises(OSError):
            self.sample(300, False, fail)
        self.assertIsNotNone(self.store.state("site")["pending"])
        self.assertFalse(self.sample(300, False))
        self.assertEqual(len(self.alerts), 1)
        self.assertIsNone(self.store.state("site")["pending"])
        self.assertEqual(len(self.store.samples("site", 0, 600)), 2)

    def test_publish_then_crash_may_redeliver_same_id(self):
        self.sample(0, False)
        def delivered_then_crashed(alert):
            self.alerts.append(alert)
            raise OSError("crash after publish")
        with self.assertRaises(OSError):
            self.sample(300, False, delivered_then_crashed)
        self.sample(300, False)
        self.assertEqual(self.alerts[0]["id"], self.alerts[1]["id"])

    def test_compare_and_swap_rejects_stale_writer(self):
        old = initial_state()
        self.sample(0, True)
        row = Observation("site", 300, False, 20, "timeout")
        from dataclasses import asdict
        self.assertFalse(self.store.commit(old, advance(old, row), asdict(row)))

    def test_targets_are_isolated(self):
        self.sample(0, False)
        process(self.store, Observation("other", 300, False, 1, "timeout"), self.alerts.append)
        self.assertEqual(self.alerts, [])
