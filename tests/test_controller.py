from dataclasses import dataclass

from wisprtypr.controller import DictationController
from wisprtypr.state import AppState


@dataclass(frozen=True)
class FakeTranscriptUpdate:
    text: str
    is_final: bool
    audio: object | None = None


class FakeTray:
    def __init__(self):
        self.states = []
        self.chunk_durations = []
        self.options = None

    def set_state(self, state, chunk_duration_seconds, error=None):
        self.states.append((state, chunk_duration_seconds, error))

    def set_chunk_duration_options(self, options, selected, on_select):
        self.options = (options, selected, on_select)

    def set_chunk_duration(self, seconds):
        self.chunk_durations.append(seconds)


class FakeTranscriber:
    def transcribe_chunk(self, chunk):
        return FakeTranscriptUpdate(text="hello world", is_final=chunk.is_final)


class FakeInjector:
    def __init__(self):
        self.injected = []

    def inject_text(self, text):
        self.injected.append(text)


class FakeCapture:
    def __init__(self, on_chunk, on_error=None):
        self.started = 0
        self.stopped = 0
        self.on_chunk = on_chunk
        self.on_error = on_error

    def start(self):
        self.started += 1

    def stop(self):
        self.stopped += 1


class FakeWorker:
    def __init__(self, transcribe, on_text, on_error=None):
        self.started = 0
        self.stopped = 0
        self.on_text = on_text

    def start(self):
        self.started += 1

    def stop(self):
        self.stopped += 1

    def submit(self, audio):
        self.on_text(FakeTranscriptUpdate(text="hello world", is_final=audio.is_final))


class FakeDetector:
    def __init__(self, on_utterance, max_chunk_seconds):
        self.on_utterance = on_utterance
        self.flushed = 0
        self.discarded = 0
        self.max_chunk_seconds = max_chunk_seconds

    def push(self, chunk):
        self.on_utterance(chunk)

    def flush(self):
        self.flushed += 1

    def discard(self):
        self.discarded += 1

    def set_max_chunk_seconds(self, seconds):
        self.max_chunk_seconds = seconds


def test_controller_toggle_lifecycle(monkeypatch):
    monkeypatch.setattr("wisprtypr.controller.AudioCapture", FakeCapture)
    monkeypatch.setattr("wisprtypr.controller.TranscriptionWorker", FakeWorker)
    monkeypatch.setattr("wisprtypr.controller.UtteranceDetector", FakeDetector)
    tray = FakeTray()
    injector = FakeInjector()

    controller = DictationController(tray=tray, transcriber=FakeTranscriber(), injector=injector)

    controller.start()
    assert controller.state == AppState.LISTENING

    controller.stop()
    assert controller.state == AppState.OFF
    assert tray.states[0][0] == AppState.OFF
    assert tray.states[1][0] == AppState.LISTENING
    assert tray.states[-1][0] == AppState.OFF


def test_controller_injects_only_while_listening(monkeypatch):
    monkeypatch.setattr("wisprtypr.controller.AudioCapture", FakeCapture)
    monkeypatch.setattr("wisprtypr.controller.TranscriptionWorker", FakeWorker)
    monkeypatch.setattr("wisprtypr.controller.UtteranceDetector", FakeDetector)
    tray = FakeTray()
    injector = FakeInjector()
    controller = DictationController(tray=tray, transcriber=FakeTranscriber(), injector=injector)

    controller._handle_transcribed_text(FakeTranscriptUpdate(text="hello world", is_final=False))
    assert injector.injected == []

    controller.start()
    controller._handle_transcribed_text(FakeTranscriptUpdate(text="hello world", is_final=False))
    assert injector.injected == []
    controller._handle_transcribed_text(FakeTranscriptUpdate(text="hello world again", is_final=False))
    assert injector.injected == ["Hello world"]
    controller._handle_transcribed_text(FakeTranscriptUpdate(text="hello world again today", is_final=True))
    assert injector.injected == ["Hello world", " again today"]


def test_controller_updates_chunk_duration(monkeypatch):
    monkeypatch.setattr("wisprtypr.controller.AudioCapture", FakeCapture)
    monkeypatch.setattr("wisprtypr.controller.TranscriptionWorker", FakeWorker)
    monkeypatch.setattr("wisprtypr.controller.UtteranceDetector", FakeDetector)
    tray = FakeTray()
    controller = DictationController(tray=tray, transcriber=FakeTranscriber(), injector=FakeInjector())

    controller.set_chunk_duration(10)

    assert controller._detector.max_chunk_seconds == 10
    assert tray.chunk_durations == [10]
    assert tray.options[1] == 4
