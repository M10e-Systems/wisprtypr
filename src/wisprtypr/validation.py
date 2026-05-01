from __future__ import annotations

import hashlib
import json
import subprocess
import threading
import time
import urllib.error
import urllib.request
import uuid
import wave
from dataclasses import dataclass
from dataclasses import field
from datetime import UTC
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np

from wisprtypr.settings import ValidationSettings

try:  # pragma: no cover - depends on host packages
    from Xlib import X
    from Xlib import XK
    from Xlib.display import Display
    from Xlib.ext import record
    from Xlib.protocol import rq

    HAS_XLIB = True
except ImportError:  # pragma: no cover - depends on host packages
    X = XK = Display = record = rq = None
    HAS_XLIB = False


def default_validation_state_dir() -> Path:
    return Path.home() / ".local" / "state" / "wisprtypr" / "validation"


def iso_now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def utc_timestamp() -> float:
    return datetime.now(UTC).timestamp()


@dataclass(frozen=True)
class InjectionMetadata:
    method: str


@dataclass
class CorrectionEvent:
    kind: str
    value: str
    timestamp: float


@dataclass
class CorrectionSummary:
    observed: bool
    confidence: float
    corrected_text: str
    latency_ms: int
    levenshtein_distance: int
    kind: str
    raw_events: list[dict[str, Any]] = field(default_factory=list)
    user_flagged_bad: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "observed": self.observed,
            "confidence": self.confidence,
            "corrected_text": self.corrected_text,
            "latency_ms": self.latency_ms,
            "levenshtein_distance": self.levenshtein_distance,
            "kind": self.kind,
            "raw_events": self.raw_events,
            "user_flagged_bad": self.user_flagged_bad,
        }


def _levenshtein_distance(left: str, right: str) -> int:
    if left == right:
        return 0
    if not left:
        return len(right)
    if not right:
        return len(left)
    previous = list(range(len(right) + 1))
    for left_index, left_char in enumerate(left, start=1):
        current = [left_index]
        for right_index, right_char in enumerate(right, start=1):
            insert_cost = current[right_index - 1] + 1
            delete_cost = previous[right_index] + 1
            replace_cost = previous[right_index - 1] + (left_char != right_char)
            current.append(min(insert_cost, delete_cost, replace_cost))
        previous = current
    return previous[-1]


def summarize_correction_events(
    injected_text: str,
    events: list[CorrectionEvent],
    started_at: float,
    user_flagged_bad: bool = False,
) -> CorrectionSummary:
    if not events and not user_flagged_bad:
        return CorrectionSummary(
            observed=False,
            confidence=0.0,
            corrected_text="",
            latency_ms=0,
            levenshtein_distance=0,
            kind="none",
            raw_events=[],
            user_flagged_bad=False,
        )

    typed = []
    backspaces = 0
    deletes = 0
    paste_seen = False
    first_timestamp = events[0].timestamp if events else started_at
    for event in events:
        if event.kind == "typed":
            typed.append(event.value)
        elif event.kind == "backspace":
            backspaces += 1
        elif event.kind == "delete":
            deletes += 1
        elif event.kind == "paste":
            paste_seen = True

    total_deleted = backspaces + deletes
    replacement = "".join(typed)
    corrected_text = injected_text
    kind = "flagged_bad" if user_flagged_bad else "unknown"
    confidence = 0.3 if user_flagged_bad else 0.0

    if total_deleted > 0:
        kept_length = max(0, len(injected_text) - total_deleted)
        corrected_text = injected_text[:kept_length] + replacement
        if replacement:
            kind = "replacement"
            confidence = 0.9 if first_timestamp - started_at <= 5 else 0.6
        else:
            kind = "deletion"
            confidence = 0.75 if first_timestamp - started_at <= 5 else 0.45
    elif replacement:
        corrected_text = injected_text + replacement
        kind = "append"
        confidence = 0.5

    if paste_seen:
        kind = "paste_replacement" if total_deleted else "paste"
        confidence = max(confidence, 0.85 if total_deleted else 0.55)

    if user_flagged_bad:
        confidence = max(confidence, 1.0)

    distance = _levenshtein_distance(injected_text, corrected_text)
    raw_events = [{"kind": event.kind, "value": event.value, "timestamp": event.timestamp} for event in events]
    return CorrectionSummary(
        observed=bool(events) or user_flagged_bad,
        confidence=round(confidence, 2),
        corrected_text=corrected_text,
        latency_ms=int(max(0.0, (first_timestamp - started_at) * 1000)),
        levenshtein_distance=distance,
        kind=kind,
        raw_events=raw_events,
        user_flagged_bad=user_flagged_bad,
    )


