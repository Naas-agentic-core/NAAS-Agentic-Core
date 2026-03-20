"""اختبارات تكامل مصغرة لتأكيد تمرير traceparent داخل بوابة API."""

from __future__ import annotations

import pytest
from fastapi.responses import PlainTextResponse
from fastapi.testclient import TestClient

from microservices.api_gateway import main
from microservices.api_gateway.security import verify_gateway_request


def test_gateway_generates_traceparent_when_missing(monkeypatch) -> None:
    """يتأكد من توليد traceparent عند غيابه وتمريره إلى طبقة التحويل."""
    captured: dict[str, str] = {}

    async def fake_forward(request, *_args, **_kwargs):
        captured["traceparent"] = getattr(request.state, "traceparent", "")
        return PlainTextResponse("ok")

    monkeypatch.setattr(main.proxy_handler, "forward", fake_forward)
    main.app.dependency_overrides[verify_gateway_request] = lambda: True
    client = TestClient(main.app)
    response = client.get("/api/v1/planning/test")
    main.app.dependency_overrides.clear()

    assert response.status_code == 200
    assert captured["traceparent"].startswith("00-")
    assert response.headers["traceparent"] == captured["traceparent"]


def test_gateway_forwards_existing_traceparent(monkeypatch) -> None:
    """يتأكد من الحفاظ على traceparent القادم من العميل دون تعديل."""
    incoming = "00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01"
    captured: dict[str, str] = {}

    async def fake_forward(request, *_args, **_kwargs):
        captured["traceparent"] = getattr(request.state, "traceparent", "")
        return PlainTextResponse("ok")

    monkeypatch.setattr(main.proxy_handler, "forward", fake_forward)
    main.app.dependency_overrides[verify_gateway_request] = lambda: True
    client = TestClient(main.app)
    response = client.get("/api/v1/planning/test", headers={"traceparent": incoming})
    main.app.dependency_overrides.clear()

    assert response.status_code == 200
    assert captured["traceparent"] == incoming
    assert response.headers["traceparent"] == incoming


@pytest.mark.asyncio
async def test_gateway_lifespan_skips_startup_probe_in_testing(monkeypatch) -> None:
    """يتأكد من تعطيل فحص الخدمات الخارجية أثناء الاختبارات لتفادي التعليق في CI."""

    async def fail_if_called(*_args, **_kwargs):
        raise AssertionError("startup dependency probe should be skipped during testing")

    async def fake_close() -> None:
        return None

    monkeypatch.setattr(main.settings, "ENVIRONMENT", "testing")
    monkeypatch.delenv("SKIP_GATEWAY_STARTUP_PROBE", raising=False)
    monkeypatch.setattr(main.proxy_handler.client, "get", fail_if_called)
    monkeypatch.setattr(main.proxy_handler, "close", fake_close)

    async with main.lifespan(main.app):
        pass
