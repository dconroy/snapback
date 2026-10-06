"""Helpers for finding and safely serving files in the media directory."""

from __future__ import annotations

import re
from pathlib import Path

MEDIA_SUFFIXES = (".jpg", ".mp4")
MEDIA_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]*\.(jpg|mp4)$")


def safe_media_path(media_dir: Path, filename: str) -> Path | None:
    """Return the path for ``filename`` inside ``media_dir``, or None if unsafe or missing."""
    if not MEDIA_NAME_RE.fullmatch(filename):
        return None
    root = media_dir.resolve()
    candidate = (root / filename).resolve()
    if candidate.parent != root or not candidate.is_file():
        return None
    return candidate


def list_media(media_dir: Path, media_type: str | None = None) -> list[Path]:
    """List captured media newest first, optionally filtered by type (e.g. "screenshot")."""
    if not media_dir.is_dir():
        return []
    items = []
    for path in media_dir.iterdir():
        if not MEDIA_NAME_RE.fullmatch(path.name) or not path.is_file():
            continue
        if media_type is not None and f"-{media_type}-" not in path.name:
            continue
        items.append(path)
    return sorted(items, key=lambda p: (p.stat().st_mtime, p.name), reverse=True)


def latest_media(media_dir: Path, media_type: str) -> Path | None:
    items = list_media(media_dir, media_type)
    return items[0] if items else None
