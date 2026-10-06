"""Snapback local web app: one page, two buttons, a tiny JSON API."""

from __future__ import annotations

import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, Response

from .capture import CaptureConfig, CaptureEngine, CaptureError, DeviceBusyError, MediaItem
from .media import safe_media_path

STATIC_DIR = Path(__file__).parent / "static"
MEDIA_TYPES = {".jpg": "image/jpeg", ".mp4": "video/mp4"}
NO_STORE = {"Cache-Control": "no-store"}


def media_json(item: MediaItem | None) -> dict[str, Any] | None:
    if item is None:
        return None
    data = item.to_dict()
    data.pop("path", None)
    data["url"] = f"/media/{item.filename}"
    return data


def create_app(engine: CaptureEngine | None = None, start_buffer: bool | None = None) -> FastAPI:
    engine = engine or CaptureEngine(CaptureConfig.from_env())
    if start_buffer is None:
        start_buffer = os.environ.get("SNAPBACK_START_BUFFER", "1") != "0"

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        if start_buffer:
            engine.start_buffer()
        try:
            yield
        finally:
            engine.stop_buffer()

    app = FastAPI(title="Snapback", lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)
    app.state.engine = engine

    def run_capture(action) -> dict[str, Any]:
        try:
            return media_json(action())
        except DeviceBusyError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except CaptureError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc

    @app.get("/", include_in_schema=False)
    def index() -> FileResponse:
        return FileResponse(STATIC_DIR / "index.html", headers={"Cache-Control": "no-store"})

    @app.get("/api/status")
    def status() -> dict[str, Any]:
        data = engine.status()
        data["latest_screenshot"] = media_json(data["latest_screenshot"])
        data["latest_replay"] = media_json(data["latest_replay"])
        return data

    @app.post("/api/screenshot")
    def screenshot() -> dict[str, Any]:
        return run_capture(engine.take_screenshot)

    @app.post("/api/replay")
    def replay() -> dict[str, Any]:
        return run_capture(engine.save_replay)

    @app.get("/live/frame.jpg")
    def live_frame() -> Response:
        data = engine.live_frame()
        if data is None:
            raise HTTPException(status_code=503, detail="no live frame from the rolling buffer")
        return Response(data, media_type="image/jpeg", headers=NO_STORE)

    @app.get("/live/stream.m3u8")
    def live_playlist() -> Response:
        playlist = engine.live_playlist()
        if playlist is None:
            raise HTTPException(status_code=503, detail="rolling buffer has no footage yet")
        return Response(playlist, media_type="application/vnd.apple.mpegurl", headers=NO_STORE)

    @app.get("/live/{filename}")
    def live_segment(filename: str) -> FileResponse:
        path = engine.live_segment(filename)
        if path is None:
            raise HTTPException(status_code=404, detail="not found")
        return FileResponse(path, media_type="video/mp2t")

    @app.get("/media/{filename}")
    def media(filename: str) -> FileResponse:
        path = safe_media_path(engine.config.media_dir, filename)
        if path is None:
            raise HTTPException(status_code=404, detail="not found")
        return FileResponse(path, media_type=MEDIA_TYPES[path.suffix])

    return app


app = create_app()
