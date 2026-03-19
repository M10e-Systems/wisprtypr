from __future__ import annotations

import argparse
import json
import subprocess
import re
import wave
from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np

from wisprtypr.audio import DetectedChunk
from wisprtypr.normalization import normalize_transcript
from wisprtypr.stt import WhisperConfig, WhisperTranscriber


@dataclass(frozen=True)
class AudioEvalCase:
    audio: Path
    expected: str


@dataclass(frozen=True)
class AudioEvalCaseResult:
    audio: str
    expected: str
    predicted: str
    expected_normalized: str
    predicted_normalized: str
    expected_match_text: str
    predicted_match_text: str
    passed: bool
    wer: float


@dataclass(frozen=True)
class AudioEvalSummary:
    total: int
    passed: int
    failed: int
    pass_rate: float
    average_wer: float


@dataclass(frozen=True)
class AudioEvalReport:
    summary: AudioEvalSummary
    cases: list[AudioEvalCaseResult]


_SPACE_RE = re.compile(r"\s+")
_NON_ALNUM_SPACE_RE = re.compile(r"[^a-z0-9\s]")
_DIGIT_WORDS = {
    "0": "zero",
    "1": "one",
    "2": "two",
    "3": "three",
    "4": "four",
    "5": "five",
    "6": "six",
    "7": "seven",
    "8": "eight",
    "9": "nine",
}
_SINGLE_DIGIT_RE = re.compile(r"\b([0-9])\b")


def load_dataset(dataset_path: Path) -> list[AudioEvalCase]:
    cases: list[AudioEvalCase] = []
    base_dir = dataset_path.parent
    with dataset_path.open("r", encoding="utf-8") as handle:
        for line_no, raw_line in enumerate(handle, start=1):
            line = raw_line.strip()
            if not line:
                continue
            data = json.loads(line)
            if not isinstance(data, dict):
                raise ValueError(f"{dataset_path}:{line_no}: expected JSON object")
            if "audio" not in data or "expected" not in data:
                raise ValueError(f"{dataset_path}:{line_no}: each entry must include 'audio' and 'expected'")
            audio_path = Path(str(data["audio"]))
            if not audio_path.is_absolute():
                audio_path = base_dir / audio_path
            cases.append(AudioEvalCase(audio=audio_path, expected=str(data["expected"])))
    if not cases:
        raise ValueError(f"{dataset_path}: dataset is empty")
    return cases


def read_wav_mono_16k(path: Path) -> np.ndarray:
    if not path.exists():
        raise FileNotFoundError(f"audio file not found: {path}")

    with wave.open(str(path), "rb") as wav_file:
        channels = wav_file.getnchannels()
        sample_width = wav_file.getsampwidth()
        sample_rate = wav_file.getframerate()
        frame_count = wav_file.getnframes()
        frames = wav_file.readframes(frame_count)

    if channels != 1:
        raise ValueError(f"{path}: expected mono WAV, got {channels} channels")
    if sample_width != 2:
        raise ValueError(f"{path}: expected 16-bit PCM WAV, got sample width {sample_width}")
    if sample_rate != 16_000:
        raise ValueError(f"{path}: expected 16000 Hz WAV, got {sample_rate} Hz")

    return np.frombuffer(frames, dtype=np.int16).astype("float32") / 32768.0


def word_error_rate(expected: str, predicted: str) -> float:
    expected_words = expected.split()
    predicted_words = predicted.split()
    if not expected_words:
        return 0.0 if not predicted_words else 1.0

    rows = len(expected_words) + 1
    cols = len(predicted_words) + 1
    matrix = [[0] * cols for _ in range(rows)]

    for i in range(rows):
        matrix[i][0] = i
    for j in range(cols):
        matrix[0][j] = j

    for i in range(1, rows):
        for j in range(1, cols):
            cost = 0 if expected_words[i - 1] == predicted_words[j - 1] else 1
            matrix[i][j] = min(
                matrix[i - 1][j] + 1,
                matrix[i][j - 1] + 1,
                matrix[i - 1][j - 1] + cost,
            )

    return matrix[-1][-1] / len(expected_words)


