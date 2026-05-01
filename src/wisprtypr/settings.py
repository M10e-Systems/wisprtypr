from __future__ import annotations

import json
import uuid
from dataclasses import asdict
from dataclasses import dataclass
from pathlib import Path


def default_settings_path() -> Path:
    return Path.home() / ".config" / "wisprtypr" / "settings.json"


@dataclass
class ValidationSettings:
    validation_enabled: bool = False
    validation_server_url: str = "http://127.0.0.1:8765"
    validation_retention_days: int = 7
    validation_capture_edit_window_seconds: int = 20
    validation_max_pending_mb: int = 256
    validation_client_id: str = ""
    validation_device_id: str = ""

    @classmethod
    def load(cls, path: Path | None = None) -> ValidationSettings:
        settings_path = path or default_settings_path()
        if not settings_path.exists():
            settings = cls()
            settings.ensure_ids()
            return settings

        raw = json.loads(settings_path.read_text(encoding="utf-8"))
        settings = cls(
            validation_enabled=bool(raw.get("validation_enabled", False)),
            validation_server_url=str(raw.get("validation_server_url", "http://127.0.0.1:8765")),
            validation_retention_days=int(raw.get("validation_retention_days", 7)),
            validation_capture_edit_window_seconds=int(raw.get("validation_capture_edit_window_seconds", 20)),
            validation_max_pending_mb=int(raw.get("validation_max_pending_mb", 256)),
            validation_client_id=str(raw.get("validation_client_id", "")),
            validation_device_id=str(raw.get("validation_device_id", "")),
        )
        settings.ensure_ids()
        return settings

    def ensure_ids(self) -> None:
        if not self.validation_client_id:
            self.validation_client_id = str(uuid.uuid4())
        if not self.validation_device_id:
            self.validation_device_id = str(uuid.uuid4())

    def save(self, path: Path | None = None) -> None:
        settings_path = path or default_settings_path()
        settings_path.parent.mkdir(parents=True, exist_ok=True)
        self.ensure_ids()
        settings_path.write_text(json.dumps(asdict(self), indent=2, sort_keys=True) + "\n", encoding="utf-8")
