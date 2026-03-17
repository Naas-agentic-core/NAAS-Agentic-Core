"""Regression: إزالة مسار WS المونوليثي تمنع stub المحلي نهائيًا."""

from fastapi.testclient import TestClient


def test_chat_stream_is_not_served_by_monolith_anymore(test_app) -> None:
    """يتحقق من أن المسار المحلي للدردشة أُزيل لتجنّب split-brain."""

    with TestClient(test_app) as client:
        response = client.get("/admin/api/chat/ws")
    assert response.status_code == 404
