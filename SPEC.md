# WisprTypr Specification

## Summary

WisprTypr is a local-first speech-to-text tray app for Ubuntu on X11 with Xfce4. It is intended to behave like a simple "Wispr Flow" style dictation tool: click the tray icon to turn dictation on or off, and while it is on, recognized text is inserted at the current cursor position in the active application without interrupting normal keyboard or mouse use.

## Product Requirements

### Core behavior

- The app must present a tray/taskbar icon in Xfce4.
- Clicking the tray icon must toggle dictation On and Off.
- Right-clicking the tray icon must open a minimal menu that includes chunk-length selection.
- Dictation remains active until explicitly toggled Off.
- While active, speech-to-text output must be inserted at the current caret position in the focused application.
- Keyboard input and mouse clicks must remain usable while dictation is active.
- The user should not need to manually start and stop capture per utterance; dictation is continuous while On.

### Speech recognition

- Speech recognition must run locally, without requiring a cloud API or account.
- Output quality should target modern smartphone-style speech-to-text quality.
- v1 is English-first.
- Only finalized utterances should be inserted; partial text should not be emitted into the target application.
- Audio input should be auto-normalized so different microphone levels do not require manual tuning.
- For low chunk durations, the app should use rolling utterance audio context and delay text insertion until words are stable across consecutive decodes or the utterance ends.
- Cleanup should correct obvious transcript formatting issues such as glued punctuation, missing spaces, and camel-cased word merges before text is inserted.
- The app should use the system default microphone by default.

### Desktop and platform scope

- v1 targets Ubuntu on X11 with Xfce4.
- Wayland support is out of scope for v1.
- Global text insertion should work across normal X11 applications using the active focused window.
- The PulseAudio/PipeWire client name shown in volume control should be `wisprtypr`, not a generic Python process name.

### Configuration and UX

- Configuration should be kept to a minimum.
- The user must be able to select recording chunk length values of `1s`, `2s`, `4s`, or `10s` from the tray icon menu.
- v1 should not require a settings window or a complex configuration flow.
- Manual launch must be supported.
- Optional start-on-login support must be available through an autostart entry.
- The tray icon should visibly communicate at least Off, Listening, and Error states.
- A minimal quit path should be available from the tray.

## Non-Goals for v1

- Wayland support.
- Multi-language auto-detection.
- Push-to-talk or a required hotkey workflow.
- Device picker UI or advanced microphone configuration.
- Cloud transcription backends.
- Disabling or intercepting normal keyboard and mouse interaction while dictation is active.

## Operational Requirements

- The application is implemented as a Python project managed with Poetry.
- The repository must maintain a `Makefile`.
- The `Makefile` must include a `test` target that resolves dependencies and runs the full automated test suite.
- `make test` is the canonical command for running the automated test suite in this repository.
- When validating changes, contributors and agents should run `make test` first rather than invoking `pytest` or other lower-level test commands directly, unless `make test` itself is broken or the task explicitly requires a narrower check.
- Automated tests should cover the toggle lifecycle, transcript normalization, text injection behavior, and process metadata relevant to desktop integration.

## Accepted v1 Implementation Choices

- Local transcription uses Whisper-class recognition.
- Text insertion may use clipboard-preserving paste with fallback typing for X11 compatibility.
- Tray integration may rely on GTK/X11-compatible status icon behavior suitable for Xfce4.
- System GTK bindings may be consumed from the host Ubuntu installation rather than being fully vendored in the Poetry environment.
