# Capture Engine

The first QuickCap runtime layer is `quickcap.capture.CaptureEngine`.

Its job is to keep hardware and ffmpeg interaction in one place so the future HTTP API can stay small and safe.

## Current Responsibilities

- Decide who owns `/dev/video0` (`device_owner`: buffer, still, recording, or nobody) and hold a cross-process lock file while owned.
- Run and supervise the rolling buffer (`start_buffer`, `stop_buffer`), see `docs/web-app.md`.
- Save a screenshot (`take_screenshot`): from the buffer's latest frame, or a direct capture if the buffer is off.
- Save the last ~30 s (`save_replay`).
- Report cheap status for the web UI (`status`) and verbose diagnostics for the CLI (`get_status`).
- Capture one still image and make a manual test recording (CLI).
- Store media in a configurable runtime directory outside the source tree.

Command construction is split into `build_still_command`, `build_buffer_command`, and `build_replay_command` so it can be unit-tested without hardware. All commands are argument lists; nothing uses `shell=True`.

## Hardware Test Result

Tested on `quikcap.local` on 2026-10-06:

- `python3 -m quickcap status` detected `/dev/video0`, `hw:CARD=C4K,DEV=0`, ffmpeg, V4L2, and ALSA capture.
- `python3 -m quickcap photo` created a 1920x1080 JPEG in `/home/pi/quickcap-runtime/captures`.
- `python3 -m quickcap record-test --seconds 3` created a 3 second MP4.
- `ffprobe` reported the MP4 as H.264 video at 1920x1080/60 fps with AAC stereo audio at 48 kHz.

The diagnostic preview server must be stopped before running photo or recording commands because `/dev/video0` can only be read by one capture process at a time.

## Default Devices

- Video: `/dev/video0`
- Audio: `hw:CARD=C4K,DEV=0`
- Input format: `mjpeg`
- Resolution: `1920x1080`
- Frame rate: `60`

These defaults match the Phase 1 bring-up result for the Elgato Cam Link 4K.

## CLI Usage

Run locally on the Pi from the repository root:

```sh
python3 -m quickcap status
python3 -m quickcap photo
python3 -m quickcap record-test --seconds 3
python3 -m quickcap replay-test --seconds 40   # buffer for 40 s, then screenshot + replay
python3 -m quickcap serve                      # the web app (needs requirements.txt installed)
```

These fail with "capture device is in use" while the web app is running.

To override the media directory:

```sh
QUICKCAP_MEDIA_DIR=~/quickcap-runtime/captures python3 -m quickcap photo
```

The CLI is a development utility. The FastAPI app (`quickcap/web.py`) calls `CaptureEngine` directly.
