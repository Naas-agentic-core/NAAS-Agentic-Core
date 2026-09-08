import re
import uuid
from unittest.mock import Mock

import httpx
import pytest

from shared.http_client import correlated


@pytest.fixture(autouse=True)
def isolate_provider(monkeypatch):
    monkeypatch.setattr(correlated, "_provider", None)


def test_explicit_id_wins_over_provider():
    def spy_provider():
        raise RuntimeError("Provider should not be called")

    correlated.set_correlation_provider(spy_provider)
    result = correlated.current_correlation_id(explicit="explicit-123")
    assert result == "explicit-123"


def test_explicit_falsy_falls_through_to_provider():
    provider = Mock(return_value="ambient-123")
    correlated.set_correlation_provider(provider)

    result = correlated.current_correlation_id(explicit="")
    assert result == "ambient-123"
    provider.assert_called_once()

    provider.reset_mock()
    result = correlated.current_correlation_id(explicit=None)
    assert result == "ambient-123"
    provider.assert_called_once()


def test_provider_returns_value():
    correlated.set_correlation_provider(lambda: "ambient-456")
    result = correlated.current_correlation_id()
    assert result == "ambient-456"


@pytest.mark.parametrize("falsy_value", [None, ""])
def test_provider_returns_none_or_falsy_falls_back_to_generated(falsy_value):
    correlated.set_correlation_provider(lambda: falsy_value)
    result = correlated.current_correlation_id()
    assert uuid.UUID(result)


def test_provider_exception_falls_back_to_generated_uuid():
    def raising_provider():
        raise ValueError("Oops")

    correlated.set_correlation_provider(raising_provider)
    result = correlated.current_correlation_id()
    assert uuid.UUID(result)


def test_provider_base_exception_not_swallowed():
    def base_raising_provider():
        raise KeyboardInterrupt()

    correlated.set_correlation_provider(base_raising_provider)
    with pytest.raises(KeyboardInterrupt):
        correlated.current_correlation_id()


def test_generated_path_is_valid_uuid_and_unique():
    result1 = correlated.current_correlation_id()
    result2 = correlated.current_correlation_id()

    assert uuid.UUID(result1)
    assert uuid.UUID(result2)
    assert result1 != result2


def test_provider_is_called_at_most_once_per_call():
    provider = Mock(return_value="ambient-value")
    correlated.set_correlation_provider(provider)

    correlated.current_correlation_id()
    provider.assert_called_once()


def test_traceparent_format_and_determinism(monkeypatch):
    correlation_id = "test-1234-abcd"

    # Mock uuid.uuid4 to have deterministic span id (since it generates one internally)
    mock_uuid = Mock()
    mock_uuid.hex = "11223344556677889900aabbccddeeff"
    monkeypatch.setattr(uuid, "uuid4", lambda: mock_uuid)

    result1 = correlated._traceparent(correlation_id)
    result2 = correlated._traceparent(correlation_id)

    assert re.match(r"^00-[0-9a-f]{32}-[0-9a-f]{16}-0[01]$", result1)
    # The trace-id part should be deterministic based on the correlation_id
    assert result1 == result2

    # Different correlation id should yield a different traceparent
    result3 = correlated._traceparent("different-id")
    assert result1 != result3


def test_correlation_headers_formats_correctly(monkeypatch):
    mock_uuid = Mock()
    mock_uuid.hex = "00000000000000000000000000000000"
    monkeypatch.setattr(uuid, "uuid4", lambda: mock_uuid)

    extra_headers = {"Other-Header": "value", "X-Correlation-ID": "explicit-in-extra"}
    headers = correlated.correlation_headers(extra_headers)

    assert headers["Other-Header"] == "value"
    assert headers["X-Correlation-ID"] == "explicit-in-extra"
    assert "traceparent" in headers

    # Check traceparent format using regex
    assert re.match(r"^00-[0-9a-f]{32}-[0-9a-f]{16}-0[01]$", headers["traceparent"])

    # Explicit id wins over inbound if provided
    headers = correlated.correlation_headers(extra_headers, correlation_id="explicit-kwargs")
    assert headers["X-Correlation-ID"] == "explicit-kwargs"


@pytest.mark.asyncio
async def test_correlated_client_sets_headers_and_closes():
    correlated.set_correlation_provider(lambda: "ambient-id")

    def mock_handler(request):
        return httpx.Response(200, json={"status": "ok"})

    transport = httpx.MockTransport(mock_handler)

    async with correlated.correlated_client(
        transport=transport, correlation_id="explicit-context-id"
    ) as client:
        # Before we actually send a request, let's verify that the client has the headers injected
        assert client.headers["X-Correlation-ID"] == "explicit-context-id"
        assert "traceparent" in client.headers

        # Send a dummy request to confirm it on the wire
        response = await client.get("http://testserver/")
        assert response.status_code == 200
        assert response.request.headers["X-Correlation-ID"] == "explicit-context-id"
        assert "traceparent" in response.request.headers

        client_ref = client

    # Ensure client closed on context exit
    assert client_ref.is_closed is True


@pytest.mark.asyncio
async def test_correlated_client_uses_ambient_when_no_explicit():
    correlated.set_correlation_provider(lambda: "ambient-id-for-client")

    def mock_handler(request):
        return httpx.Response(200, json={"status": "ok"})

    transport = httpx.MockTransport(mock_handler)

    async with correlated.correlated_client(transport=transport) as client:
        assert client.headers["X-Correlation-ID"] == "ambient-id-for-client"
        assert "traceparent" in client.headers


def test_set_correlation_provider_can_reset_to_none():
    correlated.set_correlation_provider(lambda: "ambient")
    assert correlated._provider is not None

    correlated.set_correlation_provider(None)
    assert correlated._provider is None

    # Should fallback to generated uuid
    result = correlated.current_correlation_id()
    assert uuid.UUID(result)