class ValidationSpool:
    def __init__(self, root: Path | None = None) -> None:
        self.root = root or default_validation_state_dir()
        self.pending_dir = self.root / "pending"
        self.uploaded_dir = self.root / "uploaded"
        self.audio_dir = self.root / "audio"
        self._ensure_dirs()

    def _ensure_dirs(self) -> None:
        self.pending_dir.mkdir(parents=True, exist_ok=True)
        self.uploaded_dir.mkdir(parents=True, exist_ok=True)
        self.audio_dir.mkdir(parents=True, exist_ok=True)

    def write_record(self, record: dict[str, Any], audio: np.ndarray) -> None:
        codec, audio_path = self._write_audio(record["utterance_id"], audio)
        record["audio"]["codec"] = codec
        record["audio"]["path"] = str(audio_path)
        record["audio"]["sha256"] = hashlib.sha256(audio_path.read_bytes()).hexdigest()
        self.pending_path(record["utterance_id"]).write_text(json.dumps(record, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    def update_record(self, utterance_id: str, updater) -> None:
        path = self.pending_path(utterance_id)
        if not path.exists():
            return
        record = json.loads(path.read_text(encoding="utf-8"))
        updater(record)
        path.write_text(json.dumps(record, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    def pending_records(self) -> list[dict[str, Any]]:
        records = []
        for path in sorted(self.pending_dir.glob("*.json")):
            records.append(json.loads(path.read_text(encoding="utf-8")))
        return records

    def mark_uploaded(self, utterance_id: str) -> None:
        pending = self.pending_path(utterance_id)
        if not pending.exists():
            return
        uploaded = self.uploaded_dir / pending.name
        pending.replace(uploaded)

    def delete_all(self) -> None:
        for path in list(self.pending_dir.glob("*")) + list(self.uploaded_dir.glob("*")) + list(self.audio_dir.glob("*")):
            if path.is_file():
                path.unlink()

    def cleanup_retention(self, retention_days: int) -> None:
        cutoff = time.time() - max(retention_days, 0) * 24 * 60 * 60
        for directory in (self.pending_dir, self.uploaded_dir, self.audio_dir):
            for path in directory.glob("*"):
                if path.is_file() and path.stat().st_mtime < cutoff:
                    path.unlink()

    def enforce_size_limit(self, max_pending_mb: int) -> None:
        max_bytes = max_pending_mb * 1024 * 1024
        pending_paths = sorted(self.pending_dir.glob("*.json"), key=lambda item: item.stat().st_mtime)
        while self._current_size_bytes() > max_bytes and pending_paths:
            oldest = pending_paths.pop(0)
            utterance_id = oldest.stem
            oldest.unlink(missing_ok=True)
            for audio_path in self.audio_dir.glob(f"{utterance_id}.*"):
                audio_path.unlink(missing_ok=True)

    def pending_path(self, utterance_id: str) -> Path:
        return self.pending_dir / f"{utterance_id}.json"

    def _current_size_bytes(self) -> int:
        total = 0
        for directory in (self.pending_dir, self.audio_dir):
            for path in directory.glob("*"):
                if path.is_file():
                    total += path.stat().st_size
        return total

    def _write_audio(self, utterance_id: str, audio: np.ndarray) -> tuple[str, Path]:
        wav_path = self.audio_dir / f"{utterance_id}.wav"
        self._write_wav(wav_path, audio)
        flac_path = self.audio_dir / f"{utterance_id}.flac"
        try:
            subprocess.run(
                ["ffmpeg", "-loglevel", "error", "-y", "-i", str(wav_path), str(flac_path)],
                check=True,
                capture_output=True,
                text=True,
            )
        except (FileNotFoundError, subprocess.CalledProcessError):
            return "wav", wav_path
        wav_path.unlink(missing_ok=True)
        return "flac", flac_path

    def _write_wav(self, path: Path, audio: np.ndarray) -> None:
        clipped = np.clip(audio.astype("float32"), -1.0, 1.0)
        pcm = np.int16(clipped * 32767.0)
        with wave.open(str(path), "wb") as handle:
            handle.setnchannels(1)
            handle.setsampwidth(2)
            handle.setframerate(16_000)
            handle.writeframes(pcm.tobytes())


class ValidationUploader:
    def __init__(
        self,
        settings: ValidationSettings,
        spool: ValidationSpool,
        interval_seconds: int = 30,
        before_upload=None,
    ) -> None:
        self._settings = settings
        self._spool = spool
        self._interval_seconds = interval_seconds
        self._before_upload = before_upload
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._kick_event = threading.Event()

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        self._kick_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2)
        self._thread = None

    def kick(self) -> None:
        self._kick_event.set()

    def upload_pending_now(self) -> None:
        if self._before_upload is not None:
            self._before_upload()
        for record in self._spool.pending_records():
            self._upload_record(record)

    def _run(self) -> None:
        while not self._stop_event.is_set():
            self._kick_event.wait(timeout=self._interval_seconds)
            self._kick_event.clear()
            if self._stop_event.is_set():
                return
            if not self._settings.validation_enabled:
                continue
            self.upload_pending_now()

    def _upload_record(self, record: dict[str, Any]) -> None:
        server_url = self._settings.validation_server_url.strip()
        if not server_url:
            return
        try:
            response = self._post_multipart(server_url.rstrip("/") + "/v1/validation/utterances", record)
        except (OSError, urllib.error.URLError):
            return
        if response.get("accepted"):
            self._spool.mark_uploaded(record["utterance_id"])

    def _post_multipart(self, url: str, record: dict[str, Any]) -> dict[str, Any]:
        audio_path = Path(record["audio"]["path"])
        boundary = f"wisprtypr-{uuid.uuid4().hex}"
        metadata = json.dumps(record).encode("utf-8")
        audio_bytes = audio_path.read_bytes()
        filename = audio_path.name
        body = bytearray()
        body.extend(f"--{boundary}\r\n".encode("utf-8"))
        body.extend(b'Content-Disposition: form-data; name="metadata"\r\n')
        body.extend(b"Content-Type: application/json\r\n\r\n")
        body.extend(metadata)
        body.extend(b"\r\n")
        body.extend(f"--{boundary}\r\n".encode("utf-8"))
        body.extend(
            f'Content-Disposition: form-data; name="audio"; filename="{filename}"\r\n'.encode("utf-8")
        )
        content_type = "audio/flac" if audio_path.suffix == ".flac" else "audio/wav"
        body.extend(f"Content-Type: {content_type}\r\n\r\n".encode("utf-8"))
        body.extend(audio_bytes)
        body.extend(b"\r\n")
        body.extend(f"--{boundary}--\r\n".encode("utf-8"))
        request = urllib.request.Request(
            url,
            data=bytes(body),
            headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=5) as response:
            return json.loads(response.read().decode("utf-8"))


class X11CorrectionObserver:
    def __init__(self, on_summary, edit_window_seconds: int = 20, time_fn=time.time) -> None:
        self._on_summary = on_summary
        self._edit_window_seconds = edit_window_seconds
        self._time_fn = time_fn
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._sessions: dict[str, dict[str, Any]] = {}
        self._lock = threading.Lock()
        self._enabled = HAS_XLIB

    @property
    def available(self) -> bool:
        return self._enabled

    def start(self) -> None:
        if not self._enabled:
            return
        if self._thread and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2)
        self._thread = None

    def begin_session(self, utterance_id: str, injected_text: str) -> None:
        with self._lock:
            self._sessions[utterance_id] = {
                "injected_text": injected_text,
                "started_at": self._time_fn(),
                "events": [],
                "user_flagged_bad": False,
            }

    def flag_bad(self, utterance_id: str) -> None:
        with self._lock:
            session = self._sessions.get(utterance_id)
            if session is not None:
                session["user_flagged_bad"] = True
            else:
                self._sessions[utterance_id] = {
                    "injected_text": "",
                    "started_at": self._time_fn(),
                    "events": [],
                    "user_flagged_bad": True,
                }

    def inject_events(self, utterance_id: str, events: list[CorrectionEvent]) -> None:
        with self._lock:
            session = self._sessions.get(utterance_id)
            if session is None:
                return
            session["events"].extend(events)

    def _run(self) -> None:  # pragma: no cover - depends on host X11 support
        if not HAS_XLIB:
            return
        local = Display()
        record_display = Display()
        if not record_display.has_extension("RECORD"):
            self._enabled = False
            local.close()
            record_display.close()
            return
        context = record_display.record_create_context(
            0,
            [record.AllClients],
            [
                {
                    "core_requests": (0, 0),
                    "core_replies": (0, 0),
                    "ext_requests": (0, 0, 0, 0),
                    "ext_replies": (0, 0, 0, 0),
                    "delivered_events": (0, 0),
                    "device_events": (X.KeyPress, X.KeyPress),
                    "errors": (0, 0),
                    "client_started": False,
                    "client_died": False,
                }
            ],
        )

        def handler(reply):
            if self._stop_event.is_set():
                return
            if reply.category != record.FromServer or reply.client_swapped or not reply.data:
                return
            data = reply.data
            while data:
                event, data = rq.EventField(None).parse_binary_value(data, record_display.display, None, None)
                if event.type != X.KeyPress:
                    continue
                translated = self._translate_key_event(local, event)
                if translated is None:
                    continue
                self._record_event(translated)

        try:
            record_display.record_enable_context(context, handler)
        finally:
            try:
                record_display.record_disable_context(context)
                record_display.record_free_context(context)
            except Exception:
                pass
            local.close()
            record_display.close()

    def _translate_key_event(self, display, event) -> CorrectionEvent | None:
        keysym = display.keycode_to_keysym(event.detail, 0)
        shift_keysym = display.keycode_to_keysym(event.detail, 1)
        ctrl_down = bool(event.state & X.ControlMask)
        shift_down = bool(event.state & X.ShiftMask)
        timestamp = self._time_fn()

        if keysym == XK.string_to_keysym("BackSpace"):
            return CorrectionEvent(kind="backspace", value="", timestamp=timestamp)
        if keysym == XK.string_to_keysym("Delete"):
            return CorrectionEvent(kind="delete", value="", timestamp=timestamp)

        for candidate in ("v", "V"):
            if ctrl_down and shift_keysym == XK.string_to_keysym(candidate):
                return CorrectionEvent(kind="paste", value="", timestamp=timestamp)
            if ctrl_down and keysym == XK.string_to_keysym(candidate):
                return CorrectionEvent(kind="paste", value="", timestamp=timestamp)
        if shift_down:
            keysym = shift_keysym or keysym
        char = XK.keysym_to_string(keysym)
        if ctrl_down or not char or len(char) != 1 or ord(char) < 32:
            return None
        return CorrectionEvent(kind="typed", value=char, timestamp=timestamp)

    def _record_event(self, event: CorrectionEvent) -> None:
        expired: list[tuple[str, CorrectionSummary]] = []
        with self._lock:
            now = self._time_fn()
            for utterance_id, session in list(self._sessions.items()):
                if now - session["started_at"] > self._edit_window_seconds:
                    expired.append((utterance_id, self._summarize_and_pop(utterance_id)))
            active_session_id = self._latest_session_id()
            if active_session_id is not None:
                self._sessions[active_session_id]["events"].append(event)
        for utterance_id, summary in expired:
            self._on_summary(utterance_id, summary)

    def flush_expired(self) -> None:
        expired: list[tuple[str, CorrectionSummary]] = []
        with self._lock:
            now = self._time_fn()
            for utterance_id in list(self._sessions):
                if now - self._sessions[utterance_id]["started_at"] >= self._edit_window_seconds:
                    expired.append((utterance_id, self._summarize_and_pop(utterance_id)))
        for utterance_id, summary in expired:
            self._on_summary(utterance_id, summary)

    def close_session(self, utterance_id: str) -> None:
        summary = None
        with self._lock:
            if utterance_id in self._sessions:
                summary = self._summarize_and_pop(utterance_id)
        if summary is not None:
            self._on_summary(utterance_id, summary)

    def _latest_session_id(self) -> str | None:
        if not self._sessions:
            return None
        return max(self._sessions, key=lambda utterance_id: self._sessions[utterance_id]["started_at"])

    def _summarize_and_pop(self, utterance_id: str) -> CorrectionSummary:
        session = self._sessions.pop(utterance_id)
        return summarize_correction_events(
            injected_text=session["injected_text"],
            events=session["events"],
            started_at=session["started_at"],
            user_flagged_bad=session["user_flagged_bad"],
        )


class ValidationManager:
    def __init__(
        self,
        settings: ValidationSettings,
        settings_path: Path | None = None,
        spool: ValidationSpool | None = None,
        uploader: ValidationUploader | None = None,
        observer: X11CorrectionObserver | None = None,
    ) -> None:
        self.settings = settings
        self.settings.ensure_ids()
        self._settings_path = settings_path
        self._spool = spool or ValidationSpool()
        self._observer = observer or X11CorrectionObserver(
            on_summary=self._apply_correction_summary,
            edit_window_seconds=settings.validation_capture_edit_window_seconds,
        )
        self._uploader = uploader or ValidationUploader(
            settings=settings,
            spool=self._spool,
            before_upload=self._observer.flush_expired,
        )
        self._lock = threading.Lock()
        self._last_utterance_id: str | None = None
        self._pending_context: dict[str, dict[str, Any]] = {}

    @property
    def enabled(self) -> bool:
        return self.settings.validation_enabled

    def start(self) -> None:
        self.settings.ensure_ids()
        self._spool.cleanup_retention(self.settings.validation_retention_days)
        self._spool.enforce_size_limit(self.settings.validation_max_pending_mb)
        self._observer.start()
        self._uploader.start()
        self._uploader.kick()

    def shutdown(self) -> None:
        self._observer.stop()
        self._uploader.stop()

    def set_enabled(self, enabled: bool) -> None:
        self.settings.validation_enabled = enabled
        self.settings.save(self._settings_path)
        if enabled:
            self._uploader.kick()

    def begin_utterance(self) -> str:
        utterance_id = uuid.uuid4().hex
        with self._lock:
            self._pending_context[utterance_id] = {"started_at": iso_now()}
            self._last_utterance_id = utterance_id
        return utterance_id

    def note_injection(self, utterance_id: str, full_text: str) -> None:
        if not self.enabled:
            return
        with self._lock:
            context = self._pending_context.setdefault(utterance_id, {"started_at": iso_now()})
            context["full_text"] = full_text
            self._last_utterance_id = utterance_id
        self._observer.begin_session(utterance_id, full_text)

    def complete_utterance(
        self,
        utterance_id: str,
        *,
        audio: np.ndarray,
        raw_transcript: str,
        normalized_transcript: str,
        injected_text: str,
        chunk_duration_seconds: int,
        transcriber_config: dict[str, Any],
        detector_config: dict[str, Any],
        injection_method: str,
    ) -> None:
        if not self.enabled:
            return
        window = self._capture_window_metadata()
        record = {
            "utterance_id": utterance_id,
            "user_id": self.settings.validation_client_id,
            "device_id": self.settings.validation_device_id,
            "created_at": iso_now(),
            "app": {
                "version": self._app_version(),
                "platform": "ubuntu-x11",
                "chunk_duration_seconds": chunk_duration_seconds,
                "injection_method": injection_method,
            },
            "audio": {
                "sample_rate_hz": 16_000,
                "channels": 1,
                "duration_ms": int((len(audio) / 16_000) * 1000),
                "sha256": "",
            },
            "stt": {
                "raw_transcript": raw_transcript,
                "normalized_transcript": normalized_transcript,
                "injected_text": injected_text,
                **transcriber_config,
            },
            "correction": {
                "observed": False,
                "confidence": 0.0,
                "corrected_text": "",
                "latency_ms": 0,
                "levenshtein_distance": 0,
                "kind": "none",
                "raw_events": [],
                "user_flagged_bad": False,
            },
            "window": window,
            "parameter_snapshot": detector_config,
        }
        self._spool.write_record(record, audio)
        self._spool.enforce_size_limit(self.settings.validation_max_pending_mb)

    def mark_last_utterance_wrong(self) -> None:
        utterance_id = self._last_utterance_id
        if utterance_id is None:
            return
        self._observer.flag_bad(utterance_id)
        self._apply_correction_summary(
            utterance_id,
            summarize_correction_events("", [], time.time(), user_flagged_bad=True),
        )

    def upload_pending_now(self) -> None:
        self._observer.flush_expired()
        self._uploader.upload_pending_now()

    def delete_pending_data(self) -> None:
        self._spool.delete_all()

    def finalize_observation(self, utterance_id: str) -> None:
        self._observer.close_session(utterance_id)

    def _apply_correction_summary(self, utterance_id: str, summary: CorrectionSummary) -> None:
        if not summary.observed:
            return

        def updater(record: dict[str, Any]) -> None:
            record["correction"] = summary.to_dict()

        self._spool.update_record(utterance_id, updater)

    def _capture_window_metadata(self) -> dict[str, Any]:
        app_name = ""
        title = ""
        try:
            app_name = self._run_command(["xdotool", "getactivewindow", "getwindowclassname"])
            title = self._run_command(["xdotool", "getactivewindow", "getwindowname"])
        except OSError:
            pass
        return {
            "app_name": app_name.strip(),
            "title_hash": hashlib.sha256(title.strip().encode("utf-8")).hexdigest() if title else "",
        }

    def _run_command(self, command: list[str]) -> str:
        proc = subprocess.run(command, check=True, capture_output=True, text=True)
        return proc.stdout.strip()

    def _app_version(self) -> str:
        try:
            from importlib.metadata import version

            return version("wisprtypr")
        except Exception:
            return "0.1.0"
