#!/usr/bin/env python3
"""Tiny QuickCap diagnostic preview server.

This is intentionally simple: it uses only Python's standard library and
ffmpeg. It is for bring-up, not the final QuickCap API/UI.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import threading
import time
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any


HTML = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>QuickCap Preview</title>
  <style>
    :root {
      color-scheme: dark;
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      background: #101316;
      color: #f3f5f7;
    }
    body {
      margin: 0;
      min-height: 100vh;
      display: grid;
      grid-template-rows: auto 1fr auto;
    }
    header, footer {
      padding: 14px 16px;
      background: #171b20;
      border-color: #2a3038;
    }
    header {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 12px;
      border-bottom: 1px solid #2a3038;
    }
    h1 {
      margin: 0;
      font-size: 18px;
      font-weight: 650;
    }
    main {
      display: grid;
      align-content: center;
      gap: 14px;
      padding: 16px;
    }
    .frame {
      width: min(100%, 1100px);
      margin: 0 auto;
      background: #050607;
      border: 1px solid #2a3038;
      border-radius: 8px;
      overflow: hidden;
      aspect-ratio: 16 / 9;
      display: grid;
      place-items: center;
    }
    img {
      width: 100%;
      height: 100%;
      object-fit: contain;
      display: block;
    }
    .controls {
      width: min(100%, 1100px);
      margin: 0 auto;
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 12px;
      flex-wrap: wrap;
    }
    button, a {
      border: 1px solid #3a4450;
      color: #f3f5f7;
      background: #232a32;
      border-radius: 7px;
      padding: 10px 12px;
      font: inherit;
      text-decoration: none;
    }
    button:active, a:active {
      transform: translateY(1px);
    }
    code {
      color: #bac7d5;
      overflow-wrap: anywhere;
    }
    footer {
      border-top: 1px solid #2a3038;
      color: #bac7d5;
      font-size: 13px;
    }
  </style>
</head>
<body>
  <header>
    <h1>QuickCap Preview</h1>
    <code id="state">loading</code>
  </header>
  <main>
    <div class="frame">
      <img src="/stream.mjpg" alt="Live HDMI preview">
    </div>
    <div class="controls">
      <a href="/snapshot.jpg" target="_blank" rel="noreferrer">Open snapshot</a>
      <button type="button" id="refresh">Refresh status</button>
      <code id="details"></code>
    </div>
  </main>
  <footer>
    Diagnostic-only server for Phase 1 hardware bring-up.
  </footer>
  <script>
    async function refreshStatus() {
      const state = document.getElementById("state");
      const details = document.getElementById("details");
      try {
        const response = await fetch("/api/status", {cache: "no-store"});
        const data = await response.json();
        state.textContent = data.capture_device_detected ? "capture device detected" : "no capture device";
        details.textContent = `${data.device} ${data.video_size}@${data.framerate} ${data.input_format}`;
      } catch (error) {
        state.textContent = "status unavailable";
        details.textContent = String(error);
      }
    }
    document.getElementById("refresh").addEventListener("click", refreshStatus);
    refreshStatus();
  </script>
</body>
</html>
"""


class PreviewState:
    def __init__(self) -> None:
        self.capture_lock = threading.Lock()
        self.frame_lock = threading.Lock()
        self.latest_frame: bytes | None = None
        self.latest_frame_time: float | None = None

    def set_frame(self, frame: bytes) -> None:
        with self.frame_lock:
            self.latest_frame = frame
            self.latest_frame_time = time.time()

    def get_frame(self) -> tuple[bytes | None, float | None]:
        with self.frame_lock:
            return self.latest_frame, self.latest_frame_time


def run_text(command: list[str], timeout: int = 5) -> tuple[int, str]:
    try:
        completed = subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except FileNotFoundError:
        return 127, f"{command[0]} not found"
    except subprocess.TimeoutExpired:
        return 124, "command timed out"

    return completed.returncode, (completed.stdout + completed.stderr).strip()


def ffmpeg_snapshot(args: argparse.Namespace) -> bytes:
    command = [
        "ffmpeg",
        "-hide_banner",
        "-loglevel",
        "error",
        "-f",
        "v4l2",
        "-input_format",
        args.input_format,
        "-video_size",
        args.video_size,
        "-framerate",
        str(args.framerate),
        "-i",
        args.device,
        "-frames:v",
        "1",
        "-f",
        "image2pipe",
        "-vcodec",
        "mjpeg",
        "-",
    ]
    completed = subprocess.run(command, check=False, capture_output=True, timeout=12)
    if completed.returncode != 0 or not completed.stdout:
        stderr = completed.stderr.decode("utf-8", errors="replace")
        raise RuntimeError(stderr or "ffmpeg did not return a snapshot")
    return completed.stdout


def iter_jpegs(stream: Any):
    buffer = b""
    while True:
        chunk = stream.read(8192)
        if not chunk:
            return
        buffer += chunk
        while True:
            start = buffer.find(b"\xff\xd8")
            end = buffer.find(b"\xff\xd9", start + 2)
            if start == -1 or end == -1:
                if start > 0:
                    buffer = buffer[start:]
                break
            frame = buffer[start : end + 2]
            buffer = buffer[end + 2 :]
            yield frame


