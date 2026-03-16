"""اختبارات سلوك SupervisorNode لضمان عدم حجب الحلقة الحدثية."""

import importlib
import sys
from types import ModuleType, SimpleNamespace

import pytest


class _StubSignature:
    """يمثل بديلاً بسيطاً لتوقيع DSPy لأغراض الاختبار."""


class _StubField:
    """حقل وهمي يحاكي InputField/OutputField بدون سلوك إضافي."""

    def __call__(self, *args, **kwargs):
        return None


class _StubChainOfThought:
    """مُصنّف وهمي يعيد نتيجة افتراضية قابلة للضبط عبر الاختبار."""

    def __init__(self, _signature: object) -> None:
        self._result = SimpleNamespace(is_admin="false", confidence="0.0")

    def __call__(self, **kwargs):
        return self._result


def _load_graph_main_with_stubbed_dspy(monkeypatch: pytest.MonkeyPatch):
    """يحمّل وحدة graph.main بعد حقن بديل DSPy داخل sys.modules."""
    dspy_stub = ModuleType("dspy")
    dspy_stub.Signature = _StubSignature
    dspy_stub.InputField = _StubField()
    dspy_stub.OutputField = _StubField()
    dspy_stub.ChainOfThought = _StubChainOfThought
    monkeypatch.setitem(sys.modules, "dspy", dspy_stub)

    module_name = "microservices.orchestrator_service.src.services.overmind.graph.main"
    if module_name in sys.modules:
        del sys.modules[module_name]
    return importlib.import_module(module_name)


@pytest.mark.asyncio
async def test_supervisor_node_uses_to_thread_for_dspy(monkeypatch: pytest.MonkeyPatch) -> None:
    """يتحقق من أن تصنيف DSPy يتم عبر asyncio.to_thread وليس بشكل متزامن مباشر."""
    main = _load_graph_main_with_stubbed_dspy(monkeypatch)

    node = main.SupervisorNode()

    def classifier_stub(**kwargs):
        _ = kwargs
        return SimpleNamespace(is_admin="true", confidence="0.9")

    node.dspy_classifier = classifier_stub

    called: dict[str, bool] = {"to_thread": False}

    async def fake_to_thread(func, *args, **kwargs):
        called["to_thread"] = True
        return func(*args, **kwargs)

    monkeypatch.setattr(main.asyncio, "to_thread", fake_to_thread)

    result = await node({"query": "random query", "messages": []})

    assert called["to_thread"] is True
    assert result == {"intent": "admin"}


@pytest.mark.asyncio
async def test_supervisor_node_short_circuits_admin_guard(monkeypatch: pytest.MonkeyPatch) -> None:
    """يتحقق من أن الحارس الحتمي يسبق DSPy ويعيد نية إدارية مباشرة."""
    main = _load_graph_main_with_stubbed_dspy(monkeypatch)

    node = main.SupervisorNode()

    def forbidden_classifier(**kwargs):
        _ = kwargs
        raise RuntimeError("must not run")

    node.dspy_classifier = forbidden_classifier

    result = await node({"query": "كم عدد ملفات بايثون", "messages": []})

    assert result == {"intent": "admin"}
