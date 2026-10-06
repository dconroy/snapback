# Phase 1: Live HDMI Verification

Date: 2026-10-05

## Status

Phase 1 is verified for live video and audio.

The Raspberry Pi, Cam Link, V4L2 video path, ffmpeg, and ALSA audio path are working. After moving the Pi and connecting an HDMI source, the browser preview and `/snapshot.jpg` showed visible console UI content through the Cam Link.

## Diagnostic Preview Server

A tiny diagnostic preview server has been added for bring-up:

```sh
python3 tools/preview_server.py \
  --host 0.0.0.0 \
  --port 8080 \
  --device /dev/video0 \
  --input-format mjpeg \
  --video-size 1920x1080 \
  --framerate 60 \
  --preview-fps 15
```

On the Pi it is deployed with the rest of the repo, at:

```sh
~/snapback/tools/preview_server.py
```

The preview server is currently a manual/background process. It is not installed as a boot service. See `docs/pi-startup.md`.

Open the preview at:

```text
http://snapback.local:8080/
```

Useful endpoints:

- `GET /` shows the diagnostic preview page.
- `GET /api/status` returns device and V4L2 status.
- `GET /snapshot.jpg` returns a single JPEG frame.
- `GET /stream.mjpg` returns an MJPEG preview stream.

This is a temporary bring-up utility, not the final Snapback API or mobile app.

## Verified So Far

- `snapback.local` resolves on the local network.
- `/dev/video0` is the primary Cam Link capture stream.
- `/dev/video1` is metadata and should not be treated as the primary capture stream.
- V4L2 reports `/dev/video0` as `uvcvideo`.
- ffmpeg can capture a still frame from `/dev/video0`.
- The diagnostic web server can serve `/api/status` and `/snapshot.jpg` over the LAN.
- ALSA exposes Cam Link audio as `hw:CARD=C4K,DEV=0`.
- ffmpeg can read Cam Link audio as 48 kHz stereo PCM.
- With an HDMI source connected, `/snapshot.jpg` returned visible 1920x1080 console UI content.

## Current Video Result

The latest browser preview showed visible HDMI content from the connected source. The observed image was somewhat dark, so source HDR/brightness/output-mode behavior may need later tuning, but the video signal is usable for initial development.

Before building long-running recording features, re-check the source output mode if captures appear too dark, washed out, or color-shifted.

## Preferred Initial Capture Settings

Based on current device capability checks:

- Video device: `/dev/video0`
- Input format: `mjpeg`
- Resolution: `1920x1080`
- Frame rate: `60`
- Audio device: `hw:CARD=C4K,DEV=0`
- Audio format observed by ffmpeg: `pcm_s16le`, 48 kHz, stereo

These are the initial working bring-up settings. They should still be revalidated when testing other source devices or video modes.

## Next Step

Continue to Phase 2 by building the first Python `CaptureEngine` around the working `/dev/video0` and `hw:CARD=C4K,DEV=0` devices. For manual preview, open:

```text
http://snapback.local:8080/
```

If the preview later returns to `NO SIGNAL`, inspect the HDMI cable/source connection, source output mode, HDCP/protection behavior, and supported resolution/frame-rate settings.
