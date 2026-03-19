from __future__ import annotations

from pathlib import Path

from wisprtypr.systemd_hooks import build_toggle_service


def test_build_toggle_service_includes_working_dir_and_command(tmp_path: Path):
    service_text = build_toggle_service(tmp_path, poetry_path="poetry")

    assert f"WorkingDirectory={tmp_path}" in service_text
    assert "ExecStart=/usr/bin/env poetry run wisprtypr-toggle" in service_text
    assert "poetry" in service_text
    assert "wisprtypr-toggle" in service_text
