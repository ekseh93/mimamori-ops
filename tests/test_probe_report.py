import socket
import ssl
import unittest
from unittest.mock import MagicMock, patch

from mimamori.probe import PinnedHTTPSConnection, probe, public_addresses, validate_target
from mimamori.report import render_report


class ProbeTests(unittest.TestCase):
    def test_rejects_unsafe_url_forms(self):
        for url in ["http://example.com", "https://x:444", "https://u:p@x/", "https://x/?key=secret",
                    "https://x/#fragment", "https://x/\r\nHeader:y", "https://x/\\y"]:
            with self.subTest(url=url), self.assertRaises(ValueError):
                validate_target("site", url)

    def test_rejects_unsafe_ids(self):
        for name in ["../x", "", "site\n", "UPPER", "x" * 41]:
            with self.subTest(name=name), self.assertRaises(ValueError):
                validate_target(name, "https://example.com/")

    def test_blocks_private_metadata_and_mixed_dns(self):
        for ip in ["127.0.0.1", "10.0.0.1", "169.254.169.254", "::1", "::ffff:127.0.0.1",
                   "100.64.0.1", "224.0.0.1"]:
            with self.subTest(ip=ip), patch("socket.getaddrinfo", return_value=[
                (2, 1, 6, "", ("8.8.8.8", 443)), (2, 1, 6, "", (ip, 443))
            ]), self.assertRaises(ValueError):
                public_addresses("example.com")

    def test_ipv4_preferred_when_public_ipv6_also_exists(self):
        with patch("socket.getaddrinfo", return_value=[
            (10, 1, 6, "", ("2606:4700:4700::1111", 443, 0, 0)),
            (2, 1, 6, "", ("93.184.216.34", 443))
        ]):
            self.assertEqual(public_addresses("example.com")[0], "93.184.216.34")

    @patch("mimamori.probe.socket.create_connection")
    def test_connection_uses_vetted_ip_and_original_sni(self, connect):
        conn = PinnedHTTPSConnection("example.com", "93.184.216.34")
        context = MagicMock()
        conn._context = context
        conn.connect()
        connect.assert_called_once_with(("93.184.216.34", 443), 5)
        context.wrap_socket.assert_called_once_with(connect.return_value, server_hostname="example.com")

    @patch("mimamori.probe.public_addresses", return_value=["93.184.216.34"])
    @patch("mimamori.probe.PinnedHTTPSConnection")
    def test_status_and_redirect_are_not_followed(self, factory, addresses):
        conn = factory.return_value
        conn.sock.getpeercert.return_value = {"notAfter": "Sep  9 12:00:00 2030 GMT"}
        for status, ok, reason in [(200, True, "ok"), (503, False, "http_error"),
                                   (302, False, "redirect_not_followed")]:
            conn.getresponse.return_value.status = status
            row = probe("site", "https://example.com/health", 300)
            self.assertEqual((row.ok, row.reason, row.status), (ok, reason, status))
        self.assertEqual(factory.call_count, 3)
        conn.getresponse.return_value.read.assert_not_called()

    def test_network_errors_classified_without_raw_error_text(self):
        for error, reason in [(socket.gaierror("secret"), "dns_error"),
                              (ssl.SSLError("secret"), "tls_error"),
                              (TimeoutError("secret"), "timeout"),
                              (OSError("secret"), "connection_error"),
                              (ValueError("secret"), "blocked_destination")]:
            with patch("mimamori.probe.public_addresses", side_effect=error):
                result = probe("site", "https://example.com/", 300)
                self.assertEqual(result.reason, reason)
                self.assertFalse(result.ok)


class ReportTests(unittest.TestCase):
    def test_no_data_is_not_perfect_uptime(self):
        report = render_report("site", [], 0, 600)
        self.assertIn("算出不可（観測なし）", report)
        self.assertIn("| 未観測枠 | 2 |", report)
        self.assertNotIn("100.00%", report)

    def test_missing_slots_separate_from_success_rate(self):
        row = {"target_id": "site", "slot": 0, "ok": True, "latency_ms": 12,
               "reason": "ok", "status": 200, "tls_days": 30}
        report = render_report("site", [row, row], 0, 600, simulated=True)
        self.assertIn("| 観測カバー率 | 50.00% |", report)
        self.assertIn("| 観測成功率 | 100.00% |", report)
        self.assertIn("模擬訓練データ", report)

    def test_invalid_window(self):
        for start, end in [(0, 0), (600, 0), (1, 600)]:
            with self.assertRaises(ValueError):
                render_report("site", [], start, end)

    def test_delayed_observation_has_its_own_timestamp(self):
        row = {"target_id": "site", "slot": 0, "observed_at": 120, "ok": True,
               "latency_ms": 12, "reason": "ok", "status": 200, "tls_days": 30}
        report = render_report("site", [row], 0, 300)
        self.assertIn("1970-01-01T00:00:00Z | 1970-01-01T00:02:00Z", report)