def make_handler(args: argparse.Namespace):
    state = PreviewState()

    class Handler(BaseHTTPRequestHandler):
        server_version = "QuickCapPreview/0.1"

        def log_message(self, fmt: str, *values: Any) -> None:
            sys.stderr.write(
                f"{self.address_string()} [{self.log_date_time_string()}] {fmt % values}\n"
            )

        def send_bytes(self, status: HTTPStatus, content_type: str, body: bytes) -> None:
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self) -> None:
            if self.path in ("/", "/index.html"):
                self.send_bytes(HTTPStatus.OK, "text/html; charset=utf-8", HTML.encode())
                return
            if self.path == "/api/status":
                self.handle_status()
                return
            if self.path == "/snapshot.jpg":
                self.handle_snapshot()
                return
            if self.path == "/stream.mjpg":
                self.handle_stream()
                return
            self.send_error(HTTPStatus.NOT_FOUND)

        def handle_status(self) -> None:
            _, latest_frame_time = state.get_frame()
            latest_frame_age = None
            if latest_frame_time is not None:
                latest_frame_age = round(time.time() - latest_frame_time, 3)
            status = {
                "device": args.device,
                "device_exists": Path(args.device).exists(),
                "capture_device_detected": Path(args.device).exists(),
                "input_format": args.input_format,
                "video_size": args.video_size,
                "framerate": args.framerate,
                "ffmpeg": bool(shutil.which("ffmpeg")),
                "stream_active": state.capture_lock.locked(),
                "latest_frame_age_seconds": latest_frame_age,
            }
            code, output = run_text(["v4l2-ctl", "-d", args.device, "--all"])
            status["v4l2_returncode"] = code
            status["v4l2_summary"] = output[:4000]
            body = json.dumps(status, indent=2).encode()
            self.send_bytes(HTTPStatus.OK, "application/json; charset=utf-8", body)

        def handle_snapshot(self) -> None:
            body, _ = state.get_frame()
            if body is not None:
                self.send_bytes(HTTPStatus.OK, "image/jpeg", body)
                return
            if not state.capture_lock.acquire(blocking=False):
                self.send_error(
                    HTTPStatus.SERVICE_UNAVAILABLE,
                    "Capture device is busy and no preview frame is cached yet.",
                )
                return
            try:
                body = ffmpeg_snapshot(args)
            except Exception as exc:
                self.send_error(HTTPStatus.INTERNAL_SERVER_ERROR, str(exc))
                return
            finally:
                state.capture_lock.release()
            state.set_frame(body)
            self.send_bytes(HTTPStatus.OK, "image/jpeg", body)

        def handle_stream(self) -> None:
            if not state.capture_lock.acquire(blocking=False):
                self.send_error(
                    HTTPStatus.CONFLICT,
                    "Another preview stream or capture is already using the device.",
                )
                return
            command = [
                "ffmpeg",
                "-hide_banner",
                "-loglevel",
                "error",
                "-f",
                "v4l2",
                "-input_format",
                args.input_format,
                "-video_size",
                args.video_size,
                "-framerate",
                str(args.framerate),
                "-i",
                args.device,
                "-vf",
                f"fps={args.preview_fps}",
                "-q:v",
                str(args.jpeg_quality),
                "-f",
                "mjpeg",
                "-",
            ]
            process = subprocess.Popen(
                command,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            assert process.stdout is not None
            try:
                self.send_response(HTTPStatus.OK)
                self.send_header(
                    "Content-Type",
                    "multipart/x-mixed-replace; boundary=quickcap",
                )
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                for frame in iter_jpegs(process.stdout):
                    state.set_frame(frame)
                    self.wfile.write(b"--quickcap\r\n")
                    self.wfile.write(b"Content-Type: image/jpeg\r\n")
                    self.wfile.write(f"Content-Length: {len(frame)}\r\n\r\n".encode())
                    self.wfile.write(frame)
                    self.wfile.write(b"\r\n")
                    self.wfile.flush()
            except (BrokenPipeError, ConnectionResetError):
                pass
            finally:
                process.terminate()
                try:
                    process.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    process.kill()
                state.capture_lock.release()
                time.sleep(0.1)

    return Handler


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8080)
    parser.add_argument("--device", default="/dev/video0")
    parser.add_argument("--input-format", default="mjpeg")
    parser.add_argument("--video-size", default="1920x1080")
    parser.add_argument("--framerate", type=int, default=60)
    parser.add_argument("--preview-fps", type=int, default=15)
    parser.add_argument("--jpeg-quality", type=int, default=5)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    server = ThreadingHTTPServer((args.host, args.port), make_handler(args))
    print(f"QuickCap preview listening on http://{args.host}:{args.port}", flush=True)
    print(
        f"Device {args.device} as {args.video_size}@{args.framerate} {args.input_format}",
        flush=True,
    )
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
