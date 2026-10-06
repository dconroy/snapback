# Snapback

**Instant replay for anything with HDMI.** Website: [dconroy.github.io/snapback](https://dconroy.github.io/snapback/)

Snapback turns a Raspberry Pi 5 with an Elgato Cam Link 4K into a tiny HDMI capture box for the home network. Open it on an iPhone and there are two buttons:

1. **Grab Screenshot**: saves a 1920x1080 JPEG of the live HDMI input.
2. **Download Last 30 Seconds**: saves the previous ~30 seconds (H.264 + AAC MP4).

No accounts, cloud, telemetry, database, Docker, or JS build tooling. Python + FastAPI + ffmpeg + one HTML file.

The project's code name was QuickCap, and the code still uses it: the Python package is `quickcap`, settings are `QUICKCAP_*` variables, and files live in `~/quickcap-runtime`. The GitHub repo is `dconroy/snapback` (renamed from `dconroy/quickcap`).

> **Disclaimer:** Snapback is a personal home project provided **as-is, without warranty of any kind**. The authors are not liable for lost recordings, data loss, hardware damage, or anything else arising from its use. You are responsible for what you capture, including copyright, terms of service, and recording/consent laws. It has no login, so run it only on a trusted network and never expose it to the internet. Not affiliated with Raspberry Pi, Elgato, or Apple. Read the full [DISCLAIMER.md](DISCLAIMER.md).

## Run It On The Pi

```sh
ssh pi@quikcap.local
cd ~/quickcap
git pull

python3 -m venv .venv
.venv/bin/pip install -r requirements.txt

# The Phase 1 preview server must NOT be running; only one process can read /dev/video0.
pgrep -af quickcap_preview_server.py

.venv/bin/python -m quickcap serve          # listens on 0.0.0.0:8000
```

Then open `http://quikcap.local:8000/` on the phone. Stop with Ctrl-C (this also stops the ffmpeg buffer).

The rolling buffer starts as soon as the app starts. Give it ~30 seconds before the first replay has full length.

A systemd unit template lives in [`deploy/quickcap.service`](deploy/quickcap.service). It is not installed; see [docs/pi-startup.md](docs/pi-startup.md).

## Configuration

Environment variables (all optional):

| Variable | Default |
| --- | --- |
| `QUICKCAP_RUNTIME_DIR` | `~/quickcap-runtime` |
| `QUICKCAP_MEDIA_DIR` | `$QUICKCAP_RUNTIME_DIR/captures` |
| `QUICKCAP_BUFFER_DIR` | `$QUICKCAP_RUNTIME_DIR/buffer` |
| `QUICKCAP_VIDEO_DEVICE` | `/dev/video0` |
| `QUICKCAP_AUDIO_DEVICE` | `hw:CARD=C4K,DEV=0` |
| `QUICKCAP_X264_PRESET` | `ultrafast` |
| `QUICKCAP_START_BUFFER` | `1` (set `0` to not start the buffer, e.g. for UI work) |

Captured media is never stored in the repository and is gitignored.

## HTTP API

- `GET /`: the web page.
- `GET /api/status`: device detected, buffer state, buffered seconds, latest screenshot/replay, free disk, last error.
- `POST /api/screenshot`: saves a JPEG and returns `{filename, url, size_bytes, ...}`.
- `POST /api/replay`: saves the last ~30 s and returns `{filename, url, approx_seconds, ...}`.
- `GET /media/{filename}`: serves a file from the media directory only (strict filename check, no subpaths).

Errors are JSON `{"detail": "..."}`: `409` if the capture device is busy, `503` if capture failed or the buffer has no footage.

## Development

```sh
uv venv --python 3.13 .venv          # or: python3 -m venv .venv
uv pip install --python .venv/bin/python -r requirements-dev.txt
.venv/bin/python -m pytest -q
QUICKCAP_START_BUFFER=0 .venv/bin/python -m quickcap serve --port 8000   # UI without hardware
```

Unit tests mock ffmpeg and need no hardware. Hardware checks are in [docs/manual-verification.md](docs/manual-verification.md).

## Website

The marketing page is plain HTML in [`site/`](site/). It's published by [`.github/workflows/pages.yml`](.github/workflows/pages.yml) on every push to `main` that touches `site/`. One-time setup: in the GitHub repo, go to Settings → Pages and set Source to "GitHub Actions". To preview it locally, open `site/index.html` in a browser.

## Docs

- [docs/web-app.md](docs/web-app.md): how the app, rolling buffer, and device ownership work.
- [docs/capture-engine.md](docs/capture-engine.md): `CaptureEngine` and CLI utilities.
- [docs/manual-verification.md](docs/manual-verification.md): on-Pi verification checklist.
- [docs/pi-startup.md](docs/pi-startup.md): manual start and optional systemd install.
- [docs/hardware-bringup.md](docs/hardware-bringup.md), [docs/phase1-live-hdmi.md](docs/phase1-live-hdmi.md): bring-up history.

## Safety Notes

- Do not commit passwords, private keys, IP inventory, secrets, credentials, or captured media.
- If `sudo` is required on the Pi, run it manually after reviewing the command.
