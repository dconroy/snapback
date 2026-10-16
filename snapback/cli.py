from __future__ import annotations

import argparse
import asyncio
import json
import subprocess
import sys
import time
from contextlib import contextmanager
from pathlib import Path

from .capture import CaptureConfig, CaptureEngine


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Snapback capture utility")
    parser.add_argument("--media-dir", help="Directory for captured media")
    parser.add_argument("--video-device", default=None)
    parser.add_argument("--audio-device", default=None)
    parser.add_argument("--video-size", default=None)
    parser.add_argument("--framerate", type=int, default=None)
    parser.add_argument("--input-format", default=None)

    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("status", help="Print capture status as JSON")
    subparsers.add_parser("photo", help="Capture one still image")
    record_parser = subparsers.add_parser("record-test", help="Record a short test clip")
    record_parser.add_argument("--seconds", type=float, default=3.0)
    replay_parser = subparsers.add_parser(
        "replay-test", help="Run the rolling buffer for a while, then save a replay clip"
    )
    replay_parser.add_argument("--seconds", type=float, default=40.0)
    serve_parser = subparsers.add_parser("serve", help="Run the Snapback web app")
    serve_parser.add_argument("--host", default="0.0.0.0")
    serve_parser.add_argument("--port", type=int, default=8080)
    return parser


def make_config(args: argparse.Namespace) -> CaptureConfig:
    config = CaptureConfig.from_env()
    updates = {}
    for field in ("media_dir", "video_device", "audio_device", "video_size", "framerate", "input_format"):
        value = getattr(args, field)
        if value is not None:
            updates[field] = value
    if "media_dir" in updates:
        updates["media_dir"] = Path(updates["media_dir"]).expanduser()
    return CaptureConfig(**{**config.__dict__, **updates})


@contextmanager
def _ignore_signals():
    yield


async def _serve(servers: list) -> None:
    if len(servers) == 2:
        http, https = servers
        handle_exit = http.handle_exit

        def stop_both(sig, frame):
            https.should_exit = True
            handle_exit(sig, frame)

        http.handle_exit = stop_both
        https.capture_signals = _ignore_signals
    await asyncio.gather(*(server.serve() for server in servers))


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    if args.command == "serve":
        import uvicorn

        from .tls import HTTPS_PORT, certificate_hosts, ensure_certificate
        from .web import create_app

        engine = CaptureEngine(make_config(args))
        app = create_app(engine)
        # Exactly one worker: the process owns the capture device.
        servers = [uvicorn.Server(uvicorn.Config(app, host=args.host, port=args.port, workers=1))]
        try:
            cert, key = ensure_certificate(engine.config.media_dir.parent / "tls", certificate_hosts())
        except (OSError, subprocess.CalledProcessError) as exc:
            print(f"HTTPS not started: {exc}", file=sys.stderr)
        else:
            print(f"Photos sharing: https://snapback.local:{HTTPS_PORT}/", file=sys.stderr)
            servers.append(uvicorn.Server(uvicorn.Config(
                app, host=args.host, port=HTTPS_PORT,
                ssl_certfile=str(cert), ssl_keyfile=str(key), workers=1,
            )))
        asyncio.run(_serve(servers))
        return 0

    engine = CaptureEngine(make_config(args))

    if args.command == "status":
        print(json.dumps(engine.get_status(), indent=2))
        return 0
    if args.command == "photo":
        print(json.dumps(engine.take_photo().to_dict(), indent=2))
        return 0
    if args.command == "record-test":
        item = engine.start_recording()
        time.sleep(args.seconds)
        completed = engine.stop_recording()
        print(json.dumps(completed.to_dict() | {"requested_seconds": args.seconds}, indent=2))
        return 0
    if args.command == "replay-test":
        engine.start_buffer()
        try:
            time.sleep(args.seconds)
            status = engine.status() | {"latest_screenshot": None, "latest_replay": None}
            status["recent"] = [item.to_dict() for item in status["recent"]]
            print(json.dumps(status, indent=2))
            shot = engine.take_screenshot()
            clip = engine.save_replay()
        finally:
            engine.stop_buffer()
        print(json.dumps({"screenshot": shot.to_dict(), "replay": clip.to_dict()}, indent=2))
        return 0

    parser.error(f"unknown command: {args.command}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
