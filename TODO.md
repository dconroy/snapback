# QuickCap TODO

## Current Guardrails

- Use `quikcap.local` where practical; do not hardcode DHCP-assigned IP addresses.
- Do not store passwords, credentials, secrets, or captured media in git.
- Keep the system local-network only: no cloud services, accounts, telemetry, or external database.
- Keep the implementation simple and Raspberry Pi/Linux native.
- Prefer Python, ffmpeg, V4L2, FastAPI, simple HTML/CSS/JavaScript, and Linux-native services.
- Avoid Docker, Kubernetes, Redis, PostgreSQL, React, Node build systems, and unnecessary frameworks.
- Do not add GPIO or physical-button support in this version.

## Phase 1: Verify Live HDMI Source

- Done: inspect the Cam Link with `v4l2-ctl` and ffmpeg.
- Done: confirm supported formats, resolutions, frame rates, and pixel formats.
- Done: determine that audio is exposed through ALSA as `hw:CARD=C4K,DEV=0`.
- Done: identify initial working capture settings of `/dev/video0`, MJPEG, 1920x1080, 60 fps.
- Done: add a tiny diagnostic preview web server so the incoming HDMI feed can be viewed from a browser during bring-up.
- Done: capture a real still frame from the connected HDMI source into a gitignored runtime/captures directory.
- Done: verify visible HDMI video in the browser preview and `/snapshot.jpg`.
- Follow-up: revisit source HDR/brightness/output mode if captures appear too dark.

## Phase 2: Capture Engine

- Done: create a Python `CaptureEngine` abstraction that owns all ffmpeg interaction.
- Done: implement initial methods for status, still capture, recording start, recording stop, and recording state.
- Done: use safe `subprocess` calls without `shell=True`.
- Done: generate filenames with timestamps and UUIDs.
- Done: store runtime media in a configurable directory outside source code.
- Done: test still capture and a short MP4 recording on the Pi.
- Done: explicit device ownership in `CaptureEngine` (`device_owner` + lock file). The buffer owns `/dev/video0` while the app runs; screenshots come from the buffer's frame output.

## Phase 3-5: Two-Button App (initial version built 2026-10-06)

Scope was narrowed to two actions: Grab Screenshot and Download Last 30 Seconds. See `docs/web-app.md`.

- Done: rolling buffer (2 s H.264/AAC TS segments, ~60 s kept, auto-restart on ffmpeg exit).
- Done: `save_replay()` joins the newest ~30 s of finished segments with `-c copy`.
- Done: FastAPI app: `GET /`, `GET /api/status`, `POST /api/screenshot`, `POST /api/replay`, `GET /media/{filename}`.
- Done: single mobile page with status line, two buttons, latest screenshot preview, latest replay player/link.
- Done: unit tests for path safety, media listing, command construction, ownership, buffer pruning, replay assembly, web routes.
- Done: systemd unit template in `deploy/` (not installed).
- Done: smoke test of the real buffer/replay ffmpeg commands with synthetic input on a Mac.
- Next: run `docs/manual-verification.md` on the Pi, especially real-time encoding at 1080p60.
- Later: automatic cleanup of old captures when disk gets low.
- Later, maybe: exact 30.0 s trimming (currently 28-30 s of whole segments ending 0-2 s before the press).
- Dropped for now: manual start/stop recording and a full media browser in the UI.

## GitHub Pages Marketing Site

- Done: product renamed to Snapback (code name and Python package stay `quickcap`).
- Done: static page in `site/` (plain HTML/CSS, CSS phone mockup of the app), deployed by `.github/workflows/pages.yml`.
- Done: liability disclaimer in `DISCLAIMER.md`, README, the site, and the app footer.
- Next: in GitHub Settings → Pages, set Source to "GitHub Actions" (one-time, manual).
- Next: pick an open-source license (e.g. MIT) and add `LICENSE`; none is set yet.
- Later: replace the CSS mockup with real screenshots once captured on the Pi. `*.png`/`*.jpg` are gitignored, so add an exception for `site/`.
