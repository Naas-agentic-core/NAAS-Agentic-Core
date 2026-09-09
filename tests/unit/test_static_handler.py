from pathlib import Path

import pytest
from fastapi import HTTPException
from starlette.requests import Request

from app.core import static_handler


def _build_request(method: str) -> Request:
    scope = {
        "type": "http",
        "method": method,
        "path": "/",
        "headers": [],
    }
    return Request(scope)


def test_validate_static_directory_missing(tmp_path: Path) -> None:
    missing_dir = tmp_path / "missing"

    assert static_handler._validate_static_directory(str(missing_dir)) is False


def test_validate_static_directory_exists(tmp_path: Path) -> None:
    assert static_handler._validate_static_directory(str(tmp_path)) is True


def test_is_api_route_detection() -> None:
    assert static_handler._is_api_route("api") is True
    assert static_handler._is_api_route("/api/v1") is True
    assert static_handler._is_api_route("/v1/api") is True
    assert static_handler._is_api_route("/assets") is False


@pytest.mark.asyncio
async def test_serve_static_blocks_path_traversal(tmp_path: Path) -> None:
    request = _build_request("GET")

    with pytest.raises(HTTPException) as excinfo:
        await static_handler.serve_static(request, "../secrets.txt", static_dir=str(tmp_path))

    assert excinfo.value.status_code == 404


@pytest.mark.asyncio
async def test_serve_static_returns_none_for_missing(tmp_path: Path) -> None:
    request = _build_request("GET")

    response = await static_handler.serve_static(request, "missing.txt", static_dir=str(tmp_path))

    assert response is None


@pytest.mark.asyncio
async def test_serve_static_rejects_disallowed_method(tmp_path: Path) -> None:
    file_path = tmp_path / "index.html"
    file_path.write_text("hello")

    request = _build_request("POST")

    with pytest.raises(HTTPException) as excinfo:
        await static_handler.serve_static(request, "index.html", static_dir=str(tmp_path))

    assert excinfo.value.status_code == 405
