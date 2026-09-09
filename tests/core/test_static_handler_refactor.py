# tests/core/test_static_handler_refactor.py

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.static_handler import setup_static_files


# Disable auto-use fixtures from conftest for this module to avoid DB overhead/errors
# We do this by overriding them with empty fixtures
@pytest.fixture(autouse=True)
def init_db():
    pass


@pytest.fixture(autouse=True)
def clean_db():
    pass


@pytest.fixture
def app_with_static(tmp_path):
    app = FastAPI()
    # Create dummy static structure
    static_dir = tmp_path / "static"
    static_dir.mkdir()
    (static_dir / "index.html").write_text("<html>Index</html>")
    (static_dir / "css").mkdir()
    (static_dir / "css/style.css").write_text("body {}")

    setup_static_files(app, static_dir=str(static_dir))
    return app


def test_serve_index_at_root(app_with_static):
    client = TestClient(app_with_static)
    response = client.get("/")
    assert response.status_code == 200
    assert response.text == "<html>Index</html>"


def test_serve_static_asset(app_with_static):
    client = TestClient(app_with_static)
    response = client.get("/css/style.css")
    assert response.status_code == 200
    assert response.text == "body {}"


def test_spa_fallback_for_routes(app_with_static):
    client = TestClient(app_with_static)
    # Typically SPA routes return index.html
    response = client.get("/dashboard/user")
    assert response.status_code == 200
    assert response.text == "<html>Index</html>"


def test_api_404_no_fallback(app_with_static):
    client = TestClient(app_with_static)
    response = client.get("/api/v1/missing")
    assert response.status_code == 404
    # Should NOT return index.html
    assert response.text != "<html>Index</html>"


def test_nested_api_404_no_fallback(app_with_static):
    client = TestClient(app_with_static)
    response = client.get("/admin/api/chat/ws")
    assert response.status_code == 404
    assert response.text != "<html>Index</html>"


def test_directory_traversal_protection(app_with_static):
    """
    Test that path traversal attempts (containing '..') are rejected or handled safely.
    The goal is to ensure we don't serve files outside the static directory.
    """
    client = TestClient(app_with_static)

    # Case 1: Attempt to access a file outside via traversal
    # Note: Modern clients/frameworks normalize paths before they hit the app logic.
    # If the client normalizes "/../etc/passwd" to "/etc/passwd", the handler will receive "/etc/passwd".
    # The handler constructs potential_path = static_dir + "/etc/passwd".
    # This path does not exist inside static_dir, so it should be treated as an SPA route or 404.

    # If we want to test RAW traversal (where ".." actually reaches the handler),
    # we would need to manually invoke the handler or use a raw socket, which is complex here.
    # Instead, we verify that accessing a "suspicious" path behaves as expected (returns 404 or index.html, NOT the sensitive file).

    # Try to access a known system file (mocked by expectation)
    response = client.get("/../etc/passwd")

    # Depending on client normalization:
    # 1. Normalized to "/etc/passwd" -> Handler looks for STATIC/etc/passwd -> Not found -> SPA Fallback (200 Index) OR 404 if "etc" looks like api?
    # 2. Raw "/../etc/passwd" -> Handler detects traversal -> 404.

    # In this app, SPA fallback serves index.html for unknown routes.
    # So getting 200 (Index) is actually SAFE (we didn't leak /etc/passwd).
    # Getting 404 is also SAFE.
    # Getting the CONTENT of /etc/passwd would be UNSAFE.

    assert response.status_code in [200, 404]
    if response.status_code == 200:
        assert response.text == "<html>Index</html>"
        # Confirms we served the fallback, not the sensitive file.
