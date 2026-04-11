import tempfile
import unittest
from pathlib import Path

from tracking.daemon import (
    build_tracker_command,
    render_cron_hourly,
    render_docker_compose,
    render_logrotate,
    render_systemd_service,
    render_systemd_timer,
    write_ops_bundle,
)


class TestTracker24hDaemon(unittest.TestCase):
    def test_build_tracker_command_contains_required_args(self):
        cmd = build_tracker_command(repo_root="/repo")
        self.assertIn("cd /repo &&", cmd)
        self.assertIn("v2/tracking/run_until_kickoff.py", cmd)
        self.assertIn("--sample-every-min 10", cmd)
        self.assertIn("--pinchtab-verify", cmd)

    def test_build_tracker_command_shell_quotes_paths(self):
        cmd = build_tracker_command(
            repo_root="/tmp/repo with space",
            base_url="https://example.com/match?x=1&y=2",
            sqlite_path="data/v2/tracking/a b.sqlite",
            jsonl_path="data/v2/tracking/a b.jsonl",
        )
        self.assertIn("cd '/tmp/repo with space' &&", cmd)
        self.assertIn("--sqlite 'data/v2/tracking/a b.sqlite'", cmd)
        self.assertIn("--jsonl 'data/v2/tracking/a b.jsonl'", cmd)

    def test_cron_renderer_escapes_double_quotes(self):
        command = "cd '/repo with space' && ./.venv312/bin/python s.py --base-url 'https://x?m=\"abc\"'"
        cron = render_cron_hourly(command)
        self.assertIn('\\"abc\\"', cron)

    def test_renderers_include_expected_markers(self):
        command = "cd /repo && ./.venv312/bin/python v2/tracking/run_until_kickoff.py"

        cron = render_cron_hourly(command)
        self.assertIn("0 * * * *", cron)
        self.assertIn("flock -n /tmp/aifootballbets_tracker24h.lock", cron)

        service = render_systemd_service(command, "/repo")
        self.assertIn("Description=AIFootballBets OddsPortal tracker 24h", service)
        self.assertIn("Restart=always", service)

        timer = render_systemd_timer()
        self.assertIn("OnCalendar=hourly", timer)

        compose = render_docker_compose("/repo", command)
        self.assertIn("restart: unless-stopped", compose)
        self.assertIn("PINCHTAB_TOKEN", compose)

        logrotate = render_logrotate("/repo/logs/tracker24h.log")
        self.assertIn("daily", logrotate)
        self.assertIn("copytruncate", logrotate)

    def test_write_ops_bundle_creates_all_files(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            paths = write_ops_bundle(root)

            expected = {"cron", "service", "timer", "compose", "logrotate"}
            self.assertEqual(set(paths.keys()), expected)
            for p in paths.values():
                self.assertTrue(p.exists(), f"missing file: {p}")
                self.assertGreater(len(p.read_text(encoding='utf-8').strip()), 0)


if __name__ == "__main__":
    unittest.main()
