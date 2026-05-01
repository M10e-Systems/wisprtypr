from wisprtypr.settings import ValidationSettings


def test_validation_settings_round_trip(tmp_path):
    path = tmp_path / "settings.json"

    settings = ValidationSettings(
        validation_enabled=True,
        validation_server_url="http://example.test:9999",
        validation_upload_token="secret-token",
    )
    settings.save(path)

    loaded = ValidationSettings.load(path)

    assert loaded.validation_enabled is True
    assert loaded.validation_server_url == "http://example.test:9999"
    assert loaded.validation_client_id
    assert loaded.validation_device_id
    assert loaded.validation_upload_token == "secret-token"


def test_validation_settings_missing_file_uses_defaults(tmp_path):
    loaded = ValidationSettings.load(tmp_path / "missing.json")

    assert loaded.validation_enabled is False
    assert loaded.validation_server_url == "http://127.0.0.1:8765"
    assert loaded.validation_capture_edit_window_seconds == 20
    assert loaded.validation_upload_token == ""


def test_validation_settings_security_guard():
    assert ValidationSettings(validation_server_url="https://example.test").has_secure_validation_endpoint() is True
    assert ValidationSettings(validation_server_url="http://localhost:8765").has_secure_validation_endpoint() is True
    assert ValidationSettings(validation_server_url="http://127.0.0.1:8765").has_secure_validation_endpoint() is True
    assert ValidationSettings(validation_server_url="http://example.test").has_secure_validation_endpoint() is False
