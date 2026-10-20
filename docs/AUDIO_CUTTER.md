# Haseeb Audio Cutter — Windows Desktop

Independent app: `audio-cutter`, version `1.0.0`. Separate from Haseeb Control and AI Automation Studio; does not touch VPS_1.

## Features

- Browse MP3/WAV/M4A/AAC/FLAC/OGG/OPUS/WMA/AIFF.
- Display waveform, drag start/end handles, or enter timestamps precisely as HH:MM:SS.mmm.
- Preview the first 30 seconds of a cut, with Stop.
- Export MP3 (192 kbps), WAV, M4A, FLAC or OGG with optional soft-edge fades.
- Never modify originals or overwrite existing outputs.

## Release system

Haseeb GitHub Actions Windows Build installs pinned `imageio-ffmpeg==0.6.0` on the GitHub runner and packages FFmpeg for Audio Cutter releases only. The binary and its license description are part of the ZIP, never committed to Git source. Existing Windows Python 3.11 is sufficient; no extra FFmpeg installation is required on the user's PC. The self-test creates a temporary sine-wave WAV, trims to MP3 using FFmpeg and verifies duration. A failing self-test prevents release activation.

The already configured `HaseebDesktopSync` hourly Windows task fetches only successful exact-main CI artifacts, verifies SHA-256, tests and activates each app. PC must be powered on and connected. An interactive GUI cannot open by itself from the scheduled background sync.

## Launch

After the PC hourly sync installs the app, run this once from Windows PowerShell:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "$env:LOCALAPPDATA\Haseeb\repo\ops\windows\Launch-Haseeb.ps1" -AppId audio-cutter
```

Subsequent versions update automatically through GitHub CI and hourly sync. Rollback is supported once two distinct releases are installed. No Windows remote SSH server is required.
