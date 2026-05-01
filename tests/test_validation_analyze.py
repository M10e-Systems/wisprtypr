import json
import sqlite3

from wisprtypr.validation_analyze import generate_ticket_drafts
from wisprtypr.validation_server import ValidationStore


def test_generate_ticket_drafts_from_corrections(tmp_path):
    store = ValidationStore(db_path=tmp_path / "validation.sqlite3", blob_dir=tmp_path / "audio")
    record = {
        "utterance_id": "u1",
        "user_id": "client-1",
        "device_id": "device-1",
        "created_at": "2026-01-01T00:00:00Z",
        "app": {
            "version": "0.1.0",
            "platform": "ubuntu-x11",
            "chunk_duration_seconds": 4,
            "injection_method": "paste",
        },
        "audio": {
            "codec": "wav",
            "sample_rate_hz": 16000,
            "channels": 1,
            "duration_ms": 1000,
            "sha256": "abc",
        },
        "stt": {
            "model_name": "small.en",
            "compute_type": "auto",
            "language": "en",
            "context_seconds": 12,
            "raw_transcript": "hello world",
            "normalized_transcript": "hello world",
            "injected_text": "hello world",
        },
        "correction": {
            "observed": True,
            "confidence": 1.0,
            "corrected_text": "Hello world",
            "latency_ms": 1000,
            "levenshtein_distance": 1,
            "kind": "replacement",
            "raw_events": [],
            "user_flagged_bad": False,
        },
        "window": {"app_name": "firefox", "title_hash": "hash"},
        "parameter_snapshot": {},
    }
    store.insert_utterance(record, b"audio", "u1.wav")

    drafts = generate_ticket_drafts(tmp_path / "validation.sqlite3", min_cases=1)

    assert len(drafts) == 1
    assert drafts[0]["severity"] == "medium"
    with sqlite3.connect(tmp_path / "validation.sqlite3") as connection:
        stored = connection.execute("SELECT title, evidence_json FROM ticket_drafts").fetchone()
    assert "Normalize casing" in stored[0]
    assert json.loads(stored[1])["count"] == 1
