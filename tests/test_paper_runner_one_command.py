import json
import subprocess
import tempfile
import unittest
from pathlib import Path


class TestPaperRunnerOneCommand(unittest.TestCase):
    def test_scripts_paper_run_7d_outputs_final_summary_metrics(self):
        repo_root = Path(__file__).resolve().parents[1]
        fixture = repo_root / "tests" / "fixtures" / "paper7d_provider.json"

        with tempfile.TemporaryDirectory() as td:
            tdp = Path(td)
            sqlite_path = tdp / "tracking.sqlite"
            snapshot_db = tdp / "snap.sqlite"
            out_dir = tdp / "reports"
            decision_dir = tdp / "decisions"

            cmd = [
                "python3",
                "scripts/paper_run_7d.py",
                "--start-date",
                "2026-03-10",
                "--bankroll",
                "2000",
                "--provider-json",
                str(fixture),
                "--sqlite",
                str(sqlite_path),
                "--snapshot-db",
                str(snapshot_db),
                "--out-dir",
                str(out_dir),
                "--decision-log-dir",
                str(decision_dir),
            ]

            proc = subprocess.run(
                cmd,
                cwd=str(repo_root),
                capture_output=True,
                text=True,
                check=False,
            )

            self.assertEqual(proc.returncode, 0, msg=proc.stdout + "\n" + proc.stderr)
            self.assertIn("[7D SUMMARY] final_pnl=", proc.stdout)
            self.assertIn(" roi=", proc.stdout)
            self.assertIn(" max_dd=", proc.stdout)

            summary_json = out_dir / "paper_7d_summary_2026-03-16.json"
            self.assertTrue(summary_json.exists())

            payload = json.loads(summary_json.read_text(encoding="utf-8"))
            self.assertEqual(float(payload.get("initial_bankroll", 0)), 2000.0)
            self.assertIn("summary", payload)
            self.assertIn("pnl", payload["summary"])
            self.assertIn("roi_pct", payload["summary"])
            self.assertIn("max_drawdown_pct", payload["summary"])


if __name__ == "__main__":
    unittest.main()
