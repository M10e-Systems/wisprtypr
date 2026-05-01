from __future__ import annotations

from wisprtypr.control import ControlServer
from wisprtypr.controller import DictationController
from wisprtypr.injection import TextInjector
from wisprtypr.settings import ValidationSettings
from wisprtypr.stt import WhisperTranscriber
from wisprtypr.tray import TrayIcon
from wisprtypr.tray import GLib
from wisprtypr.validation import ValidationManager


class Application:
    def __init__(self) -> None:
        self._controller = None
        self._validation = ValidationManager(settings=ValidationSettings.load())
        self._control = ControlServer(on_toggle=self._toggle_from_control)
        self._tray = TrayIcon(on_toggle=self._toggle, on_quit=self._quit)
        self._controller = DictationController(
            tray=self._tray,
            transcriber=WhisperTranscriber(),
            injector=TextInjector(),
            validation_manager=self._validation,
        )
        self._tray.set_validation_actions(
            enabled=self._validation.enabled,
            on_enable=self._enable_validation,
            on_disable=self._disable_validation,
            on_mark_last_bad=self._mark_last_utterance_wrong,
            on_upload_pending=self._upload_pending_validation,
            on_delete_pending=self._delete_pending_validation,
        )

    def run(self) -> None:
        self._control.start()
        self._validation.start()
        try:
            self._tray.run()
        finally:
            self._control.stop()
            self._validation.shutdown()

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
        self._validation.shutdown()
        self._tray.stop()

    def _enable_validation(self) -> None:
        self._validation.set_enabled(True)

    def _disable_validation(self) -> None:
        self._validation.set_enabled(False)

    def _mark_last_utterance_wrong(self) -> None:
        self._validation.mark_last_utterance_wrong()

    def _upload_pending_validation(self) -> None:
        self._validation.upload_pending_now()

    def _delete_pending_validation(self) -> None:
        self._validation.delete_pending_data()
