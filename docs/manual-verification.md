# Manual Hardware Verification

Unit tests mock ffmpeg. These checks need the real Pi, Cam Link, and an HDMI source. Run from `~/snapback` on `snapback.local` with the preview server stopped.

Pre-hardware smoke test (done on a Mac, 2026-10-06): the exact buffer and replay commands ran with ffmpeg 9 against synthetic `lavfi` video/audio instead of V4L2/ALSA. The replay came out as a 10.0 s, 1920x1080/60 H.264 + 48 kHz stereo AAC MP4, and the screenshot as a 1920x1080 JPEG.

## Results On The Pi (2026-10-06, first deploy)

Deployed with `scripts/deploy.sh`; running as `snapback.service` on port 8080. The Cam Link was showing its own "NO SIGNAL" card (no HDMI source active), so the picture was static:

- New `seg_*.ts` every 2.0 s; the segment count leveled off at 31.
- `POST /api/replay` → 30.003 s MP4, h264 1920x1080 60/1 + aac 48 kHz stereo (checked with `ffprobe` on the Pi).
- `POST /api/screenshot` → 1920x1080 JPEG of the live input.
- ffmpeg ~170% CPU (of 400%), 58 °C, `get_throttled=0x0`.
- ffmpeg log only had harmless startup notices (`EOI missing, emulating`, `Guessed Channel Layout`, `deprecated pixel format`).
- `GET /` 200; `/media/..%2F..%2Fetc%2Fpasswd` 404.

**Still to verify with a real moving HDMI source:** CPU and real-time cadence with busy content (static frames are much cheaper to encode), the phone checks below, and the failure handling.

## 1. Engine without the web app

```sh
.venv/bin/python -m snapback status            # video/audio detected, ffmpeg available
.venv/bin/python -m snapback replay-test --seconds 40
```

Expect JSON with a screenshot and a replay with `approx_seconds: 30`. Check the clip:

```sh
ffprobe -v error -show_entries format=duration:stream=codec_name,width,height,r_frame_rate \
  -of compact ~/snapback-runtime/captures/*-replay-*.mp4 | tail -4
```

- [ ] duration about 30 s
- [ ] h264 1920x1080 60/1 and aac stream present

## 2. Buffer keeps up in real time

Start the app (`.venv/bin/python -m snapback serve`) and in a second SSH session:

```sh
watch -n1 'ls -l --time-style=+%T ~/snapback-runtime/buffer | tail -4; uptime'
cat ~/snapback-runtime/buffer/ffmpeg-buffer.log
```

- [ ] a new `seg_*.ts` appears every ~2 s (not slower)
- [ ] segment count levels off at about 31
- [ ] log has no repeated "real-time buffer ... full" / "frame dropped" warnings
- [ ] `top`: ffmpeg CPU is sustainable and the Pi is not thermal throttling (`vcgencmd get_throttled` → `0x0`)

If it falls behind, see "Performance Notes" in `docs/web-app.md`.

## 3. Phone

On the iPhone, open `http://snapback.local:8080/`.

- [ ] status line shows "Capture device OK · buffer running (Ns)"
- [ ] Grab Screenshot shows a preview of the HDMI picture within ~1 s
- [ ] Download Last 30 Seconds returns a clip that plays in Safari with sound
- [ ] the download link saves the MP4 to Files; it can be moved to Photos from there

## 4. Failure handling

- [ ] Unplug HDMI from the source for 10 s and plug it back in: status shows an error or restarting, then recovers to running without restarting the app.
- [ ] Start `python -m snapback photo` while the app runs: it fails with "capture device is in use by another Snapback process".
- [ ] `curl -i http://snapback.local:8080/media/..%2F..%2Fetc%2Fpasswd` → 404.
- [ ] Ctrl-C the app: `pgrep ffmpeg` shows nothing left running.
