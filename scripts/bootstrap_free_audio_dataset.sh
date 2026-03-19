#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DATASET_DIR="$ROOT_DIR/tests/fixtures/audio/free-samples"
CLIPS_DIR="$DATASET_DIR/clips"
TMP_DIR="$DATASET_DIR/.tmp"

mkdir -p "$CLIPS_DIR" "$TMP_DIR"

JFK_FLAC_URL="https://raw.githubusercontent.com/openai/whisper/main/tests/jfk.flac"
ENGLISH_WAV_URL="https://raw.githubusercontent.com/Uberi/speech_recognition/master/tests/english.wav"

curl -L "$JFK_FLAC_URL" -o "$TMP_DIR/jfk.flac"
curl -L "$ENGLISH_WAV_URL" -o "$TMP_DIR/english.wav"

ffmpeg -y -loglevel error -i "$TMP_DIR/jfk.flac" -ac 1 -ar 16000 -sample_fmt s16 "$CLIPS_DIR/jfk.wav"
ffmpeg -y -loglevel error -i "$TMP_DIR/english.wav" -ac 1 -ar 16000 -sample_fmt s16 "$CLIPS_DIR/one-two-three.wav"

cat > "$DATASET_DIR/dataset.jsonl" <<'EOF'
{"audio":"clips/jfk.wav","expected":"And so my fellow Americans, ask not what your country can do for you, ask what you can do for your country."}
{"audio":"clips/one-two-three.wav","expected":"one two three"}
EOF

cat > "$DATASET_DIR/SOURCES.md" <<'EOF'
# Free Audio Sample Sources

This starter dataset uses freely-available speech samples and expected transcripts from upstream open-source test fixtures.

## 1) JFK sample

- Audio source: `https://raw.githubusercontent.com/openai/whisper/main/tests/jfk.flac`
- Upstream repo: `https://github.com/openai/whisper`
- Upstream license: MIT
- Expected transcript basis: `https://raw.githubusercontent.com/SYSTRAN/faster-whisper/master/tests/test_transcribe.py`

## 2) One-two-three sample

- Audio source: `https://raw.githubusercontent.com/Uberi/speech_recognition/master/tests/english.wav`
- Upstream repo: `https://github.com/Uberi/speech_recognition`
- Upstream license: BSD-3-Clause
- Expected transcript basis: `https://raw.githubusercontent.com/Uberi/speech_recognition/master/tests/test_recognition.py`
EOF

rm -rf "$TMP_DIR"

echo "Bootstrapped dataset at: $DATASET_DIR/dataset.jsonl"
