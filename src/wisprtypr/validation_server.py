from __future__ import annotations

import argparse
import cgi
import json
import sqlite3
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler
from http.server import ThreadingHTTPServer
from pathlib import Path
from typing import Any


SCHEMA = """
CREATE TABLE IF NOT EXISTS utterances (
    utterance_id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    device_id TEXT NOT NULL,
    created_at TEXT NOT NULL,
    app_version TEXT NOT NULL,
    platform TEXT NOT NULL,
    chunk_duration_seconds INTEGER NOT NULL,
    injection_method TEXT NOT NULL,
    audio_codec TEXT NOT NULL,
    audio_path TEXT NOT NULL,
    audio_sha256 TEXT NOT NULL,
    duration_ms INTEGER NOT NULL,
    model_name TEXT NOT NULL,
    compute_type TEXT NOT NULL,
    language TEXT NOT NULL,
    context_seconds INTEGER NOT NULL,
    raw_transcript TEXT NOT NULL,
    normalized_transcript TEXT NOT NULL,
    injected_text TEXT NOT NULL,
    window_app_name TEXT NOT NULL,
    window_title_hash TEXT NOT NULL,
    parameter_snapshot_json TEXT NOT NULL,
    user_flagged_bad INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS corrections (
    utterance_id TEXT PRIMARY KEY,
    observed INTEGER NOT NULL,
    confidence REAL NOT NULL,
    corrected_text TEXT NOT NULL,
    latency_ms INTEGER NOT NULL,
    levenshtein_distance INTEGER NOT NULL,
    kind TEXT NOT NULL,
    raw_events_json TEXT NOT NULL,
    FOREIGN KEY (utterance_id) REFERENCES utterances (utterance_id)
);
CREATE TABLE IF NOT EXISTS ticket_drafts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    generated_at TEXT NOT NULL,
    cluster_key TEXT NOT NULL,
    title TEXT NOT NULL,
    severity TEXT NOT NULL,
    evidence_json TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'draft'
);
"""


class ValidationStore:
    def __init__(self, db_path: Path, blob_dir: Path) -> None:
        self.db_path = db_path
        self.blob_dir = blob_dir
        self.blob_dir.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _initialize(self) -> None:
        with sqlite3.connect(self.db_path) as connection:
            connection.executescript(SCHEMA)

    def insert_utterance(self, record: dict[str, Any], audio_bytes: bytes, filename: str) -> bool:
        utterance_id = record["utterance_id"]
        audio_path = self.blob_dir / f"{utterance_id}{Path(filename).suffix or '.bin'}"
        with sqlite3.connect(self.db_path) as connection:
            exists = connection.execute(
                "SELECT 1 FROM utterances WHERE utterance_id = ?",
                (utterance_id,),
            ).fetchone()
            if exists:
                return False
            audio_path.write_bytes(audio_bytes)
            connection.execute(
                """
                INSERT INTO utterances (
                    utterance_id, user_id, device_id, created_at, app_version, platform,
                    chunk_duration_seconds, injection_method, audio_codec, audio_path,
                    audio_sha256, duration_ms, model_name, compute_type, language,
                    context_seconds, raw_transcript, normalized_transcript, injected_text,
                    window_app_name, window_title_hash, parameter_snapshot_json, user_flagged_bad
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    utterance_id,
                    record["user_id"],
                    record["device_id"],
                    record["created_at"],
                    record["app"]["version"],
                    record["app"]["platform"],
                    record["app"]["chunk_duration_seconds"],
                    record["app"]["injection_method"],
                    record["audio"]["codec"],
                    str(audio_path),
                    record["audio"]["sha256"],
                    record["audio"]["duration_ms"],
                    record["stt"]["model_name"],
                    record["stt"]["compute_type"],
                    record["stt"]["language"],
                    record["stt"]["context_seconds"],
                    record["stt"]["raw_transcript"],
                    record["stt"]["normalized_transcript"],
                    record["stt"]["injected_text"],
                    record["window"]["app_name"],
                    record["window"]["title_hash"],
                    json.dumps(record.get("parameter_snapshot", {}), sort_keys=True),
                    int(record.get("correction", {}).get("user_flagged_bad", False)),
                ),
            )
            correction = record.get("correction", {})
            connection.execute(
                """
                INSERT INTO corrections (
                    utterance_id, observed, confidence, corrected_text, latency_ms,
                    levenshtein_distance, kind, raw_events_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    utterance_id,
                    int(correction.get("observed", False)),
                    correction.get("confidence", 0.0),
                    correction.get("corrected_text", ""),
                    correction.get("latency_ms", 0),
                    correction.get("levenshtein_distance", 0),
                    correction.get("kind", "none"),
                    json.dumps(correction.get("raw_events", []), sort_keys=True),
                ),
            )
        return True


def build_handler(store: ValidationStore):
    class ValidationHandler(BaseHTTPRequestHandler):
        def do_POST(self) -> None:  # noqa: N802
            if self.path != "/v1/validation/utterances":
                self._send_json(HTTPStatus.NOT_FOUND, {"accepted": False, "error": "not_found"})
                return
            try:
                record, audio_bytes, filename = self._parse_request()
                self._validate_record(record)
            except ValueError as exc:
                self._send_json(HTTPStatus.BAD_REQUEST, {"accepted": False, "error": str(exc)})
                return
            deduplicated = not store.insert_utterance(record, audio_bytes, filename)
            self._send_json(
                HTTPStatus.OK,
                {
                    "accepted": True,
                    "utterance_id": record["utterance_id"],
                    "deduplicated": deduplicated,
                },
            )

        def log_message(self, format, *args) -> None:  # noqa: A003
            return

        def _parse_request(self) -> tuple[dict[str, Any], bytes, str]:
            form = cgi.FieldStorage(
                fp=self.rfile,
                headers=self.headers,
                environ={
                    "REQUEST_METHOD": "POST",
                    "CONTENT_TYPE": self.headers.get("Content-Type", ""),
                },
            )
            metadata_item = form["metadata"] if "metadata" in form else None
            audio_item = form["audio"] if "audio" in form else None
            if metadata_item is None or audio_item is None:
                raise ValueError("missing metadata or audio")
            record = json.loads(metadata_item.value)
            filename = audio_item.filename or "audio.bin"
            audio_bytes = audio_item.file.read()
            return record, audio_bytes, filename

        def _validate_record(self, record: dict[str, Any]) -> None:
            required = (
                "utterance_id",
                "user_id",
                "device_id",
                "created_at",
                "app",
                "audio",
                "stt",
                "window",
            )
            for key in required:
                if key not in record:
                    raise ValueError(f"missing {key}")
            stt_required = ("model_name", "compute_type", "language", "context_seconds", "raw_transcript", "normalized_transcript", "injected_text")
            for key in stt_required:
                if key not in record["stt"]:
                    raise ValueError(f"missing stt.{key}")

        def _send_json(self, status: HTTPStatus, payload: dict[str, Any]) -> None:
            body = json.dumps(payload).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    return ValidationHandler


def validation_server_main() -> None:
    parser = argparse.ArgumentParser(description="Run the WisprTypr validation ingest server")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", default=8765, type=int)
    parser.add_argument("--db", type=Path, default=Path("artifacts/validation/validation.sqlite3"))
    parser.add_argument("--blob-dir", type=Path, default=Path("artifacts/validation/audio"))
    args = parser.parse_args()

    args.db.parent.mkdir(parents=True, exist_ok=True)
    store = ValidationStore(db_path=args.db, blob_dir=args.blob_dir)
    server = ThreadingHTTPServer((args.host, args.port), build_handler(store))
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
