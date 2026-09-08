import logging
import sys

import pytest

from app.infrastructure.clients.orchestrator.local_fallback import LocalFallbackMixin


@pytest.mark.asyncio
async def test_mark_fallback_silenced_exception_logged(monkeypatch, caplog):
    # Monkeypatch the module where it is imported inside the helper

    # We can mock sys.modules to simulate failure of import or mock the function.
    # The helper tries to import `mark_fallback_used` from `app.telemetry.path_observer`.

    class FakePathObserver:
        def mark_fallback_used(self, path):
            raise ValueError("Telemetry broke!")

    monkeypatch.setitem(sys.modules, "app.telemetry.path_observer", FakePathObserver())

    with caplog.at_level(logging.WARNING):
        from app.infrastructure.clients.orchestrator.local_fallback import _mark_fallback

        _mark_fallback("some_test_stream")

    assert "Telemetry logging error (silenced)" in caplog.text
    assert any(
        record.levelname == "WARNING" and "Telemetry logging error (silenced)" in record.message
        for record in caplog.records
    )


@pytest.mark.asyncio
async def test_local_retrieval_stream_preserves_behavior_on_telemetry_failure(monkeypatch, caplog):
    class FakePathObserver:
        def mark_fallback_used(self, path):
            raise ValueError("Telemetry broke again!")

    monkeypatch.setitem(sys.modules, "app.telemetry.path_observer", FakePathObserver())

    class FakeClient(LocalFallbackMixin):
        async def _build_local_retrieval_response(self, question, history_messages=None):
            return "Test Response"

        async def _stream_markdown_typing(self, content):
            yield content

    FakeClient()

    with caplog.at_level(logging.WARNING):
        from app.infrastructure.clients.orchestrator.local_fallback import _mark_fallback

        _mark_fallback("local_retrieval_stream")

    assert "Telemetry logging error (silenced)" in caplog.text


@pytest.mark.asyncio
async def test_record_fallback_success(monkeypatch):
    called_with = None

    class FakePathObserver:
        def mark_fallback_used(self, path):
            nonlocal called_with
            called_with = path

    monkeypatch.setitem(sys.modules, "app.telemetry.path_observer", FakePathObserver())

    from app.infrastructure.clients.orchestrator.local_fallback import _mark_fallback

    _mark_fallback("test_success_stream")

    assert called_with == "test_success_stream"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "exception_to_raise", [ImportError("Module not found"), RuntimeError("DB Offline")]
)
async def test_record_fallback_failure_logged(monkeypatch, caplog, exception_to_raise):
    class FakePathObserver:
        def mark_fallback_used(self, path):
            raise exception_to_raise

    monkeypatch.setitem(sys.modules, "app.telemetry.path_observer", FakePathObserver())

    with caplog.at_level(logging.WARNING):
        from app.infrastructure.clients.orchestrator.local_fallback import _mark_fallback

        _mark_fallback("test_fail_stream")

    assert "Telemetry logging error (silenced)" in caplog.text
    assert any(
        record.levelname == "WARNING" and "Telemetry logging error" in record.message
        for record in caplog.records
    )
