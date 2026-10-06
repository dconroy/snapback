from __future__ import annotations

import fcntl
import os
import re
import shutil
import signal
import subprocess
import threading
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .media import latest_media


DEFAULT_VIDEO_DEVICE = "/dev/video0"
DEFAULT_AUDIO_DEVICE = "hw:CARD=C4K,DEV=0"
DEFAULT_VIDEO_SIZE = "1920x1080"
DEFAULT_FRAMERATE = 60
DEFAULT_INPUT_FORMAT = "mjpeg"
DEFAULT_RUNTIME_DIR = "~/quickcap-runtime"

SEGMENT_TEMPLATE = "seg_%06d.ts"
SEGMENT_RE = re.compile(r"^seg_(\d{6})\.ts$")
LATEST_FRAME_NAME = "latest.jpg"
BUFFER_LOG_NAME = "ffmpeg-buffer.log"
X264_PRESETS = (
    "ultrafast", "superfast", "veryfast", "faster", "fast", "medium", "slow", "slower", "veryslow",
)


class CaptureError(RuntimeError):
    """Raised when the capture device or ffmpeg command fails."""


class DeviceBusyError(CaptureError):
    """Raised when something else already owns the capture device."""


@dataclass(frozen=True)
class CaptureConfig:
    media_dir: Path
    video_device: str = DEFAULT_VIDEO_DEVICE
    audio_device: str = DEFAULT_AUDIO_DEVICE
    video_size: str = DEFAULT_VIDEO_SIZE
    framerate: int = DEFAULT_FRAMERATE
    input_format: str = DEFAULT_INPUT_FORMAT
    buffer_dir: Path | None = None
    segment_seconds: int = 2
    buffer_keep_seconds: int = 60
    replay_seconds: int = 30
    x264_preset: str = "ultrafast"
    screenshot_fps: int = 2

    def __post_init__(self) -> None:
        if self.buffer_dir is None:
            object.__setattr__(self, "buffer_dir", self.media_dir.parent / "buffer")
        if self.x264_preset not in X264_PRESETS:
            raise ValueError(f"unknown x264 preset: {self.x264_preset}")
        if not 1 <= self.segment_seconds <= 10:
            raise ValueError("segment_seconds must be between 1 and 10")
        if self.buffer_keep_seconds < self.replay_seconds + self.segment_seconds:
            raise ValueError("buffer_keep_seconds must be longer than replay_seconds")

    @property
    def lock_path(self) -> Path:
        return self.media_dir.parent / "quickcap-device.lock"

    @classmethod
    def from_env(cls) -> "CaptureConfig":
        env = os.environ
        runtime_dir = Path(env.get("QUICKCAP_RUNTIME_DIR", DEFAULT_RUNTIME_DIR)).expanduser()
        media_dir = Path(env.get("QUICKCAP_MEDIA_DIR", runtime_dir / "captures")).expanduser()
        buffer_dir = Path(env.get("QUICKCAP_BUFFER_DIR", runtime_dir / "buffer")).expanduser()
        return cls(
            media_dir=media_dir,
            buffer_dir=buffer_dir,
            video_device=env.get("QUICKCAP_VIDEO_DEVICE", DEFAULT_VIDEO_DEVICE),
            audio_device=env.get("QUICKCAP_AUDIO_DEVICE", DEFAULT_AUDIO_DEVICE),
            x264_preset=env.get("QUICKCAP_X264_PRESET", "ultrafast"),
        )


@dataclass(frozen=True)
class MediaItem:
    id: str
    media_type: str
    path: Path
    created_at: str
    extra: dict[str, Any] = field(default_factory=dict)

    @property
    def filename(self) -> str:
        return self.path.name

    @classmethod
    def from_path(cls, path: Path) -> "MediaItem":
        parts = path.stem.split("-")
        media_type = parts[1] if len(parts) >= 3 else "unknown"
        created_at = datetime.fromtimestamp(path.stat().st_mtime, timezone.utc)
        return cls(
            id=parts[-1],
            media_type=media_type,
            path=path,
            created_at=created_at.strftime("%Y-%m-%dT%H:%M:%SZ"),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "media_type": self.media_type,
            "path": str(self.path),
            "filename": self.filename,
            "created_at": self.created_at,
            "size_bytes": self.path.stat().st_size if self.path.exists() else 0,
            **self.extra,
        }


