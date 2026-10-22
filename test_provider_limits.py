"""Provider quotas use reported windows, never token/dollar estimates."""
import json
import os
import signal
import sys
import tempfile
import time
from pathlib import Path
import subprocess
import unittest
from unittest import mock
import provider_limits as app


class ProviderQuotaTests(unittest.TestCase):
    def test_codex_primary_can_be_weekly_and_absent_five_hour_stays_absent(self):
        rows, plan = app.parse_codex({"rateLimits": {"planType": "pro",
            "primary": {"usedPercent": 100, "windowDurationMins": 10080, "resetsAt": 1793086879},
            "secondary": None}})
        self.assertEqual(plan, "pro")
        self.assertEqual([(r["title"], r["used_percent"]) for r in rows], [("Weekly", 100)])
        self.assertIsNotNone(rows[0]["resets_at"])

    def test_codex_bucket_map_does_not_duplicate_legacy_window(self):
        bucket = {"primary": {"usedPercent": 15, "windowDurationMins": 300, "resetsAt": 1793086879},
                  "secondary": {"usedPercent": 25, "windowDurationMins": 10080, "resetsAt": 1793086879}}
        rows, _ = app.parse_codex({"rateLimits": bucket, "rateLimitsByLimitId": {"codex": bucket}})
        self.assertEqual(len(rows), 2)
        self.assertEqual([x["title"] for x in rows], ["5 hours", "Weekly"])

    def test_claude_scoped_fable_schema_and_legacy_windows_are_deduplicated(self):
        payload = {"five_hour": {"utilization": 41, "resets_at": "2026-10-22T11:30:00Z"},
                   "seven_day": {"utilization": 100, "resets_at": "2026-10-22T17:00:00Z"},
                   "limits": [
                       {"kind": "session", "percent": 41, "resets_at": "2026-10-22T11:30:00Z"},
                       {"kind": "weekly_all", "percent": 100, "resets_at": "2026-10-22T17:00:00Z"},
                       {"kind": "weekly_scoped", "percent": 4, "resets_at": "2026-10-22T17:00:00Z",
                        "scope": {"model": {"display_name": "Fable"}}}]}
        rows = app.parse_claude(payload)
        self.assertEqual([x["title"] for x in rows], ["5 hours", "Weekly", "Weekly · Fable"])
        self.assertEqual(rows[-1]["used_percent"], 4)

    def test_malformed_sibling_does_not_hide_valid_claude_window(self):
        rows = app.parse_claude({"five_hour": {"utilization": False},
                                "seven_day": {"utilization": 0, "resets_at": "bad"},
                                "limits": [None, {"kind": "weekly_scoped", "percent": "25"}]})
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["used_percent"], 0)
        self.assertIsNone(rows[0]["resets_at"])

    def test_grok_uses_actual_period_and_does_not_invent_zero(self):
        config = {"creditUsagePercent": 79,
                  "currentPeriod": {"start": "2026-10-16T04:50:00Z", "end": "2026-10-23T04:50:00Z"}}
        row = app.parse_grok({"config": config})[0]
        self.assertEqual((row["title"], row["duration_minutes"], row["used_percent"]), ("Weekly", 10080, 79))
        config.pop("creditUsagePercent")
        config["prepaidBalance"] = {"val": 0}
        self.assertEqual(app.parse_grok({"config": config}), [])

    def test_grok_monthly_window_remains_monthly_near_reset(self):
        rows = app.parse_grok({"config": {"creditUsagePercent": 99, "currentPeriod": {
            "start": "2026-09-23T00:00:00Z", "end": "2026-10-23T00:00:00Z"}}})
        self.assertEqual(rows[0]["title"], "Monthly")

    def test_percentages_must_be_finite_numeric_measurements(self):
        for value in [None, True, "42", float("nan"), float("inf"), -1]:
            self.assertIsNone(app.window("x", "Weekly", value, None, 10080))
        self.assertIsNotNone(app.window("x", "Weekly", 0, None, 10080))

    def test_unknown_provider_error_never_leaks_credentials(self):
        with mock.patch.object(app, "rpc", side_effect=RuntimeError("SECRET AUTHORIZATION TOKEN")):
            row = app.fetch("codex")
        self.assertEqual(row["status"], "unavailable")
        self.assertNotIn("SECRET", json.dumps(row))
        self.assertEqual(row["windows"], [])

    def test_rate_limit_cooldown_is_preserved_in_safe_response(self):
        with mock.patch.object(app, "claude_worker",
                               side_effect=app.Unavailable("Cooldown", "rate_limited", 300)):
            row = app.fetch("claude")
        self.assertEqual((row["status"], row["retry_after_seconds"]), ("rate_limited", 300))

    def test_zero_retry_after_uses_safe_cooldown(self):
        error = app.urllib.error.HTTPError("https://api.anthropic.com/api/oauth/usage",
                                          429, "rate limit", {"Retry-After": "0"}, None)
        with mock.patch.object(app.Path, "is_file", return_value=False), \
             mock.patch.object(app, "keychain_credentials", return_value={"claudeAiOauth": {"accessToken": "TEST"}}), \
             mock.patch.object(app.urllib.request, "build_opener") as opener:
            opener.return_value.open.side_effect = error
            with self.assertRaises(app.Unavailable) as result:
                app.claude()
        self.assertEqual((result.exception.status, result.exception.retry), ("rate_limited", 300))

    @unittest.skipUnless(os.name == "posix", "CLI process groups require POSIX")
    def test_cancellation_reaps_owned_cli_processes(self):
        with tempfile.TemporaryDirectory(prefix="AISAD quota test ") as directory:
            folder = Path(directory)
            source = "#!" + sys.executable + "\n" + (
                "import os,sys,time\nfrom pathlib import Path\n"
                "Path(os.environ['AISAD_TEST_PIDS'],Path(sys.argv[0]).name+'.pid').write_text(str(os.getpid()))\n"
                "time.sleep(20)\n")
            for name in ["codex", "grok"]:
                executable = folder/name
                executable.write_text(source)
                executable.chmod(0o700)
            environment = dict(os.environ, PATH=directory, AISAD_TEST_PIDS=directory)
            process = subprocess.Popen([sys.executable, str(Path(app.__file__).resolve()),
                "--providers", "codex", "grok"], env=environment,
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, start_new_session=True)
            try:
                deadline = time.monotonic() + 5
                while len(list(folder.glob("*.pid"))) < 2 and time.monotonic() < deadline:
                    time.sleep(.01)
                pids = [int(p.read_text()) for p in folder.glob("*.pid")]
                self.assertEqual(len(pids), 2)
                process.send_signal(signal.SIGTERM)
                process.communicate(timeout=3)
                for pid in pids:
                    with self.assertRaises(ProcessLookupError):
                        os.kill(pid, 0)
            finally:
                app.stop_child(process)
                for stream in (process.stdout, process.stderr):
                    stream.close()

    def test_missing_auth_never_runs_a_login_or_refresh(self):
        with mock.patch.object(app, "keychain_credentials", return_value=None), \
             mock.patch.object(app.Path, "is_file", return_value=False), \
             mock.patch.object(app.urllib.request, "build_opener") as request:
            with self.assertRaises(app.Unavailable):
                app.claude()
            request.assert_not_called()

    def test_claude_worker_timeout_stops_its_process(self):
        process = mock.Mock()
        process.communicate.side_effect = subprocess.TimeoutExpired("reader", 18)
        with mock.patch.object(app.subprocess, "Popen", return_value=process), \
             mock.patch.object(app, "stop_child") as stop:
            with self.assertRaises(app.Unavailable):
                app.claude_worker()
            stop.assert_called_once_with(process)
        app.CHILDREN.discard(process)


if __name__ == "__main__":
    unittest.main()