def transcribe_audio_case(transcriber, audio: np.ndarray, chunk_duration_seconds: int) -> str:
    if chunk_duration_seconds <= 0:
        raise ValueError("chunk_duration_seconds must be positive")

    samples_per_chunk = chunk_duration_seconds * 16_000
    if audio.size == 0:
        return ""

    emitted_parts: list[str] = []
    committed_words: list[str] = []
    last_hypothesis_words: list[str] = []
    for start in range(0, len(audio), samples_per_chunk):
        end = min(start + samples_per_chunk, len(audio))
        is_final = end >= len(audio)
        update = transcriber.transcribe_chunk(DetectedChunk(audio=audio[start:end], is_final=is_final))
        normalized = normalize_transcript(update.text)
        if not normalized:
            if is_final:
                committed_words = []
                last_hypothesis_words = []
            continue

        current_words = normalized.split()
        if is_final:
            stable_words = current_words
        else:
            stable_words = _common_prefix_words(last_hypothesis_words, current_words)

        if len(stable_words) > len(committed_words):
            had_existing = bool(committed_words)
            new_words = stable_words[len(committed_words) :]
            emitted_parts.append(_format_commit_text(new_words, has_existing=had_existing))
            committed_words = stable_words
        last_hypothesis_words = current_words

        if is_final:
            committed_words = []
            last_hypothesis_words = []

    return "".join(emitted_parts).strip()


def canonicalize_for_match(text: str) -> str:
    normalized = normalize_transcript(text).lower()
    normalized = _SINGLE_DIGIT_RE.sub(lambda m: _DIGIT_WORDS[m.group(1)], normalized)
    normalized = _NON_ALNUM_SPACE_RE.sub(" ", normalized)
    return _SPACE_RE.sub(" ", normalized).strip()


def evaluate_cases(cases: list[AudioEvalCase], transcriber, chunk_duration_seconds: int) -> AudioEvalReport:
    case_results: list[AudioEvalCaseResult] = []
    for case in cases:
        audio = read_wav_mono_16k(case.audio)
        predicted = transcribe_audio_case(transcriber, audio=audio, chunk_duration_seconds=chunk_duration_seconds)
        expected_normalized = normalize_transcript(case.expected)
        predicted_normalized = normalize_transcript(predicted)
        expected_match_text = canonicalize_for_match(expected_normalized)
        predicted_match_text = canonicalize_for_match(predicted_normalized)
        passed = expected_match_text == predicted_match_text
        wer = word_error_rate(expected_match_text, predicted_match_text)
        case_results.append(
            AudioEvalCaseResult(
                audio=str(case.audio),
                expected=case.expected,
                predicted=predicted,
                expected_normalized=expected_normalized,
                predicted_normalized=predicted_normalized,
                expected_match_text=expected_match_text,
                predicted_match_text=predicted_match_text,
                passed=passed,
                wer=wer,
            )
        )

    passed_count = sum(1 for result in case_results if result.passed)
    total = len(case_results)
    failed = total - passed_count
    average_wer = sum(result.wer for result in case_results) / total
    summary = AudioEvalSummary(
        total=total,
        passed=passed_count,
        failed=failed,
        pass_rate=passed_count / total,
        average_wer=average_wer,
    )
    return AudioEvalReport(summary=summary, cases=case_results)


def run_audio_eval(
    dataset: Path,
    model_name: str,
    compute_type: str,
    language: str,
    context_seconds: int,
    chunk_duration_seconds: int,
) -> AudioEvalReport:
    cases = load_dataset(dataset)
    transcriber = WhisperTranscriber(
        WhisperConfig(
            model_name=model_name,
            compute_type=compute_type,
            language=language,
            context_seconds=context_seconds,
        )
    )
    return evaluate_cases(cases, transcriber=transcriber, chunk_duration_seconds=chunk_duration_seconds)


