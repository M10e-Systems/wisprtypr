from __future__ import annotations

import argparse
import os
import socket
import threading
from pathlib import Path


def default_socket_path() -> Path:
    return Path(f"/tmp/wisprtypr-control-{os.getuid()}.sock")


class ControlServer:
    def __init__(self, on_toggle, socket_path: Path | None = None) -> None:
        self._on_toggle = on_toggle
        self._socket_path = socket_path or default_socket_path()
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()

    @property
    def socket_path(self) -> Path:
        return self._socket_path

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        try:
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
                client.settimeout(0.2)
                client.connect(str(self._socket_path))
                client.sendall(b"__stop__\n")
        except OSError:
            pass

        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=1)
        self._thread = None

    def _run(self) -> None:
        self._socket_path.parent.mkdir(parents=True, exist_ok=True)
        if self._socket_path.exists():
            self._socket_path.unlink()

        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as server:
            server.bind(str(self._socket_path))
            server.listen(4)
            server.settimeout(0.5)
            while not self._stop_event.is_set():
                try:
                    conn, _addr = server.accept()
                except socket.timeout:
                    continue
                except OSError:
                    break

                with conn:
                    try:
                        raw = conn.recv(1024)
                    except OSError:
                        continue
                    command = raw.decode("utf-8", errors="ignore").strip().lower()
                    if command == "toggle":
                        self._on_toggle()

        try:
            if self._socket_path.exists():
                self._socket_path.unlink()
        except OSError:
            pass


def send_control_command(command: str, socket_path: Path | None = None, timeout: float = 1.0) -> bool:
    path = socket_path or default_socket_path()
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
        client.settimeout(timeout)
        client.connect(str(path))
        client.sendall((command.strip() + "\n").encode("utf-8"))
    return True


def toggle_main() -> None:
    parser = argparse.ArgumentParser(description="Toggle WisprTypr recording in the running tray app")
    parser.add_argument("--socket", type=Path, help="optional control socket path")
    args = parser.parse_args()

    try:
        send_control_command("toggle", socket_path=args.socket)
    except OSError as exc:
        raise SystemExit(f"failed to send toggle command: {exc}")
