from __future__ import annotations

from pathlib import Path


AUTOSTART_TEMPLATE = """[Desktop Entry]
Type=Application
Version=1.0
Name=WisprTypr
Comment=Tray dictation for Ubuntu/Xfce on X11
Exec={exec_path}
Terminal=false
Categories=Utility;
StartupNotify=false
"""


def install_autostart(exec_path: str = "wisprtypr") -> Path:
    target = Path.home() / ".config" / "autostart" / "wisprtypr.desktop"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(AUTOSTART_TEMPLATE.format(exec_path=exec_path))
    return target


def main() -> None:
    path = install_autostart()
    print(f"Installed autostart entry at {path}")
