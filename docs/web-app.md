# QuickCap Web App

## Pieces

- `quickcap/capture.py`: `CaptureEngine`. The only code that starts ffmpeg. Owns the capture device.
- `quickcap/media.py`: safe filename checks and "latest screenshot/replay" lookup.
- `quickcap/web.py`: FastAPI routes. Thin; every capture action is one engine call.
- `quickcap/static/index.html`: the single page (HTML/CSS/vanilla JS). Polls `/api/status` every 3 s.
- `python -m quickcap serve`: runs uvicorn with exactly one worker.

## Capture Device Ownership

Only one process can read `/dev/video0`. `CaptureEngine.device_owner` is always one of:

- `None`: nobody is reading the device.
- `"buffer"`: the rolling-buffer ffmpeg (normal state while the app runs).
- `"still"`: a one-off still capture (only when the buffer is off or down).
- `"recording"`: a CLI `record-test`.

Claiming the device also takes a non-blocking `flock` on `~/quickcap-runtime/quickcap-device.lock`, so the web app and the CLI cannot both grab the device. Anything that tries while the device is owned gets `DeviceBusyError` (HTTP 409).

The Phase 1 preview server (`tools/quickcap_preview_server.py`) does not know about this lock. Stop it before running QuickCap.

## Rolling Buffer

While the app runs, one long-lived ffmpeg process reads video and audio and writes two outputs:

1. **Segments**: H.264 (`libx264`, preset `ultrafast`, CRF 23) + AAC 128k, cut into 2-second MPEG-TS files `buffer/seg_000123.ts`. Keyframes are forced every 2 s so every segment starts cleanly.
2. **Latest frame**: a full-resolution JPEG written to `buffer/latest.jpg` twice per second (atomically, via temp file + rename).

A background thread checks once per second:

- deletes segments older than ~60 seconds (keeps 31 x 2 s),
- restarts ffmpeg 5 s after it exits (HDMI unplugged, Cam Link reset, etc.) and records the last log lines in `last_error`.

The ffmpeg log is at `buffer/ffmpeg-buffer.log`. Segments, the frame, and the log are cleared each time the buffer (re)starts.

### "Download Last 30 Seconds" behaviour

Replay takes the newest 15 **finished** segments (the one being written is skipped) and joins them with `ffmpeg -c copy` into an MP4 with `+faststart`. No re-encoding, so it takes about a second.

What this means in practice:

- The clip is ~30 s long and ends 0-2 s before the button press (the unfinished segment is not included).
- If the buffer has been running for less than 30 s, you get whatever is there. The response has `approx_seconds`.
- If the buffer is stopped, replay fails with 503. Leftover segments from earlier runs are never used.

### Screenshot behaviour

- Buffer running: copies `buffer/latest.jpg` (at most ~0.5 s old) into the media folder. No second reader on the device.
- Buffer not running: runs a one-shot ffmpeg still capture (same command as `python -m quickcap photo`).

## Media Files

Saved to `~/quickcap-runtime/captures` as `YYYYMMDDTHHMMSSZ-{screenshot|replay}-{id8}.{jpg|mp4}`. Files are written as `.part` first and renamed when complete, so half-written files are never listed or served.

`GET /media/{filename}` only serves names matching `^[A-Za-z0-9][A-Za-z0-9_-]*\.(jpg|mp4)$` that resolve to a regular file directly inside the media directory (symlinks out are refused). Nothing from HTTP input reaches ffmpeg arguments or filesystem paths.

Nothing deletes old captures yet. Clean up manually when disk gets low (shown in the status line).

## Performance Notes

Software H.264 at 1080p60 on a Pi 5 is the heaviest part. `ultrafast` is the default to stay real-time. The cost is bigger files: roughly 30-100 MB per 30 s clip depending on content.

If `docs/manual-verification.md` shows the buffer falling behind, drop to 30 fps (the Cam Link supports 1080p30 MJPEG):

```sh
.venv/bin/python -m quickcap --framerate 30 serve
```

If it keeps up with headroom, try `QUICKCAP_X264_PRESET=superfast` for smaller files.
