import json

import numpy as np

from wisprtypr.settings import ValidationSettings
from wisprtypr.validation import CorrectionEvent
from wisprtypr.validation import ValidationManager
from wisprtypr.validation import ValidationSpool
from wisprtypr.validation import summarize_correction_events


class FakeObserver:
    def __init__(self, on_summary=None, edit_window_seconds=20):
        self.started = 0
        self.stopped = 0
        self.begun = []
        self.flagged = []

    def start(self):
        self.started += 1

    def stop(self):
        self.stopped += 1

    def begin_session(self, utterance_id, injected_text):
        self.begun.append((utterance_id, injected_text))

    def flag_bad(self, utterance_id):
        self.flagged.append(utterance_id)

    def flush_expired(self):
        return None


class FakeUploader:
    def __init__(self, settings, spool, interval_seconds=30):
        self.started = 0
        self.stopped = 0
        self.uploads = 0
        self.kicks = 0

    def start(self):
        self.started += 1

    def stop(self):
        self.stopped += 1

    def kick(self):
        self.kicks += 1

    def upload_pending_now(self):
        self.uploads += 1


def test_summarize_correction_events_reconstructs_replacement():
    summary = summarize_correction_events(
        "Hello worlt",
        [
            CorrectionEvent(kind="backspace", value="", timestamp=1.0),
            CorrectionEvent(kind="typed", value="d", timestamp=1.1),
        ],
        started_at=0.0,
    )

    assert summary.observed is True
    assert summary.corrected_text == "Hello world"
    assert summary.kind == "replacement"
    assert summary.confidence >= 0.6


def test_validation_manager_writes_record_and_marks_bad(tmp_path, monkeypatch):
    settings = ValidationSettings(validation_enabled=True)
    spool = ValidationSpool(root=tmp_path / "validation")
    manager = ValidationManager(
        settings=settings,
        settings_path=tmp_path / "settings.json",
        spool=spool,
        uploader=FakeUploader(settings, spool),
        observer=FakeObserver(),
    )
    monkeypatch.setattr(
        manager,
        "_capture_window_metadata",
        lambda: {"app_name": "firefox", "title_hash": "abc"},
    )

    utterance_id = manager.begin_utterance()
    manager.note_injection(utterance_id, full_text="Hello world")
    manager.complete_utterance(
        utterance_id,
        audio=np.zeros(16_000, dtype="float32"),
        raw_transcript="hello world",
        normalized_transcript="Hello world",
        injected_text="Hello world",
        chunk_duration_seconds=4,
        transcriber_config={
            "model_name": "small.en",
            "compute_type": "auto",
            "language": "en",
            "context_seconds": 12,
        },
        detector_config={"energy_threshold": 0.015},
        injection_method="paste",
    )
    manager.mark_last_utterance_wrong()

    record = json.loads(spool.pending_path(utterance_id).read_text(encoding="utf-8"))
    assert record["stt"]["normalized_transcript"] == "Hello world"
    assert record["correction"]["user_flagged_bad"] is True
    assert record["audio"]["codec"] in {"flac", "wav"}


def test_validation_spool_enforces_size_limit(tmp_path):
    spool = ValidationSpool(root=tmp_path / "validation")
    sample_audio = np.zeros(8_000, dtype="float32")
    for index in range(2):
        spool.write_record(
            {
                "utterance_id": f"u{index}",
                "user_id": "u",
                "device_id": "d",
                "created_at": "2026-01-01T00:00:00Z",
                "app": {
                    "version": "0.1.0",
                    "platform": "ubuntu-x11",
                    "chunk_duration_seconds": 4,
                    "injection_method": "paste",
                },
                "audio": {"sample_rate_hz": 16_000, "channels": 1, "duration_ms": 500, "sha256": ""},
                "stt": {
                    "model_name": "small.en",
                    "compute_type": "auto",
                    "language": "en",
                    "context_seconds": 12,
                    "raw_transcript": "hello",
                    "normalized_transcript": "Hello",
                    "injected_text": "Hello",
                },
                "correction": {"observed": False, "confidence": 0.0, "corrected_text": "", "latency_ms": 0, "levenshtein_distance": 0, "kind": "none", "raw_events": [], "user_flagged_bad": False},
                "window": {"app_name": "", "title_hash": ""},
                "parameter_snapshot": {},
            },
            sample_audio,
        )

    spool.enforce_size_limit(0)

    assert spool.pending_records() == []


def test_prepare_disable_reports_pending_state(tmp_path):
    settings = ValidationSettings(validation_enabled=True)
    spool = ValidationSpool(root=tmp_path / "validation")
    manager = ValidationManager(
        settings=settings,
        settings_path=tmp_path / "settings.json",
        spool=spool,
        uploader=FakeUploader(settings, spool),
        observer=FakeObserver(),
    )
    assert manager.prepare_disable() == "no_pending"

    spool.pending_path("u1").write_text('{"utterance_id":"u1"}\n', encoding="utf-8")
    assert manager.prepare_disable() == "pending_exists"
