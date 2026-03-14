"""اختبارات دورة حياة relay داخل orchestrator main دون التأثير على المسارات الحرجة."""

from __future__ import annotations

from contextlib import asynccontextmanager

import pytest

from microservices.orchestrator_service import main


@pytest.mark.asyncio
async def test_run_outbox_relay_once_uses_settings_limits(monkeypatch) -> None:
    """يتأكد أن دورة relay المفردة تمرر إعدادات batch/retry إلى state manager."""

    captured: dict[str, int] = {}

    class _FakeManager:
        def __init__(self, session) -> None:
            _ = session

        async def relay_outbox_events(
            self,
            *,
            batch_size: int,
            max_failed_attempts: int,
            processing_timeout_seconds: int,
        ) -> dict[str, int]:
            captured["batch_size"] = batch_size
            captured["max_failed_attempts"] = max_failed_attempts
            captured["processing_timeout_seconds"] = processing_timeout_seconds
            return {"processed": 0, "published": 0, "failed": 0, "skipped": 0}

    @asynccontextmanager
    async def _fake_session_factory():
        yield object()

    monkeypatch.setattr(main, "MissionStateManager", _FakeManager)
    monkeypatch.setattr(main, "async_session_factory", _fake_session_factory)
    monkeypatch.setattr(main.settings, "OUTBOX_RELAY_BATCH_SIZE", 17)
    monkeypatch.setattr(main.settings, "OUTBOX_RELAY_MAX_FAILED_ATTEMPTS", 5)
    monkeypatch.setattr(main.settings, "OUTBOX_RELAY_PROCESSING_TIMEOUT_SECONDS", 123)

    summary = await main._run_outbox_relay_once()

    assert summary == {"processed": 0, "published": 0, "failed": 0, "skipped": 0}
    assert captured == {"batch_size": 17, "max_failed_attempts": 5, "processing_timeout_seconds": 123}
