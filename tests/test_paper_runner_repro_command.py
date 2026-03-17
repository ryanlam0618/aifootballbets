import json
import subprocess
import tempfile
import unittest
from pathlib import Path


class TestPaperRunnerReproCommand(unittest.TestCase):
    def test_repro_script_runs_with_defaults_and_outputs_final_metrics(self):
        repo_root = Path(__file__).resolve().parents[1]

        with tempfile.TemporaryDirectory() as td:
            tdp = Path(td)
            sqlite_path = tdp / "bets_repro.sqlite"
            snapshot_db = tdp / "snap_repro.sqlite"
            out_dir = tdp / "reports_repro"
            decision_dir = tdp / "decisions_repro"

            cmd = [
                "python3",
                "scripts/paper_run_7d_repro.py",
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
            self.assertIn("[ONE-COMMAND] final_pnl=", proc.stdout)
            self.assertIn(" roi=", proc.stdout)
            self.assertIn(" max_dd=", proc.stdout)

            summary_json = out_dir / "paper_7d_summary_2026-03-16.json"
            self.assertTrue(summary_json.exists())

            payload = json.loads(summary_json.read_text(encoding="utf-8"))
            self.assertEqual(float(payload.get("initial_bankroll", 0)), 2000.0)
            self.assertEqual(payload.get("start_date"), "2026-03-10")
            self.assertEqual(payload.get("end_date"), "2026-03-16")
            self.assertIn("summary", payload)
            self.assertIn("pnl", payload["summary"])
            self.assertIn("roi_pct", payload["summary"])
            self.assertIn("max_drawdown_pct", payload["summary"])


if __name__ == "__main__":
    unittest.main()
