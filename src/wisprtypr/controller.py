from __future__ import annotations

from wisprtypr.audio import AudioCapture, TranscriptionWorker, UtteranceDetector
from wisprtypr.normalization import normalize_transcript
from wisprtypr.state import AppState
from wisprtypr.stt import TranscriptUpdate


class DictationController:
    chunk_duration_options = (1, 2, 4, 10)

    def __init__(self, tray, transcriber, injector, validation_manager=None) -> None:
        self._tray = tray
        self._transcriber = transcriber
        self._injector = injector
        self._validation_manager = validation_manager
        self._state = AppState.OFF
        self._chunk_duration_seconds = 4
        self._committed_words: list[str] = []
        self._last_hypothesis_words: list[str] = []
        self._active_validation_utterance_id: str | None = None
        self._worker = TranscriptionWorker(
            transcribe=self._transcriber.transcribe_chunk,
            on_text=self._handle_transcribed_text,
            on_error=self._handle_error,
        )
        self._detector = UtteranceDetector(
            on_utterance=self._worker.submit,
            max_chunk_seconds=self._chunk_duration_seconds,
        )
        self._capture = AudioCapture(on_chunk=self._detector.push, on_error=self._handle_error)
        self._tray.set_chunk_duration_options(
            self.chunk_duration_options,
            selected=self._chunk_duration_seconds,
            on_select=self.set_chunk_duration,
        )
        self._set_state(AppState.OFF)

    @property
    def state(self) -> AppState:
        return self._state

    def toggle(self) -> None:
        if self._state == AppState.LISTENING:
            self.stop()
        else:
            self.start()

    def set_chunk_duration(self, seconds: int) -> None:
        if seconds not in self.chunk_duration_options:
            raise ValueError(f"unsupported chunk duration: {seconds}")
        self._chunk_duration_seconds = seconds
        self._detector.set_max_chunk_seconds(seconds)
        self._tray.set_chunk_duration(seconds)

    def start(self) -> None:
        if self._state == AppState.LISTENING:
            return
        self._reset_live_transcript()
        self._worker.start()
        try:
            self._capture.start()
        except Exception as exc:
            self._handle_error(exc)
            return
        self._set_state(AppState.LISTENING)

    def stop(self) -> None:
        if self._state == AppState.OFF:
            return
        self._set_state(AppState.OFF)
        self._capture.stop()
        self._detector.discard()
        self._worker.stop()
        self._finalize_active_validation_observation()
        self._reset_live_transcript()

    def shutdown(self) -> None:
        self.stop()

    def _handle_transcribed_text(self, update: TranscriptUpdate) -> None:
        if self._state != AppState.LISTENING:
            return
        normalized = normalize_transcript(update.text)
        if not normalized:
            if update.is_final:
                self._reset_live_transcript()
            return

        if self._validation_manager is not None and self._validation_manager.enabled:
            if self._active_validation_utterance_id is None:
                self._active_validation_utterance_id = self._validation_manager.begin_utterance()

        next_text = self._next_commit_text(normalized, is_final=update.is_final)
        if next_text:
            utterance_id = None
            if self._validation_manager is not None and self._validation_manager.enabled:
                utterance_id = self._active_validation_utterance_id
            injection = self._injector.inject_text(next_text)
            if self._validation_manager is not None and utterance_id is not None:
                self._validation_manager.note_injection(utterance_id, full_text=normalized)
        if update.is_final:
            if (
                self._validation_manager is not None
                and self._active_validation_utterance_id is not None
                and update.audio is not None
                and normalized
            ):
                self._validation_manager.complete_utterance(
                    self._active_validation_utterance_id,
                    audio=update.audio,
                    raw_transcript=update.text,
                    normalized_transcript=normalized,
                    injected_text=normalized,
                    chunk_duration_seconds=self._chunk_duration_seconds,
                    transcriber_config=_describe_transcriber_config(self._transcriber),
                    detector_config=self._detector.describe_config(),
                    injection_method=_describe_injection_method(injection) if next_text else "none",
                )
            self._finalize_active_validation_observation()
            self._reset_live_transcript()

    def _handle_error(self, exc: Exception) -> None:
        self._capture.stop()
        self._worker.stop()
        self._finalize_active_validation_observation()
        self._reset_live_transcript()
        self._set_state(AppState.ERROR, str(exc))

    def _finalize_active_validation_observation(self) -> None:
        if self._validation_manager is None:
            return
        if self._active_validation_utterance_id is None:
            return
        self._validation_manager.finalize_observation(self._active_validation_utterance_id)
        self._active_validation_utterance_id = None

    def _set_state(self, state: AppState, error: str | None = None) -> None:
        self._state = state
        self._tray.set_state(state, chunk_duration_seconds=self._chunk_duration_seconds, error=error)

    def _next_commit_text(self, hypothesis: str, is_final: bool) -> str:
        current_words = hypothesis.split()
        if is_final:
            stable_words = current_words
        else:
            stable_words = _common_prefix_words(self._last_hypothesis_words, current_words)
        if len(stable_words) <= len(self._committed_words):
            self._last_hypothesis_words = current_words
            return ""

        had_existing = bool(self._committed_words)
        new_words = stable_words[len(self._committed_words) :]
        self._committed_words = stable_words
        self._last_hypothesis_words = current_words
        return _format_commit_text(new_words, has_existing=had_existing)

    def _reset_live_transcript(self) -> None:
        self._committed_words = []
        self._last_hypothesis_words = []
        self._active_validation_utterance_id = None


def _common_prefix_words(left: list[str], right: list[str]) -> list[str]:
    prefix: list[str] = []
    for left_word, right_word in zip(left, right):
        if left_word != right_word:
            break
        prefix.append(right_word)
    return prefix


def _format_commit_text(words: list[str], has_existing: bool) -> str:
    if not words:
        return ""
    text = " ".join(words)
    if has_existing:
        return f" {text}"
    return text


def _describe_transcriber_config(transcriber) -> dict[str, object]:
    config = getattr(transcriber, "config", None)
    if config is None:
        return {}
    return {
        "model_name": getattr(config, "model_name", None),
        "compute_type": getattr(config, "compute_type", None),
        "language": getattr(config, "language", None),
        "context_seconds": getattr(config, "context_seconds", None),
    }


def _describe_injection_method(injection) -> str:
    return getattr(injection, "method", "none")
