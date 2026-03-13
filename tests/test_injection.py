from types import SimpleNamespace

import pytest

from wisprtypr.injection import TextInjector


def test_inject_text_restores_clipboards(monkeypatch):
    calls = []
    clipboard = {"clipboard": "old clip", "primary": "old primary"}

    def fake_run(cmd, **kwargs):
        calls.append(cmd)
        if cmd[0] == "xsel" and "--output" in cmd:
            selection = "clipboard" if "--clipboard" in cmd else "primary"
            return SimpleNamespace(returncode=0, stdout=clipboard[selection], stderr="")
        if cmd[0] == "xsel" and "--input" in cmd:
            selection = "clipboard" if "--clipboard" in cmd else "primary"
            clipboard[selection] = kwargs["input"]
            return SimpleNamespace(returncode=0, stdout="", stderr="")
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr("wisprtypr.injection.subprocess.run", fake_run)

    TextInjector().inject_text("hello")

    assert clipboard == {"clipboard": "old clip", "primary": "old primary"}
    assert ["xdotool", "key", "--clearmodifiers", "ctrl+v"] in calls


def test_inject_text_falls_back_to_typing(monkeypatch):
    commands = []

    def fake_run(cmd, **kwargs):
        commands.append(cmd)
        if cmd[:2] == ["xdotool", "key"]:
            raise RuntimeError("paste failed")
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr("wisprtypr.injection.subprocess.run", fake_run)

    TextInjector().inject_text("fallback")

    assert ["xdotool", "type", "--clearmodifiers", "--delay", "1", "fallback"] in commands
