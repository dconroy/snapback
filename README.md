# Snapback

**Instant replay for anything with HDMI.** Website: [snapback.video](https://www.snapback.video/) · Contact: [contact@snapback.video](mailto:contact@snapback.video)

Snapback turns a Raspberry Pi 5 with an Elgato Cam Link 4K into a tiny HDMI capture box for the home network. Open it on an iPhone and there are two buttons:

1. **Grab Screenshot**: saves a 1920x1080 JPEG of the live HDMI input.
2. **Download Last 30 Seconds**: saves the previous ~30 seconds (H.264 + AAC MP4).

No accounts, cloud, telemetry, database, Docker, or JS build tooling. Python + FastAPI + ffmpeg + one HTML file.

The project's code name was QuickCap, and the code still uses it: the Python package is `quickcap`, settings are `QUICKCAP_*` variables, and files live in `~/quickcap-runtime`. The GitHub repo is `dconroy/snapback` (renamed from `dconroy/quickcap`).

> **Disclaimer:** Snapback is a personal home project provided **as-is, without warranty of any kind**. The authors are not liable for lost recordings, data loss, hardware damage, or anything else arising from its use. You are responsible for what you capture, including copyright, terms of service, and recording/consent laws. It has no login, so run it only on a trusted network and never expose it to the internet. Not affiliated with Raspberry Pi, Elgato, or Apple. Read the full [DISCLAIMER.md](DISCLAIMER.md).

## Deploy To The Pi

The Pi has no git checkout. You edit on the Mac and push files over SSH:

```sh
cp .env.example .env        # once: SSH user/host (and password, or use SSH keys)
scripts/deploy.sh           # copy code, install deps, restart, print /api/status
```

Then open `http://quikcap.local:8080/` on the phone.

`deploy.sh` rsyncs the repo to `~/quickcap` on the Pi, leaving out `.git`, `.venv`, `.env`, and `site/`. It then runs `scripts/pi-install.sh` on the Pi, which:

1. creates `~/quickcap/.venv` if needed and installs `requirements.txt`;
2. installs the systemd **user** service `snapback.service`, which needs no sudo;
3. stops the Phase 1 preview server if it is running, since it holds `/dev/video0` and port 8080;
4. restarts Snapback and prints its status.

The service restarts on crash, but it is **not enabled at boot**. After a reboot, run `scripts/pi-ctl.sh start` or redeploy. See [docs/pi-startup.md](docs/pi-startup.md) to opt in to starting at boot.

Day-to-day commands from the Mac:

```sh
scripts/pi-ctl.sh status       # service state + /api/status
scripts/pi-ctl.sh logs 200     # app logs (journald)
scripts/pi-ctl.sh ffmpeg-log   # rolling-buffer ffmpeg warnings
scripts/pi-ctl.sh restart | stop | start
scripts/pi-ctl.sh ssh
```

The rolling buffer starts with the app. Give it ~30 seconds before the first replay has full length.

## Configuration

Environment variables, all optional. On the Pi, put them in `~/quickcap-runtime/snapback.env` (`KEY=value` lines) and run `scripts/pi-ctl.sh restart`.

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
QUICKCAP_START_BUFFER=0 .venv/bin/python -m quickcap serve --port 8080   # UI without hardware
```

Unit tests mock ffmpeg and need no hardware. Hardware checks are in [docs/manual-verification.md](docs/manual-verification.md).

## Website

The marketing page at [snapback.video](https://www.snapback.video/) is plain HTML in [`site/`](site/). It's published to GitHub Pages by [`.github/workflows/pages.yml`](.github/workflows/pages.yml) on every push to `main` that touches `site/`. To preview it locally, open `site/index.html` in a browser.

Pages is set to Source "GitHub Actions", with the custom domain `www.snapback.video` configured in the repo's Pages settings (GitHub redirects the bare `snapback.video` to it). There's no `CNAME` file because GitHub ignores it for Actions deployments. DNS at the registrar must point at GitHub Pages:

| Host | Type | Value |
| --- | --- | --- |
| `@` | A | `185.199.108.153`, `185.199.109.153`, `185.199.110.153`, `185.199.111.153` |
| `@` | AAAA | `2606:50c0:8000::153`, `2606:50c0:8001::153`, `2606:50c0:8002::153`, `2606:50c0:8003::153` |
| `www` | CNAME | `dconroy.github.io` |

## Docs

- [docs/web-app.md](docs/web-app.md): how the app, rolling buffer, and device ownership work.
- [docs/capture-engine.md](docs/capture-engine.md): `CaptureEngine` and CLI utilities.
- [docs/manual-verification.md](docs/manual-verification.md): on-Pi verification checklist.
- [docs/pi-startup.md](docs/pi-startup.md): manual start and optional systemd install.
- [docs/hardware-bringup.md](docs/hardware-bringup.md), [docs/phase1-live-hdmi.md](docs/phase1-live-hdmi.md): bring-up history.

## Safety Notes

- Do not commit passwords, private keys, IP inventory, secrets, credentials, or captured media.
- If `sudo` is required on the Pi, run it manually after reviewing the command.
