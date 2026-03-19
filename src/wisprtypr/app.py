from __future__ import annotations

from wisprtypr.control import ControlServer
from wisprtypr.controller import DictationController
from wisprtypr.injection import TextInjector
from wisprtypr.stt import WhisperTranscriber
from wisprtypr.tray import TrayIcon
from wisprtypr.tray import GLib


class Application:
    def __init__(self) -> None:
        self._controller = None
        self._control = ControlServer(on_toggle=self._toggle_from_control)
        self._tray = TrayIcon(on_toggle=self._toggle, on_quit=self._quit)
        self._controller = DictationController(
            tray=self._tray,
            transcriber=WhisperTranscriber(),
            injector=TextInjector(),
        )

    def run(self) -> None:
        self._control.start()
        try:
            self._tray.run()
        finally:
            self._control.stop()

    def _toggle(self) -> None:
        if self._controller is not None:
            self._controller.toggle()

    def _toggle_from_control(self) -> None:
        GLib.idle_add(self._toggle_from_control_sync)

    def _toggle_from_control_sync(self) -> bool:
        self._toggle()
        return False

    def _quit(self) -> None:
        if self._controller is not None:
            self._controller.shutdown()
        self._control.stop()
        self._tray.stop()
