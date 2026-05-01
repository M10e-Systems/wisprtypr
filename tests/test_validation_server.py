import threading
from http.server import ThreadingHTTPServer

from wisprtypr.validation import ValidationSpool
from wisprtypr.validation import ValidationUploader
from wisprtypr.settings import ValidationSettings
from wisprtypr.validation_server import ValidationStore
from wisprtypr.validation_server import build_handler


def _sample_record(audio_path):
    return {
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
            "path": str(audio_path),
        },
        "stt": {
            "model_name": "small.en",
            "compute_type": "auto",
            "language": "en",
            "context_seconds": 12,
            "raw_transcript": "hello world",
            "normalized_transcript": "Hello world",
            "injected_text": "Hello world",
        },
        "correction": {
            "observed": True,
            "confidence": 1.0,
            "corrected_text": "Hello world!",
            "latency_ms": 1000,
            "levenshtein_distance": 1,
            "kind": "replacement",
            "raw_events": [],
            "user_flagged_bad": False,
        },
        "window": {"app_name": "firefox", "title_hash": "hash"},
        "parameter_snapshot": {"energy_threshold": 0.015},
    }


def test_validation_server_accepts_multipart_upload(tmp_path):
    store = ValidationStore(db_path=tmp_path / "validation.sqlite3", blob_dir=tmp_path / "audio")
    server = ThreadingHTTPServer(("127.0.0.1", 0), build_handler(store))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    try:
        spool = ValidationSpool(root=tmp_path / "client")
        audio_path = spool.audio_dir / "u1.wav"
        audio_path.write_bytes(b"RIFF")
        record = _sample_record(audio_path)
        uploader = ValidationUploader(
            settings=ValidationSettings(validation_enabled=True, validation_server_url=f"http://127.0.0.1:{server.server_port}"),
            spool=spool,
        )
        response = uploader._post_multipart(
            f"http://127.0.0.1:{server.server_port}/v1/validation/utterances",
            record,
        )

        assert response["accepted"] is True
    finally:
        server.shutdown()
        server.server_close()


def test_validation_store_deduplicates_records(tmp_path):
    store = ValidationStore(db_path=tmp_path / "validation.sqlite3", blob_dir=tmp_path / "audio")
    record = _sample_record(tmp_path / "u1.wav")

    inserted = store.insert_utterance(record, b"audio", "u1.wav")
    inserted_again = store.insert_utterance(record, b"audio", "u1.wav")

    assert inserted is True
    assert inserted_again is False
