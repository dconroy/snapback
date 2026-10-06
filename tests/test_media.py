from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

from snapback.media import latest_media, list_media, safe_media_path


class SafeMediaPathTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.media_dir = self.root / "captures"
        self.media_dir.mkdir()
        (self.media_dir / "20261006T140000Z-screenshot-aaaa1111.jpg").write_bytes(b"jpg")
        (self.root / "secret.jpg").write_bytes(b"secret")

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_accepts_existing_media_file(self) -> None:
        path = safe_media_path(self.media_dir, "20261006T140000Z-screenshot-aaaa1111.jpg")
        self.assertEqual(path, (self.media_dir / "20261006T140000Z-screenshot-aaaa1111.jpg").resolve())

    def test_rejects_traversal_and_odd_names(self) -> None:
        for name in (
            "../secret.jpg",
            "..%2Fsecret.jpg",
            "/etc/passwd",
            "sub/file.jpg",
            ".hidden.jpg",
            "notes.txt",
            "file.jpg.part",
            "",
            "missing.jpg",
        ):
            with self.subTest(name=name):
                self.assertIsNone(safe_media_path(self.media_dir, name))

    def test_rejects_symlink_escaping_media_dir(self) -> None:
        link = self.media_dir / "escape.jpg"
        os.symlink(self.root / "secret.jpg", link)
        self.assertIsNone(safe_media_path(self.media_dir, "escape.jpg"))


class ListMediaTests(unittest.TestCase):
    def test_lists_newest_first_and_filters_by_type(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            media_dir = Path(tmpdir)
            old_shot = media_dir / "20261006T140000Z-screenshot-aaaa1111.jpg"
            new_shot = media_dir / "20261006T140100Z-screenshot-bbbb2222.jpg"
            replay = media_dir / "20261006T140200Z-replay-cccc3333.mp4"
            partial = media_dir / "20261006T140300Z-replay-dddd4444.mp4.part"
            for i, path in enumerate((old_shot, new_shot, replay, partial)):
                path.write_bytes(b"x")
                os.utime(path, (1_000_000 + i, 1_000_000 + i))
            (media_dir / "readme.txt").write_text("ignored")

            self.assertEqual(list_media(media_dir), [replay, new_shot, old_shot])
            self.assertEqual(list_media(media_dir, "screenshot"), [new_shot, old_shot])
            self.assertEqual(latest_media(media_dir, "replay"), replay)

    def test_missing_dir_is_empty(self) -> None:
        self.assertEqual(list_media(Path("/nonexistent/snapback")), [])
        self.assertIsNone(latest_media(Path("/nonexistent/snapback"), "replay"))


if __name__ == "__main__":
    unittest.main()
