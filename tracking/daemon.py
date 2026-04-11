from __future__ import annotations

from pathlib import Path
from shlex import quote


def build_tracker_command(
    repo_root: str,
    *,
    base_url: str = "",
    sqlite_path: str = "data/v2/tracking/bets.sqlite",
    jsonl_path: str = "data/v2/tracking/tracker24h.jsonl",
    sample_every_min: int = 10,
    pinchtab_verify: bool = True,
) -> str:
    parts = [
        f"cd {quote(repo_root)} &&",
        "./.venv312/bin/python v2/tracking/run_until_kickoff.py",
        f"--sample-every-min {int(sample_every_min)}",
        f"--sqlite {quote(sqlite_path)}",
        f"--jsonl {quote(jsonl_path)}",
    ]
    if base_url:
        parts.append(f"--base-url {quote(base_url)}")
    if pinchtab_verify:
        parts.append("--pinchtab-verify")
    return " ".join(parts)


def render_cron_hourly(command: str) -> str:
    safe = command.replace('"', '\\"')
    return f'0 * * * * flock -n /tmp/aifootballbets_tracker24h.lock /bin/bash -lc "{safe}"\n'


def render_systemd_service(command: str, repo_root: str) -> str:
    return f"""[Unit]
Description=AIFootballBets OddsPortal tracker 24h
After=network-online.target

[Service]
Type=simple
WorkingDirectory={repo_root}
ExecStart=/bin/bash -lc '{command}'
Restart=always
RestartSec=10
Environment=PINCHTAB_TOKEN=%i
"""


def render_systemd_timer() -> str:
    return """[Unit]
Description=Run AIFootballBets tracker hourly

[Timer]
OnCalendar=hourly
Persistent=true

[Install]
WantedBy=timers.target
"""


def render_docker_compose(repo_root: str, command: str) -> str:
    safe = command.replace('"', '\\"')
    return f"""services:
  tracker24h:
    image: python:3.12-slim
    working_dir: {repo_root}
    command: /bin/bash -lc \"{safe}\"
    restart: unless-stopped
    environment:
      PINCHTAB_TOKEN: ${{PINCHTAB_TOKEN}}
"""


def render_logrotate(log_path: str) -> str:
    return f"""{log_path} {{
    daily
    rotate 7
    missingok
    compress
    copytruncate
}}
"""


def write_ops_bundle(root: Path) -> dict[str, Path]:
    root.mkdir(parents=True, exist_ok=True)
    command = build_tracker_command(repo_root=str(root))
    paths = {
        'cron': root / 'tracker24h.cron',
        'service': root / 'tracker24h.service',
        'timer': root / 'tracker24h.timer',
        'compose': root / 'docker-compose.tracker24h.yml',
        'logrotate': root / 'tracker24h.logrotate',
    }
    paths['cron'].write_text(render_cron_hourly(command), encoding='utf-8')
    paths['service'].write_text(render_systemd_service(command, str(root)), encoding='utf-8')
    paths['timer'].write_text(render_systemd_timer(), encoding='utf-8')
    paths['compose'].write_text(render_docker_compose(str(root), command), encoding='utf-8')
    paths['logrotate'].write_text(render_logrotate(str(root / 'logs' / 'tracker24h.log')), encoding='utf-8')
    return paths
