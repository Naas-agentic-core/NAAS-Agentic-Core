"""اختبارات حراسة معمارية للتأكد من عدم حجب حلقة الأحداث في عمليات DSPy."""

from __future__ import annotations

from pathlib import Path


def test_research_agent_uses_asyncio_to_thread_for_blocking_dspy_calls() -> None:
    """يتأكد أن عمليات DSPy الثقيلة في خدمة البحث تُنفّذ عبر asyncio.to_thread."""
    source = Path("microservices/research_agent/main.py").read_text(encoding="utf-8")
    assert "asyncio.to_thread" in source
