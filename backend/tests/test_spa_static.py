from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from news_dashboard.main import SPAStaticFiles


def test_spa_static_falls_back_to_index_for_client_routes(tmp_path: Path) -> None:
    static_dir = tmp_path / "dist"
    static_dir.mkdir()
    (static_dir / "index.html").write_text("<div id='root'></div>", encoding="utf-8")
    (static_dir / "asset.txt").write_text("asset", encoding="utf-8")
    (static_dir / "favicon.ico").write_bytes(b"icon")

    app = FastAPI()
    app.mount("/", SPAStaticFiles(directory=static_dir, html=True), name="static")

    client = TestClient(app)

    route_response = client.get("/later")
    assert route_response.status_code == 200
    assert "<div id='root'></div>" in route_response.text

    asset_response = client.get("/asset.txt")
    assert asset_response.status_code == 200
    assert asset_response.text == "asset"

    favicon_response = client.get("/favicon.ico")
    assert favicon_response.status_code == 200
    assert favicon_response.content == b"icon"

    missing_asset_response = client.get("/assets/missing.js")
    assert missing_asset_response.status_code == 404

    api_response = client.get("/api/unknown")
    assert api_response.status_code == 404
