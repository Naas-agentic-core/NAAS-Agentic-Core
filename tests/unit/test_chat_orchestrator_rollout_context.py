"""اختبارات تثبت تمرير سياق rollout عند التفويض إلى orchestrator client."""

from __future__ import annotations

from collections.abc import AsyncGenerator

import pytest

from app.services.chat.intent_detector import ChatIntent, IntentResult
from app.services.chat.orchestrator import ChatOrchestrator


@pytest.mark.asyncio
async def test_orchestrator_passes_rollout_context_on_delegation(monkeypatch) -> None:
    """يتأكد أن التفويض ينقل سبب القرار والمرحلة لضمان التتبع الطرفي."""
    monkeypatch.setenv("CHAT_ORCHESTRATOR_ROLLOUT_ENABLED", "1")
    monkeypatch.setenv("CHAT_ORCHESTRATOR_PARITY_VERIFIED", "1")
    monkeypatch.setenv("CHAT_ORCHESTRATOR_CAPABILITY_LEVEL", "parity_ready")
    monkeypatch.setenv("CHAT_ORCHESTRATOR_CANARY_STAGE", "full")

    orchestrator = ChatOrchestrator()
    orchestrator._intent_detector = _StaticIntentDetector(ChatIntent.ADMIN_QUERY)

    captured_context: dict[str, object] = {}

    async def fake_chat_with_agent(
        *,
        question: str,
        user_id: int,
        conversation_id: int,
        history_messages: list[dict[str, str]],
        context: dict[str, object],
    ) -> AsyncGenerator[str, None]:
        captured_context.update(context)
        yield "تم التفويض"

    monkeypatch.setattr(
        "app.services.chat.orchestrator.orchestrator_client.chat_with_agent",
        fake_chat_with_agent,
    )

    chunks: list[str] = []
    async for chunk in orchestrator.process(
        question="كم عدد المستخدمين؟",
        user_id=99,
        conversation_id=123,
        ai_client=_DummyAIClient(),
        history_messages=[],
    ):
        if isinstance(chunk, str):
            chunks.append(chunk)

    rollout = captured_context.get("rollout")
    assert isinstance(rollout, dict)
    assert rollout.get("reason") == "canary_full"
    assert rollout.get("canary_percent") == 100
    assert rollout.get("stage") == "full"
    assert chunks == ["تم التفويض"]


class _StaticIntentDetector:
    """كاشف نية ثابت لتثبيت مسار الاختبار بدون اعتماد على regex."""

    def __init__(self, intent: ChatIntent) -> None:
        self._intent = intent

    async def detect(self, _question: str) -> IntentResult:
        return IntentResult(intent=self._intent, confidence=1.0, params={})


class _DummyAIClient:
    """عميل صوري يُستخدم فقط لتلبية توقيع الدالة تحت الاختبار."""
