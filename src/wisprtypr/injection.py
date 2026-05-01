from __future__ import annotations

import subprocess
import time
from dataclasses import dataclass


class InjectionError(RuntimeError):
    """Raised when text injection fails."""


@dataclass
class ClipboardSnapshot:
    clipboard: str
    primary: str


@dataclass(frozen=True)
class InjectionResult:
    method: str


class TextInjector:
    def inject_text(self, text: str) -> InjectionResult:
        if not text:
            return InjectionResult(method="none")
        snapshot = self._snapshot_clipboards()
        try:
            self._set_clipboard(text)
            self._paste()
        except Exception:
            self._restore_clipboards(snapshot)
            self._type_text(text)
            return InjectionResult(method="type")
        else:
            self._restore_clipboards(snapshot)
            return InjectionResult(method="paste")

    def _snapshot_clipboards(self) -> ClipboardSnapshot:
        return ClipboardSnapshot(
            clipboard=self._read_selection("clipboard"),
            primary=self._read_selection("primary"),
        )

    def _restore_clipboards(self, snapshot: ClipboardSnapshot) -> None:
        self._write_selection("clipboard", snapshot.clipboard)
        self._write_selection("primary", snapshot.primary)

    def _set_clipboard(self, text: str) -> None:
        self._write_selection("clipboard", text)

    def _paste(self) -> None:
        paste_attempts = (
            ["xdotool", "key", "--clearmodifiers", "ctrl+v"],
            ["xdotool", "key", "--clearmodifiers", "shift+Insert"],
            ["xdotool", "key", "--clearmodifiers", "ctrl+shift+v"],
        )
        last_error = None
        for cmd in paste_attempts:
            try:
                subprocess.run(cmd, check=True, capture_output=True, text=True)
                time.sleep(0.05)
                return
            except Exception as exc:
                last_error = exc
        if last_error is not None:
            raise last_error

    def _type_text(self, text: str) -> None:
        subprocess.run(
            ["xdotool", "type", "--clearmodifiers", "--delay", "1", text],
            check=True,
            capture_output=True,
            text=True,
        )

    def _read_selection(self, selection: str) -> str:
        proc = subprocess.run(
            ["xsel", "--clipboard" if selection == "clipboard" else "--primary", "--output"],
            check=False,
            capture_output=True,
            text=True,
        )
        return proc.stdout

    def _write_selection(self, selection: str, text: str) -> None:
        proc = subprocess.run(
            ["xsel", "--clipboard" if selection == "clipboard" else "--primary", "--input"],
            input=text,
            check=False,
            capture_output=True,
            text=True,
        )
        if proc.returncode != 0:
            raise InjectionError(proc.stderr.strip() or f"failed to write {selection} selection")
