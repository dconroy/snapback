from __future__ import annotations

import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from snapback.capture import CaptureConfig, CaptureEngine
from snapback.web import create_app


class WebTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        root = Path(self._tmp.name)
        self.engine = CaptureEngine(CaptureConfig(media_dir=root / "captures"))
        (root / "secret.jpg").write_bytes(b"secret")
        self.client = TestClient(create_app(self.engine, start_buffer=False))

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_index_page_has_both_buttons(self) -> None:
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertIn("Grab Screenshot", response.text)
        self.assertIn("Download Last 30 Seconds", response.text)

    def test_status_shape(self) -> None:
        data = self.client.get("/api/status").json()
        for key in (
            "device_detected",
            "buffer_running",
            "buffer_state",
            "latest_screenshot",
            "latest_replay",
            "disk_free_bytes",
        ):
            self.assertIn(key, data)
        self.assertFalse(data["buffer_running"])
        self.assertIsNone(data["latest_screenshot"])

    def test_screenshot_returns_media_url_that_serves_file(self) -> None:
        def fake_run(command, **kwargs):
            Path(command[-1]).write_bytes(b"\xff\xd8jpeg\xff\xd9")
            return subprocess.CompletedProcess(command, 0, b"", b"")

        with patch("snapback.capture.subprocess.run", side_effect=fake_run):
            response = self.client.post("/api/screenshot")

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertNotIn("path", data)
        self.assertTrue(data["url"].startswith("/media/"))

        media = self.client.get(data["url"])
        self.assertEqual(media.status_code, 200)
        self.assertEqual(media.headers["content-type"], "image/jpeg")
        self.assertEqual(self.client.get("/api/status").json()["latest_screenshot"]["url"], data["url"])

    def test_replay_without_buffer_is_service_unavailable(self) -> None:
        response = self.client.post("/api/replay")
        self.assertEqual(response.status_code, 503)
        self.assertIn("detail", response.json())

    def test_media_route_rejects_paths_outside_media_dir(self) -> None:
        for url in ("/media/..%2Fsecret.jpg", "/media/../secret.jpg", "/media/nope.jpg", "/media/x.txt"):
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url).status_code, 404)


if __name__ == "__main__":
    unittest.main()