def print_report(report: AudioEvalReport) -> None:
    print(
        "Summary: "
        f"{report.summary.passed}/{report.summary.total} passed, "
        f"failed={report.summary.failed}, "
        f"pass_rate={report.summary.pass_rate:.2%}, "
        f"avg_wer={report.summary.average_wer:.4f}"
    )
    for result in report.cases:
        status = "PASS" if result.passed else "FAIL"
        print(
            f"[{status}] {result.audio} | "
            f"expected='{result.expected_normalized}' | "
            f"predicted='{result.predicted_normalized}' | "
            f"expected_match='{result.expected_match_text}' | "
            f"predicted_match='{result.predicted_match_text}' | "
            f"wer={result.wer:.4f}"
        )


def write_report(report: AudioEvalReport, path: Path) -> None:
    payload = {
        "summary": asdict(report.summary),
        "cases": [asdict(result) for result in report.cases],
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def audio_eval_main() -> None:
    parser = argparse.ArgumentParser(description="Run real-audio WisprTypr transcript evaluation")
    parser.add_argument("--dataset", required=True, type=Path, help="JSONL file with {audio, expected} per line")
    parser.add_argument("--model", default="small.en", help="Whisper model name")
    parser.add_argument("--compute-type", default="auto", help="faster-whisper compute type")
    parser.add_argument("--language", default="en", help="Whisper language code")
    parser.add_argument(
        "--context-seconds",
        type=int,
        default=WhisperConfig().context_seconds,
        help="rolling context seconds",
    )
    parser.add_argument("--chunk-seconds", type=int, default=4, help="chunk duration in seconds")
    parser.add_argument("--report-json", type=Path, help="optional path to write JSON report")
    args = parser.parse_args()

    report = run_audio_eval(
        dataset=args.dataset,
        model_name=args.model,
        compute_type=args.compute_type,
        language=args.language,
        context_seconds=args.context_seconds,
        chunk_duration_seconds=args.chunk_seconds,
    )
    print_report(report)
    if args.report_json:
        write_report(report, args.report_json)
    if report.summary.failed:
        raise SystemExit(1)


def audio_fix_loop_main() -> None:
    parser = argparse.ArgumentParser(description="Run test + audio eval loop until green or max iterations")
    parser.add_argument("--dataset", required=True, type=Path, help="JSONL file with {audio, expected} per line")
    parser.add_argument("--max-iterations", type=int, default=5)
    parser.add_argument("--model", default="small.en")
    parser.add_argument("--compute-type", default="auto")
    parser.add_argument("--language", default="en")
    parser.add_argument("--context-seconds", type=int, default=WhisperConfig().context_seconds)
    parser.add_argument("--chunk-seconds", type=int, default=4)
    parser.add_argument("--report-dir", type=Path, default=Path("artifacts/audio-loop"))
    args = parser.parse_args()

    args.report_dir.mkdir(parents=True, exist_ok=True)

    for iteration in range(1, args.max_iterations + 1):
        print(f"Iteration {iteration}/{args.max_iterations}")
        print("Running make test...")
        test_result = subprocess.run(["make", "test"], check=False)
        if test_result.returncode != 0:
            print("Loop stopped: make test failed")
            raise SystemExit(test_result.returncode)

        report = run_audio_eval(
            dataset=args.dataset,
            model_name=args.model,
            compute_type=args.compute_type,
            language=args.language,
            context_seconds=args.context_seconds,
            chunk_duration_seconds=args.chunk_seconds,
        )
        report_path = args.report_dir / f"iteration-{iteration:02d}.json"
        write_report(report, report_path)
        print_report(report)
        print(f"Saved report to {report_path}")

        if report.summary.failed == 0:
            print("Loop complete: all audio cases passed")
            return

        print("Loop requires code changes before next iteration.")
        if iteration < args.max_iterations:
            print("Re-run after applying fixes.")

    raise SystemExit(1)


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
