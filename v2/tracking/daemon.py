from __future__ import annotations

from pathlib import Path
import shlex


def _escape_double_quoted_shell(s: str) -> str:
    return str(s).replace("\\", "\\\\").replace('"', '\\"')


def build_tracker_command(
    repo_root: str,
    python_bin: str = "./.venv312/bin/python",
    script_path: str = "v2/tracking/run_until_kickoff.py",
    base_url: str = "https://www.oddsportal.com/football/england/premier-league/brentford-wolves-0jR7cwU6/",
    sample_every_min: int = 10,
    sqlite_path: str = "data/v2/tracking/brentford_wolves_until_kickoff.sqlite",
    jsonl_path: str = "data/v2/tracking/brentford_wolves_until_kickoff.jsonl",
    storage_state: str = "/tmp/oddsportal_storage.json",
    top_lines: int = 2,
    prefer_lines_ou: str = "2.5,2.75",
    prefer_lines_ah: str = "-0.25,0.0",
    pinchtab_verify: bool = True,
) -> str:
    parts = [
        python_bin,
        script_path,
        "--base-url",
        base_url,
        "--sample-every-min",
        str(int(sample_every_min)),
        "--top-lines",
        str(int(top_lines)),
        "--prefer-lines-ou",
        prefer_lines_ou,
        "--prefer-lines-ah",
        prefer_lines_ah,
        "--sqlite",
        sqlite_path,
        "--jsonl",
        jsonl_path,
        "--storage-state",
        storage_state,
    ]
    if pinchtab_verify:
        parts.append("--pinchtab-verify")

    quoted = " ".join(shlex.quote(p) for p in parts)
    return f"cd {shlex.quote(repo_root)} && {quoted}"


def render_cron_hourly(command: str, log_path: str = "logs/tracker24h.log") -> str:
    safe_command = _escape_double_quoted_shell(command)
    return (
        "# aifootballbets tracker 24h (hourly watchdog)\n"
        "SHELL=/bin/bash\n"
        "PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin\n"
        f"0 * * * * flock -n /tmp/aifootballbets_tracker24h.lock bash -lc \"{safe_command}\" >> {log_path} 2>&1\n"
    )


def render_systemd_service(command: str, repo_root: str) -> str:
    return (
        "[Unit]\n"
        "Description=AIFootballBets OddsPortal tracker 24h\n"
        "After=network-online.target\n"
        "Wants=network-online.target\n\n"
        "[Service]\n"
        "Type=simple\n"
        "WorkingDirectory={repo}\n"
        "ExecStart=/bin/bash -lc '{cmd}'\n"
        "Restart=always\n"
        "RestartSec=15\n"
        "StandardOutput=append:{repo}/logs/tracker24h.log\n"
        "StandardError=append:{repo}/logs/tracker24h.log\n\n"
        "[Install]\n"
        "WantedBy=multi-user.target\n"
    ).format(repo=repo_root, cmd=command)


def render_systemd_timer() -> str:
    return (
        "[Unit]\n"
        "Description=Watchdog for AIFootballBets tracker 24h\n\n"
        "[Timer]\n"
        "OnCalendar=hourly\n"
        "Persistent=true\n"
        "Unit=aifootballbets-tracker24h.service\n\n"
        "[Install]\n"
        "WantedBy=timers.target\n"
    )


def render_docker_compose(repo_root: str, command: str) -> str:
    return (
        "services:\n"
        "  tracker24h:\n"
        "    image: python:3.12-slim\n"
        "    working_dir: /workspace\n"
        f"    command: [\"/bin/bash\", \"-lc\", \"{command}\"]\n"
        "    volumes:\n"
        f"      - {repo_root}:/workspace\n"
        "    restart: unless-stopped\n"
        "    environment:\n"
        "      - PINCHTAB_TOKEN=${PINCHTAB_TOKEN:-}\n"
    )


def render_logrotate(log_path: str, rotate_count: int = 14) -> str:
    return (
        f"{log_path} {{\n"
        "  daily\n"
        f"  rotate {int(rotate_count)}\n"
        "  missingok\n"
        "  notifempty\n"
        "  compress\n"
        "  copytruncate\n"
        "}\n"
    )


def write_ops_bundle(repo_root: Path) -> dict[str, Path]:
    command = build_tracker_command(repo_root=str(repo_root))

    out_dir = repo_root / "ops" / "tracker24h"
    out_dir.mkdir(parents=True, exist_ok=True)
    (repo_root / "logs").mkdir(parents=True, exist_ok=True)

    paths = {
        "cron": out_dir / "tracker24h.cron",
        "service": out_dir / "aifootballbets-tracker24h.service",
        "timer": out_dir / "aifootballbets-tracker24h.timer",
        "compose": out_dir / "docker-compose.tracker24h.yml",
        "logrotate": out_dir / "tracker24h.logrotate",
    }

    paths["cron"].write_text(render_cron_hourly(command), encoding="utf-8")
    paths["service"].write_text(render_systemd_service(command, str(repo_root)), encoding="utf-8")
    paths["timer"].write_text(render_systemd_timer(), encoding="utf-8")
    paths["compose"].write_text(render_docker_compose(str(repo_root), command), encoding="utf-8")
    paths["logrotate"].write_text(render_logrotate(str(repo_root / "logs" / "tracker24h.log")), encoding="utf-8")

    return paths


if __name__ == "__main__":
    write_ops_bundle(Path(__file__).resolve().parents[2])
