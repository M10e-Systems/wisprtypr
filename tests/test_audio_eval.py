from __future__ import annotations

import json
import wave
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pytest

from wisprtypr.audio_eval import (
    evaluate_cases,
    load_dataset,
    read_wav_mono_16k,
    transcribe_audio_case,
    word_error_rate,
)
from wisprtypr.audio_eval import AudioEvalCase


@dataclass(frozen=True)
class FakeUpdate:
    text: str
    is_final: bool


class FakeTranscriber:
    def __init__(self, outputs: list[str]):
        self._outputs = outputs
        self._index = 0

    def transcribe_chunk(self, chunk):
        text = self._outputs[min(self._index, len(self._outputs) - 1)]
        self._index += 1
        return FakeUpdate(text=text, is_final=chunk.is_final)


def _write_wav(path: Path, samples: np.ndarray, sample_rate: int = 16_000, channels: int = 1) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as wav_file:
        wav_file.setnchannels(channels)
        wav_file.setsampwidth(2)
        wav_file.setframerate(sample_rate)
        pcm = np.clip(samples, -1.0, 1.0)
        wav_file.writeframes((pcm * 32767).astype(np.int16).tobytes())


def test_load_dataset_resolves_relative_paths(tmp_path: Path):
    audio_file = tmp_path / "sample.wav"
    _write_wav(audio_file, np.zeros(160, dtype=np.float32))
    dataset = tmp_path / "dataset.jsonl"
    dataset.write_text(json.dumps({"audio": "sample.wav", "expected": "hello"}) + "\n", encoding="utf-8")

    cases = load_dataset(dataset)

    assert len(cases) == 1
    assert cases[0].audio == audio_file
    assert cases[0].expected == "hello"


def test_read_wav_mono_16k_validates_format(tmp_path: Path):
    bad_file = tmp_path / "stereo.wav"
    _write_wav(bad_file, np.zeros(160, dtype=np.float32), channels=2)

    with pytest.raises(ValueError, match="expected mono WAV"):
        read_wav_mono_16k(bad_file)


def test_transcribe_audio_case_chunks_and_uses_final_text():
    transcriber = FakeTranscriber(["hello", "hello world"])
    audio = np.zeros(32_100, dtype=np.float32)

    text = transcribe_audio_case(transcriber, audio=audio, chunk_duration_seconds=1)

    assert text == "hello world"


def test_evaluate_cases_uses_normalized_exact_match(tmp_path: Path):
    audio_file = tmp_path / "case.wav"
    _write_wav(audio_file, np.zeros(1600, dtype=np.float32))
    transcriber = FakeTranscriber(["hello world"])

    report = evaluate_cases(
        [AudioEvalCase(audio=audio_file, expected="  Hello   world  ")],
        transcriber=transcriber,
        chunk_duration_seconds=1,
    )

    assert report.summary.total == 1
    assert report.summary.passed == 1
    assert report.summary.failed == 0
    assert report.cases[0].passed is True


def test_word_error_rate_smoke():
    assert word_error_rate("hello world", "hello brave world") == pytest.approx(0.5)
