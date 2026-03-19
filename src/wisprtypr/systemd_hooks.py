from __future__ import annotations

import subprocess
from pathlib import Path


TOGGLE_SERVICE_TEMPLATE = """[Unit]
Description=Toggle WisprTypr Recording

[Service]
Type=oneshot
WorkingDirectory={working_dir}
ExecStart={exec_start}

[Install]
WantedBy=default.target
"""


def build_toggle_service(working_dir: Path, poetry_path: str = "poetry") -> str:
    exec_start = f"/usr/bin/env {poetry_path} run wisprtypr-toggle"
    return TOGGLE_SERVICE_TEMPLATE.format(working_dir=str(working_dir), exec_start=exec_start)


def install_systemd_toggle_hook(working_dir: Path | None = None, poetry_path: str = "poetry") -> Path:
    resolved_working_dir = (working_dir or Path.cwd()).resolve()
    user_systemd_dir = Path.home() / ".config" / "systemd" / "user"
    target = user_systemd_dir / "wisprtypr-toggle.service"
    user_systemd_dir.mkdir(parents=True, exist_ok=True)
    target.write_text(build_toggle_service(resolved_working_dir, poetry_path=poetry_path), encoding="utf-8")

    subprocess.run(["systemctl", "--user", "daemon-reload"], check=True)
    return target


def main() -> None:
    path = install_systemd_toggle_hook()
    print(f"Installed systemd toggle hook at {path}")
    print("Use: systemctl --user start wisprtypr-toggle")
