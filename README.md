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
