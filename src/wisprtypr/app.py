from __future__ import annotations

from wisprtypr.controller import DictationController
from wisprtypr.injection import TextInjector
from wisprtypr.stt import WhisperTranscriber
from wisprtypr.tray import TrayIcon


class Application:
    def __init__(self) -> None:
        self._controller = None
        self._tray = TrayIcon(on_toggle=self._toggle, on_quit=self._quit)
        self._controller = DictationController(
            tray=self._tray,
            transcriber=WhisperTranscriber(),
            injector=TextInjector(),
        )

    def run(self) -> None:
        self._tray.run()

    def _toggle(self) -> None:
        if self._controller is not None:
            self._controller.toggle()

    def _quit(self) -> None:
        if self._controller is not None:
            self._controller.shutdown()
        self._tray.stop()
