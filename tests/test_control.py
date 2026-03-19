from __future__ import annotations

import threading
import time

from wisprtypr.control import ControlServer, send_control_command


def test_control_server_receives_toggle(tmp_path):
    toggled = threading.Event()
    socket_path = tmp_path / "control.sock"
    server = ControlServer(on_toggle=toggled.set, socket_path=socket_path)

    server.start()
    try:
        deadline = time.time() + 2
        while time.time() < deadline and not socket_path.exists():
            time.sleep(0.01)

        assert socket_path.exists()
        send_control_command("toggle", socket_path=socket_path)
        assert toggled.wait(timeout=1)
    finally:
        server.stop()


def test_control_server_cleans_up_socket(tmp_path):
    socket_path = tmp_path / "control.sock"
    server = ControlServer(on_toggle=lambda: None, socket_path=socket_path)

    server.start()
    deadline = time.time() + 2
    while time.time() < deadline and not socket_path.exists():
        time.sleep(0.01)

    server.stop()

    assert not socket_path.exists()
