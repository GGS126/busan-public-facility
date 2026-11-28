"""Deployment-only static hosting must not hide API errors or serve secret files."""

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

from app.static_site import mount_frontend


def site(tmp_path, monkeypatch):
    (tmp_path / "index.html").write_text("<html>frontend</html>", encoding="utf-8")
    (tmp_path / "assets").mkdir()
    (tmp_path / "assets" / "app.js").write_text("console.log('ok')", encoding="utf-8")
    monkeypatch.setenv("FRONTEND_DIST_PATH", str(tmp_path))
    return tmp_path


def test_static_root_and_assets_keep_api_routes(tmp_path, monkeypatch):
    site(tmp_path, monkeypatch)
    app = FastAPI()

    @app.get("/api/health")
    def health():
        return {"status": "ok"}

    @app.post("/api/facilities/search")
    def search():
        return {"results": []}

    mount_frontend(app)
    with TestClient(app) as client:
        assert client.get("/").text == "<html>frontend</html>"
        assert client.get("/assets/app.js").status_code == 200
        assert client.get("/api/health").json() == {"status": "ok"}
        wrong_method = client.get("/api/facilities/search")
        assert wrong_method.status_code == 405
        assert "POST" in wrong_method.headers["allow"]
        assert client.post("/api/health").status_code == 405
        for path in ("/api/unknown", "/missing.js", "/.env", "/backend/.env", "/database/seed.json"):
            assert client.get(path).status_code == 404


def test_api_only_mode_without_frontend(monkeypatch):
    monkeypatch.delenv("FRONTEND_DIST_PATH", raising=False)
    app = FastAPI()
    mount_frontend(app)
    assert TestClient(app).get("/").status_code == 404


def test_configured_but_missing_build_is_an_error(tmp_path, monkeypatch):
    monkeypatch.setenv("FRONTEND_DIST_PATH", str(tmp_path))
    with pytest.raises(RuntimeError, match="프론트 빌드"):
        mount_frontend(FastAPI())


def test_real_health_does_not_need_a_gemini_key(monkeypatch):
    from app import main

    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    response = TestClient(main.app).get("/api/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "facility_count": len(main.facilities)}
