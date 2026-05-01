from __future__ import annotations

import queue
import threading
import time
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass

import numpy as np


AudioCallback = Callable[[np.ndarray], None]
ErrorCallback = Callable[[Exception], None]


@dataclass(frozen=True)
class DetectedChunk:
    audio: np.ndarray
    is_final: bool


class AudioCapture:
    sample_rate = 16_000
    channels = 1
    blocksize = 1_600

    def __init__(self, on_chunk: AudioCallback, on_error: ErrorCallback | None = None) -> None:
        self._on_chunk = on_chunk
        self._on_error = on_error
        self._stream = None

    def start(self) -> None:
        import sounddevice as sd

        self._stream = sd.InputStream(
            samplerate=self.sample_rate,
            channels=self.channels,
            dtype="float32",
            blocksize=self.blocksize,
            callback=self._callback,
        )
        self._stream.start()

    def stop(self) -> None:
        if self._stream is None:
            return
        self._stream.stop()
        self._stream.close()
        self._stream = None

    def _callback(self, indata, frames, time_info, status) -> None:  # pragma: no cover
        try:
            if status:
                raise RuntimeError(str(status))
            audio = np.squeeze(np.copy(indata))
            self._on_chunk(normalize_audio(audio))
        except Exception as exc:
            if self._on_error is not None:
                self._on_error(exc)


def normalize_audio(audio: np.ndarray, target_rms: float = 0.12) -> np.ndarray:
    if audio.size == 0:
        return audio
    rms = float(np.sqrt(np.mean(np.square(audio))))
    if rms < 1e-4:
        return audio
    gain = min(target_rms / rms, 8.0)
    return np.clip(audio * gain, -1.0, 1.0)


class UtteranceDetector:
    def __init__(
        self,
        on_utterance: AudioCallback,
        silence_seconds: float = 0.75,
        min_speech_seconds: float = 0.25,
        energy_threshold: float = 0.015,
        sample_rate: int = 16_000,
        max_chunk_seconds: int = 4,
    ) -> None:
        self._on_utterance = on_utterance
        self._silence_seconds = silence_seconds
        self._min_speech_samples = int(min_speech_seconds * sample_rate)
        self._energy_threshold = energy_threshold
        self._sample_rate = sample_rate
        self._max_chunk_samples = int(max_chunk_seconds * sample_rate)
        self._chunks: list[np.ndarray] = []
        self._speech_samples = 0
        self._silence_samples = 0

    def push(self, chunk: np.ndarray) -> None:
        if chunk.size == 0:
            return
        energy = float(np.sqrt(np.mean(np.square(chunk))))
        self._chunks.append(chunk)
        if energy >= self._energy_threshold:
            self._speech_samples += len(chunk)
            self._silence_samples = 0
            if self._speech_samples >= self._min_speech_samples and self._buffered_samples >= self._max_chunk_samples:
                utterance = np.concatenate(self._chunks)
                self._reset()
                self._on_utterance(DetectedChunk(audio=utterance, is_final=False))
            return

        self._silence_samples += len(chunk)
        if self._speech_samples >= self._min_speech_samples and self._silence_samples >= int(
            self._silence_seconds * self._sample_rate
        ):
            utterance = np.concatenate(self._chunks)
            self._reset()
            self._on_utterance(DetectedChunk(audio=utterance, is_final=True))
            return

        if self._speech_samples == 0 and self._silence_samples >= int(2 * self._sample_rate):
            self._reset()

    def flush(self) -> None:
        if self._speech_samples >= self._min_speech_samples and self._chunks:
            self._on_utterance(DetectedChunk(audio=np.concatenate(self._chunks), is_final=True))
        self._reset()

    def discard(self) -> None:
        self._reset()

    def set_max_chunk_seconds(self, seconds: int) -> None:
        self._max_chunk_samples = int(seconds * self._sample_rate)

    def describe_config(self) -> dict[str, float | int]:
        return {
            "silence_seconds": self._silence_seconds,
            "min_speech_seconds": self._min_speech_samples / self._sample_rate,
            "energy_threshold": self._energy_threshold,
            "sample_rate": self._sample_rate,
            "max_chunk_seconds": self._max_chunk_samples / self._sample_rate,
        }

    @property
    def _buffered_samples(self) -> int:
        return sum(len(chunk) for chunk in self._chunks)

    def _reset(self) -> None:
        self._chunks = []
        self._speech_samples = 0
        self._silence_samples = 0


class TranscriptionWorker:
    def __init__(
        self,
        transcribe: Callable[[DetectedChunk], object],
        on_text: Callable[[object], None],
        on_error: ErrorCallback | None = None,
    ) -> None:
        self._transcribe = transcribe
        self._on_text = on_text
        self._on_error = on_error
        self._pending: deque[DetectedChunk] = deque()
        self._condition = threading.Condition()
        self._stopping = False
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stopping = False
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def submit(self, chunk: DetectedChunk) -> None:
        with self._condition:
            self._pending.append(chunk)
            self._condition.notify()

    def stop(self) -> None:
        with self._condition:
            self._stopping = True
            self._condition.notify_all()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2)
        self._thread = None

    def _run(self) -> None:
        while True:
            with self._condition:
                while not self._pending and not self._stopping:
                    self._condition.wait()
                if self._stopping and not self._pending:
                    return
                item = self._pending.popleft()
                while self._pending and not item.is_final:
                    next_item = self._pending[0]
                    item = merge_detected_chunks(item, self._pending.popleft())
                    if next_item.is_final:
                        break
            try:
                result = self._transcribe(item)
                if getattr(result, "text", ""):
                    self._on_text(result)
            except Exception as exc:  # pragma: no cover
                if self._on_error is not None:
                    self._on_error(exc)
                time.sleep(0.1)


def merge_detected_chunks(left: DetectedChunk, right: DetectedChunk) -> DetectedChunk:
    return DetectedChunk(
        audio=np.concatenate((left.audio, right.audio)),
        is_final=left.is_final or right.is_final,
    )