class CaptureEngine:
    """Owns every ffmpeg process and decides who may read the capture device.

    Only one ffmpeg process can read /dev/video0 at a time. ``device_owner`` is
    one of None, "buffer", "still", or "recording". A file lock in the runtime
    directory extends that rule to other QuickCap processes such as the CLI.
    """

    def __init__(self, config: CaptureConfig) -> None:
        self.config = config
        self._lock = threading.RLock()
        self._owner: str | None = None
        self._device_lock_file: Any = None

        self._recording_process: subprocess.Popen[bytes] | None = None
        self._recording_item: MediaItem | None = None

        self._buffer_process: subprocess.Popen[bytes] | None = None
        self._buffer_wanted = False
        self._buffer_started_at: float | None = None
        self._next_restart_at = 0.0
        self._last_error: str | None = None
        self._supervisor: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._replay_lock = threading.Lock()

    # ----- device ownership -------------------------------------------------

    @property
    def device_owner(self) -> str | None:
        return self._owner

    def _claim_device(self, owner: str) -> None:
        with self._lock:
            if self._owner is not None:
                raise DeviceBusyError(f"capture device is in use by {self._owner}")
            self.config.lock_path.parent.mkdir(parents=True, exist_ok=True)
            lock_file = open(self.config.lock_path, "w")
            try:
                fcntl.flock(lock_file, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                lock_file.close()
                raise DeviceBusyError("capture device is in use by another QuickCap process") from None
            self._device_lock_file = lock_file
            self._owner = owner

    def _release_device(self, owner: str) -> None:
        with self._lock:
            if self._owner != owner:
                return
            self._owner = None
            if self._device_lock_file is not None:
                fcntl.flock(self._device_lock_file, fcntl.LOCK_UN)
                self._device_lock_file.close()
                self._device_lock_file = None

    # ----- status -----------------------------------------------------------

    @property
    def is_recording(self) -> bool:
        return self._recording_process is not None and self._recording_process.poll() is None

    @property
    def buffer_running(self) -> bool:
        process = self._buffer_process
        return process is not None and process.poll() is None

    def buffer_state(self) -> str:
        if not self._buffer_wanted:
            return "stopped"
        if not self.buffer_running:
            return "restarting"
        if not self.complete_segments():
            return "starting"
        return "running"

    def buffered_seconds(self) -> int:
        return len(self.complete_segments()) * self.config.segment_seconds

    def status(self) -> dict[str, Any]:
        """Cheap status for the web UI; does not spawn any processes."""
        disk_path = self.config.media_dir if self.config.media_dir.exists() else Path.home()
        screenshot = latest_media(self.config.media_dir, "screenshot")
        replay = latest_media(self.config.media_dir, "replay")
        return {
            "device_detected": Path(self.config.video_device).exists(),
            "video_device": self.config.video_device,
            "audio_device": self.config.audio_device,
            "capture_mode": f"{self.config.video_size}@{self.config.framerate} {self.config.input_format}",
            "device_owner": self._owner,
            "buffer_running": self.buffer_running,
            "buffer_state": self.buffer_state(),
            "buffered_seconds": self.buffered_seconds(),
            "replay_seconds": self.config.replay_seconds,
            "recording": self.is_recording,
            "last_error": self._last_error,
            "latest_screenshot": MediaItem.from_path(screenshot) if screenshot else None,
            "latest_replay": MediaItem.from_path(replay) if replay else None,
            "disk_free_bytes": shutil.disk_usage(disk_path).free,
        }

    def get_status(self) -> dict[str, Any]:
        """Verbose diagnostic status for the CLI (runs v4l2-ctl and arecord)."""
        device_path = Path(self.config.video_device)
        disk = shutil.disk_usage(self.config.media_dir.parent if self.config.media_dir.exists() else Path.home())
        v4l2_returncode, v4l2_output = self._run_text(
            ["v4l2-ctl", "-d", self.config.video_device, "--all"],
            timeout=5,
        )
        audio_returncode, audio_output = self._run_text(["arecord", "-l"], timeout=5)

        return {
            "online": True,
            "video_device": self.config.video_device,
            "video_device_detected": device_path.exists(),
            "audio_device": self.config.audio_device,
            "audio_devices_available": audio_returncode == 0,
            "video_size": self.config.video_size,
            "framerate": self.config.framerate,
            "input_format": self.config.input_format,
            "recording": self.is_recording,
            "recording_id": self._recording_item.id if self._recording_item else None,
            "media_dir": str(self.config.media_dir),
            "disk_free_bytes": disk.free,
            "disk_total_bytes": disk.total,
            "v4l2_returncode": v4l2_returncode,
            "v4l2_summary": v4l2_output[:4000],
            "audio_returncode": audio_returncode,
            "audio_summary": audio_output[:2000],
            "ffmpeg_available": shutil.which("ffmpeg") is not None,
        }

    # ----- stills -----------------------------------------------------------

    def take_screenshot(self) -> MediaItem:
        """Save a JPEG of the live input, using the buffer's frame when it is running."""
        if self.buffer_running:
            return self._screenshot_from_buffer()
        return self._capture_still("screenshot")

    def take_photo(self) -> MediaItem:
        return self._capture_still("photo")

    def _screenshot_from_buffer(self) -> MediaItem:
        frame_path = self.config.buffer_dir / LATEST_FRAME_NAME
        max_age = max(3.0, 3.0 / self.config.screenshot_fps)
        for _ in range(3):
            try:
                data = frame_path.read_bytes()
                age = time.time() - frame_path.stat().st_mtime
            except FileNotFoundError:
                data, age = b"", 0.0
            if data.startswith(b"\xff\xd8") and data.rstrip(b"\x00").endswith(b"\xff\xd9") and age <= max_age:
                break
            time.sleep(0.5)
        else:
            raise CaptureError("no fresh frame from the rolling buffer yet")

        self._ensure_media_dir()
        item = self._new_media_item("screenshot", ".jpg")
        tmp_path = item.path.with_name(item.path.name + ".part")
        tmp_path.write_bytes(data)
        tmp_path.replace(item.path)
        return item

    def build_still_command(self, output_path: Path) -> list[str]:
        return [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-f",
            "v4l2",
            "-input_format",
            self.config.input_format,
            "-video_size",
            self.config.video_size,
            "-framerate",
            str(self.config.framerate),
            "-i",
            self.config.video_device,
            "-frames:v",
            "1",
            "-update",
            "1",
            "-y",
            str(output_path),
        ]

    def _capture_still(self, media_type: str) -> MediaItem:
        self._claim_device("still")
        try:
            self._ensure_media_dir()
            item = self._new_media_item(media_type, ".jpg")
            completed = self._run_ffmpeg(self.build_still_command(item.path), timeout=15)
        finally:
            self._release_device("still")
        if completed.returncode != 0 or not item.path.exists() or item.path.stat().st_size == 0:
            stderr = completed.stderr.decode("utf-8", errors="replace")
            raise CaptureError(stderr or "ffmpeg did not create a photo")
        return item

    # ----- rolling buffer ---------------------------------------------------

    def build_buffer_command(self) -> list[str]:
        """One ffmpeg process: H.264/AAC segments plus a periodically refreshed JPEG."""
        c = self.config
        gop = c.framerate * c.segment_seconds
        return [
            "ffmpeg",
            "-hide_banner",
            "-nostdin",
            "-loglevel",
            "warning",
            "-y",
            "-thread_queue_size",
            "1024",
            "-f",
            "v4l2",
            "-input_format",
            c.input_format,
            "-video_size",
            c.video_size,
            "-framerate",
            str(c.framerate),
            "-i",
            c.video_device,
            "-thread_queue_size",
            "1024",
            "-f",
            "alsa",
            "-ac",
            "2",
            "-ar",
            "48000",
            "-i",
            c.audio_device,
            # Output 1: rolling segments.
            "-map",
            "0:v",
            "-map",
            "1:a",
            "-c:v",
            "libx264",
            "-preset",
            c.x264_preset,
            "-crf",
            "23",
            "-pix_fmt",
            "yuv420p",
            "-g",
            str(gop),
            "-keyint_min",
            str(gop),
            "-sc_threshold",
            "0",
            "-force_key_frames",
            f"expr:gte(t,n_forced*{c.segment_seconds})",
            "-c:a",
            "aac",
            "-b:a",
            "128k",
            "-f",
            "segment",
            "-segment_time",
            str(c.segment_seconds),
            "-segment_format",
            "mpegts",
            str(c.buffer_dir / SEGMENT_TEMPLATE),
            # Output 2: latest frame for screenshots.
            "-map",
            "0:v",
            "-vf",
            f"fps={c.screenshot_fps}",
            "-c:v",
            "mjpeg",
            "-q:v",
            "2",
            "-f",
            "image2",
            "-update",
            "1",
            "-atomic_writing",
            "1",
            str(c.buffer_dir / LATEST_FRAME_NAME),
        ]

    def start_buffer(self) -> None:
        """Keep a rolling buffer running until stop_buffer(); restarts ffmpeg if it dies."""
        with self._lock:
            self._buffer_wanted = True
            self._stop_event.clear()
            if not self.buffer_running:
                try:
                    self._spawn_buffer()
                except CaptureError as exc:
                    self._last_error = str(exc)
                    self._next_restart_at = time.monotonic() + 5
            if self._supervisor is None or not self._supervisor.is_alive():
                self._supervisor = threading.Thread(
                    target=self._supervise, name="quickcap-buffer", daemon=True
                )
                self._supervisor.start()

    def stop_buffer(self, timeout: float = 5) -> None:
        with self._lock:
            self._buffer_wanted = False
            self._stop_event.set()
            process = self._buffer_process
            self._buffer_process = None
        if process is not None:
            self._stop_process(process, timeout)
        self._release_device("buffer")
        supervisor = self._supervisor
        if supervisor is not None and supervisor is not threading.current_thread():
            supervisor.join(timeout=timeout)
        self._supervisor = None

    def _spawn_buffer(self) -> None:
        self._claim_device("buffer")
        try:
            buffer_dir = self.config.buffer_dir
            buffer_dir.mkdir(parents=True, exist_ok=True)
            for stale in self._all_segments():
                stale.unlink(missing_ok=True)
            (buffer_dir / LATEST_FRAME_NAME).unlink(missing_ok=True)
            (buffer_dir / BUFFER_LOG_NAME).unlink(missing_ok=True)
            log_file = open(buffer_dir / BUFFER_LOG_NAME, "ab")
            try:
                self._buffer_process = subprocess.Popen(
                    self.build_buffer_command(),
                    stdin=subprocess.DEVNULL,
                    stdout=subprocess.DEVNULL,
                    stderr=log_file,
                )
            finally:
                log_file.close()
        except OSError as exc:
            self._release_device("buffer")
            raise CaptureError(f"could not start buffer: {exc}") from exc
        except BaseException:
            self._release_device("buffer")
            raise
        self._buffer_started_at = time.monotonic()
        self._last_error = None

    def _supervise(self) -> None:
        while not self._stop_event.wait(1.0):
            self.prune_segments()
            with self._lock:
                if not self._buffer_wanted:
                    continue
                process = self._buffer_process
                if process is not None and process.poll() is not None:
                    self._last_error = f"buffer ffmpeg exited with {process.returncode}: {self._log_tail()}"
                    self._buffer_process = None
                    self._release_device("buffer")
                    self._next_restart_at = time.monotonic() + 5
                if self._buffer_process is None and time.monotonic() >= self._next_restart_at:
                    try:
                        self._spawn_buffer()
                    except CaptureError as exc:
                        self._last_error = str(exc)
                        self._next_restart_at = time.monotonic() + 5

    def _log_tail(self, max_chars: int = 500) -> str:
        try:
            text = (self.config.buffer_dir / BUFFER_LOG_NAME).read_text(errors="replace")
        except OSError:
            return ""
        return text.strip()[-max_chars:]

    def _all_segments(self) -> list[Path]:
        buffer_dir = self.config.buffer_dir
        if not buffer_dir.is_dir():
            return []
        segments = [p for p in buffer_dir.iterdir() if SEGMENT_RE.fullmatch(p.name)]
        return sorted(segments, key=lambda p: p.name)

    def complete_segments(self) -> list[Path]:
        """Segments ffmpeg has finished writing (the newest one is still open while running).

        Leftover segments are ignored unless the buffer is switched on, so a
        replay never contains footage from an earlier session.
        """
        if not self._buffer_wanted:
            return []
        segments = self._all_segments()
        if segments and self.buffer_running:
            segments = segments[:-1]
        return segments

    def prune_segments(self) -> None:
        keep = self.config.buffer_keep_seconds // self.config.segment_seconds + 1
        segments = self._all_segments()
        for old in segments[:-keep]:
            old.unlink(missing_ok=True)

    def build_replay_command(self, segments: list[Path], output_path: Path) -> list[str]:
        return [
            "ffmpeg",
            "-hide_banner",
            "-nostdin",
            "-loglevel",
            "error",
            "-i",
            "concat:" + "|".join(str(p) for p in segments),
            "-map",
            "0",
            "-c",
            "copy",
            "-bsf:a",
            "aac_adtstoasc",
            "-movflags",
            "+faststart",
            "-f",
            "mp4",
            "-y",
            str(output_path),
        ]

    def save_replay(self) -> MediaItem:
        """Stitch the newest completed segments (about replay_seconds) into an MP4."""
        with self._replay_lock:
            count = -(-self.config.replay_seconds // self.config.segment_seconds)
            segments = self.complete_segments()[-count:]
            if not self._buffer_wanted:
                raise CaptureError("rolling buffer is not running")
            if not segments:
                raise CaptureError("rolling buffer has no footage yet")

            self._ensure_media_dir()
            item = self._new_media_item("replay", ".mp4")
            tmp_path = item.path.with_name(item.path.name + ".part")
            try:
                completed = self._run_ffmpeg(self.build_replay_command(segments, tmp_path), timeout=60)
            except CaptureError:
                tmp_path.unlink(missing_ok=True)
                raise
            if completed.returncode != 0 or not tmp_path.exists() or tmp_path.stat().st_size == 0:
                tmp_path.unlink(missing_ok=True)
                stderr = completed.stderr.decode("utf-8", errors="replace")
                raise CaptureError(stderr or "ffmpeg did not create a replay clip")
            tmp_path.replace(item.path)
            return MediaItem(
                id=item.id,
                media_type=item.media_type,
                path=item.path,
                created_at=item.created_at,
                extra={"approx_seconds": len(segments) * self.config.segment_seconds},
            )

    # ----- manual recording (CLI) -------------------------------------------

    def start_recording(self) -> MediaItem:
        if self.is_recording:
            raise CaptureError("recording is already active")
        self._claim_device("recording")
        self._ensure_media_dir()
        item = self._new_media_item("video", ".mp4")
        command = [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-f",
            "v4l2",
            "-input_format",
            self.config.input_format,
            "-video_size",
            self.config.video_size,
            "-framerate",
            str(self.config.framerate),
            "-i",
            self.config.video_device,
            "-f",
            "alsa",
            "-i",
            self.config.audio_device,
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            "-crf",
            "23",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            "-b:a",
            "128k",
            "-movflags",
            "+faststart",
            "-y",
            str(item.path),
        ]
        try:
            self._recording_process = subprocess.Popen(command, stdin=subprocess.PIPE)
        except OSError:
            self._release_device("recording")
            raise
        self._recording_item = item
        return item

    def stop_recording(self, timeout: int = 10) -> MediaItem:
        process = self._recording_process
        item = self._recording_item
        if process is None or item is None:
            raise CaptureError("no recording is active")

        if process.poll() is None:
            try:
                assert process.stdin is not None
                process.stdin.write(b"q")
                process.stdin.flush()
                process.wait(timeout=timeout)
            except (BrokenPipeError, subprocess.TimeoutExpired):
                self._stop_process(process, timeout)

        self._recording_process = None
        self._recording_item = None
        self._release_device("recording")
        if process.returncode not in (0, 255):
            raise CaptureError(f"ffmpeg recording exited with {process.returncode}")
        if not item.path.exists() or item.path.stat().st_size == 0:
            raise CaptureError("recording stopped but no video file was created")
        return item

    # ----- helpers ----------------------------------------------------------

    @staticmethod
    def _stop_process(process: subprocess.Popen[bytes], timeout: float) -> None:
        if process.poll() is not None:
            return
        process.send_signal(signal.SIGINT)
        try:
            process.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=timeout)

    def _ensure_media_dir(self) -> None:
        self.config.media_dir.mkdir(parents=True, exist_ok=True)

    def _new_media_item(self, media_type: str, suffix: str) -> MediaItem:
        now = datetime.now(timezone.utc)
        media_id = uuid.uuid4().hex
        filename = f"{now:%Y%m%dT%H%M%SZ}-{media_type}-{media_id[:8]}{suffix}"
        return MediaItem(
            id=media_id,
            media_type=media_type,
            path=self.config.media_dir / filename,
            created_at=now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        )

    @staticmethod
    def _run_ffmpeg(command: list[str], timeout: float) -> subprocess.CompletedProcess[bytes]:
        try:
            return subprocess.run(command, check=False, capture_output=True, timeout=timeout)
        except FileNotFoundError:
            raise CaptureError("ffmpeg not found") from None
        except subprocess.TimeoutExpired:
            raise CaptureError(f"ffmpeg timed out after {timeout} seconds") from None

    @staticmethod
    def _run_text(command: list[str], timeout: int) -> tuple[int, str]:
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
