from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np

from wisprtypr.audio import DetectedChunk


@dataclass
class WhisperConfig:
    model_name: str = "small.en"
    compute_type: str = "auto"
    language: str = "en"
    context_seconds: int = 12


@dataclass(frozen=True)
class TranscriptUpdate:
    text: str
    is_final: bool
    audio: np.ndarray | None = None


class WhisperTranscriber:
    def __init__(self, config: WhisperConfig | None = None) -> None:
        self.config = config or WhisperConfig()
        self._model = None
        self._active_audio = np.array([], dtype="float32")

    def transcribe(self, audio: np.ndarray) -> str:
        if audio.size == 0:
            return ""
        model = self._get_model()
        segments, _info = model.transcribe(
            audio.astype("float32"),
            language=self.config.language,
            vad_filter=True,
            beam_size=5,
            best_of=5,
            condition_on_previous_text=False,
        )
        return " ".join(segment.text.strip() for segment in segments if segment.text.strip())

    def transcribe_chunk(self, chunk: DetectedChunk) -> TranscriptUpdate:
        self._active_audio = np.concatenate((self._active_audio, chunk.audio.astype("float32")))
        max_samples = self.config.context_seconds * 16_000
        if self._active_audio.size > max_samples:
            self._active_audio = self._active_audio[-max_samples:]
        captured_audio = np.copy(self._active_audio)
        text = self.transcribe(self._active_audio)
        result = TranscriptUpdate(text=text, is_final=chunk.is_final, audio=captured_audio)
        if chunk.is_final:
            self._active_audio = np.array([], dtype="float32")
        return result

    def _get_model(self):
        if self._model is None:
            from faster_whisper import WhisperModel

            cache_dir = Path.home() / ".cache" / "wisprtypr"
            cache_dir.mkdir(parents=True, exist_ok=True)
            self._model = WhisperModel(
                self.config.model_name,
                compute_type=self.config.compute_type,
                download_root=str(cache_dir),
            )
        return self._model
