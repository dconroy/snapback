from __future__ import annotations

import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from quickcap.capture import CaptureConfig, CaptureEngine, CaptureError, DeviceBusyError

JPEG = b"\xff\xd8fake-jpeg\xff\xd9"


class FakeProcess:
    """Stands in for a long-running ffmpeg Popen."""

    def __init__(self, *args, **kwargs) -> None:
        self.args = args
        self.returncode = None

    def poll(self):
        return self.returncode

    def send_signal(self, sig) -> None:
        self.returncode = 255

    def wait(self, timeout=None):
        return self.returncode

    def kill(self) -> None:
        self.returncode = -9


def make_engine(tmpdir: str) -> CaptureEngine:
    return CaptureEngine(CaptureConfig(media_dir=Path(tmpdir) / "captures"))


def write_segments(engine: CaptureEngine, count: int) -> list[Path]:
    engine.config.buffer_dir.mkdir(parents=True, exist_ok=True)
    paths = []
    for i in range(count):
        path = engine.config.buffer_dir / f"seg_{i:06d}.ts"
        path.write_bytes(b"ts")
        paths.append(path)
    return paths


class CaptureEngineTests(unittest.TestCase):
    def test_photo_uses_safe_ffmpeg_arguments(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            engine = CaptureEngine(CaptureConfig(media_dir=Path(tmpdir)))

            def fake_run(command, **kwargs):
                Path(command[-1]).write_bytes(b"jpeg")
                return subprocess.CompletedProcess(command, 0, b"", b"")

            with patch("quickcap.capture.subprocess.run", side_effect=fake_run) as run:
                item = engine.take_photo()

            command = run.call_args.args[0]
            self.assertEqual(command[0], "ffmpeg")
            self.assertIn("/dev/video0", command)
            self.assertNotIn("shell", run.call_args.kwargs)
            self.assertTrue(item.path.exists())
            self.assertEqual(item.media_type, "photo")
            self.assertIsNone(engine.device_owner)

    def test_photo_failure_raises_capture_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            engine = CaptureEngine(CaptureConfig(media_dir=Path(tmpdir)))
            failed = subprocess.CompletedProcess(["ffmpeg"], 1, b"", b"bad input")

            with patch("quickcap.capture.subprocess.run", return_value=failed):
                with self.assertRaises(CaptureError):
                    engine.take_photo()
            self.assertIsNone(engine.device_owner)

    def test_status_reports_missing_helpers_without_crashing(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            engine = CaptureEngine(CaptureConfig(media_dir=Path(tmpdir)))

            def fake_run(command, **kwargs):
                raise FileNotFoundError(command[0])

            with patch("quickcap.capture.subprocess.run", side_effect=fake_run):
                status = engine.get_status()

            self.assertEqual(status["v4l2_returncode"], 127)
            self.assertEqual(status["audio_returncode"], 127)


class ConfigTests(unittest.TestCase):
    def test_defaults_live_under_runtime_dir(self) -> None:
        with patch.dict("os.environ", {"QUICKCAP_RUNTIME_DIR": "/tmp/qc-runtime"}, clear=True):
            config = CaptureConfig.from_env()
        self.assertEqual(config.media_dir, Path("/tmp/qc-runtime/captures"))
        self.assertEqual(config.buffer_dir, Path("/tmp/qc-runtime/buffer"))
        self.assertEqual(config.video_device, "/dev/video0")

    def test_rejects_unknown_preset(self) -> None:
        with self.assertRaises(ValueError):
            CaptureConfig(media_dir=Path("/tmp/x"), x264_preset="--evil")


class BufferCommandTests(unittest.TestCase):
    def test_buffer_command_reads_video0_and_writes_segments_and_frame(self) -> None:
        engine = CaptureEngine(CaptureConfig(media_dir=Path("/rt/captures")))
        command = engine.build_buffer_command()

        self.assertEqual(command[0], "ffmpeg")
        self.assertTrue(all(isinstance(part, str) for part in command))
        self.assertEqual(command[command.index("-i") + 1], "/dev/video0")
        self.assertNotIn("/dev/video1", command)
        self.assertIn("hw:CARD=C4K,DEV=0", command)
        self.assertIn("mjpeg", command)
        self.assertIn("1920x1080", command)
        self.assertIn("segment", command)
        self.assertEqual(command[command.index("-segment_time") + 1], "2")
        self.assertEqual(command[command.index("-g") + 1], "120")
        self.assertIn("/rt/buffer/seg_%06d.ts", command)
        self.assertEqual(command[-1], "/rt/buffer/latest.jpg")

    def test_replay_command_concats_segments_without_reencoding(self) -> None:
        engine = CaptureEngine(CaptureConfig(media_dir=Path("/rt/captures")))
        segments = [Path("/rt/buffer/seg_000001.ts"), Path("/rt/buffer/seg_000002.ts")]
        command = engine.build_replay_command(segments, Path("/rt/captures/out.mp4"))

        self.assertIn("concat:/rt/buffer/seg_000001.ts|/rt/buffer/seg_000002.ts", command)
        self.assertEqual(command[command.index("-c") + 1], "copy")
        self.assertEqual(command[-1], "/rt/captures/out.mp4")


class RollingBufferTests(unittest.TestCase):
    def test_start_buffer_claims_device_and_blocks_direct_capture(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            engine = make_engine(tmpdir)
            with patch("quickcap.capture.subprocess.Popen", FakeProcess):
                engine.start_buffer()
                try:
                    self.assertTrue(engine.buffer_running)
                    self.assertEqual(engine.device_owner, "buffer")
                    with self.assertRaises(DeviceBusyError):
                        engine.take_photo()
                finally:
                    engine.stop_buffer()
            self.assertFalse(engine.buffer_running)
            self.assertIsNone(engine.device_owner)

    def test_second_engine_cannot_claim_device(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            first, second = make_engine(tmpdir), make_engine(tmpdir)
            first._claim_device("still")
            try:
                with self.assertRaises(DeviceBusyError):
                    second._claim_device("still")
            finally:
                first._release_device("still")
            second._claim_device("still")
            second._release_device("still")

    def test_complete_segments_skip_the_one_being_written(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            engine = make_engine(tmpdir)
            segments = write_segments(engine, 3)
            self.assertEqual(engine.complete_segments(), [], "buffer off: ignore leftovers")

            engine._buffer_wanted = True
            self.assertEqual(engine.complete_segments(), segments)

            engine._buffer_process = FakeProcess()
            self.assertEqual(engine.complete_segments(), segments[:2])
            self.assertEqual(engine.buffered_seconds(), 4)

    def test_prune_keeps_about_sixty_seconds(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            engine = make_engine(tmpdir)
            segments = write_segments(engine, 40)
            engine.prune_segments()
            remaining = sorted(engine.config.buffer_dir.glob("seg_*.ts"))
            self.assertEqual(remaining, segments[-31:])

    def test_save_replay_uses_last_thirty_seconds_of_segments(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            engine = make_engine(tmpdir)
            segments = write_segments(engine, 25)
            engine._buffer_wanted = True
            engine._buffer_process = FakeProcess()

            def fake_run(command, **kwargs):
                Path(command[-1]).write_bytes(b"mp4")
                return subprocess.CompletedProcess(command, 0, b"", b"")

            with patch("quickcap.capture.subprocess.run", side_effect=fake_run) as run:
                item = engine.save_replay()

            command = run.call_args.args[0]
            concat = command[command.index("-i") + 1]
            used = concat.removeprefix("concat:").split("|")
            self.assertEqual(used, [str(p) for p in segments[-16:-1]])
            self.assertEqual(item.media_type, "replay")
            self.assertEqual(item.extra["approx_seconds"], 30)
            self.assertTrue(item.path.exists())
            self.assertEqual(list(engine.config.media_dir.glob("*.part")), [])

    def test_save_replay_without_footage_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            with self.assertRaises(CaptureError):
                make_engine(tmpdir).save_replay()

    def test_screenshot_while_buffering_copies_latest_frame(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            engine = make_engine(tmpdir)
            engine.config.buffer_dir.mkdir(parents=True)
            (engine.config.buffer_dir / "latest.jpg").write_bytes(JPEG)
            engine._buffer_process = FakeProcess()

            with patch("quickcap.capture.subprocess.run") as run:
                item = engine.take_screenshot()

            run.assert_not_called()
            self.assertEqual(item.media_type, "screenshot")
            self.assertEqual(item.path.read_bytes(), JPEG)


if __name__ == "__main__":
    unittest.main()
