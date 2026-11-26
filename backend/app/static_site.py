"""Optionally serve the built frontend from the API's origin."""

import os
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles


def mount_frontend(app: FastAPI) -> None:
    directory = os.getenv("FRONTEND_DIST_PATH", "").strip()
    if not directory:
        return
    path = Path(directory).resolve()
    if not (path / "index.html").is_file():
        raise RuntimeError("프론트 빌드가 없습니다. frontend에서 npm ci 및 npm run build를 실행하세요.")
    # Called after the API routes. Unknown paths stay 404 rather than returning index.html.
    app.mount("/", StaticFiles(directory=path, html=True), name="frontend")
