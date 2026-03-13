import os

from wisprtypr.runtime import configure_process_metadata


def test_configure_process_metadata_sets_pulse_properties(monkeypatch):
    monkeypatch.delenv("PULSE_PROP_application.name", raising=False)
    monkeypatch.delenv("PULSE_PROP_application.process.binary", raising=False)

    configure_process_metadata("wisprtypr")

    assert os.environ["PULSE_PROP_application.name"] == "wisprtypr"
    assert os.environ["PULSE_PROP_application.process.binary"] == "wisprtypr"
