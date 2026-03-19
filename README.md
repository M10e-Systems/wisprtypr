# WisprTypr

WisprTypr is a local-first tray dictation app for Ubuntu/Xfce on X11. Click the tray icon to toggle dictation on and off. While active, finalized speech segments are inserted at the current caret and normal keyboard or mouse input continues to work.

## Requirements

System packages:

- `python3-gi`
- `gir1.2-gtk-3.0`
- `xdotool`
- `xsel`
- `portaudio19-dev`
- `ffmpeg`

Python dependencies are managed with Poetry.

## Run

```bash
poetry install
poetry run wisprtypr
```

## Autostart

```bash
poetry run wisprtypr-install-autostart
```

This installs a desktop entry at `~/.config/autostart/wisprtypr.desktop`.

## Real-Audio Regression Loop

Bootstrap a starter dataset of freely-available audio samples:

```bash
make audio-dataset-bootstrap
```

Prepare a JSONL dataset where each line has `audio` and `expected`:

```json
{"audio":"./clips/hello.wav","expected":"hello world"}
{"audio":"./clips/status.wav","expected":"what is the status today"}
```

Constraints:

- WAV only
- mono
- 16-bit PCM
- 16 kHz

Run one evaluation pass:

```bash
make audio-eval DATASET=path/to/dataset.jsonl
```

With the bootstrapped starter set:

```bash
make audio-eval DATASET=tests/fixtures/audio/free-samples/dataset.jsonl
```

Run iterative test + audio evaluation loop:

```bash
make audio-loop DATASET=path/to/dataset.jsonl MAX_ITERATIONS=5
```

The loop writes per-iteration reports under `artifacts/audio-loop/` and fails if any case does not match expected normalized text.
