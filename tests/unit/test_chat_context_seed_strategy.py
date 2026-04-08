"""اختبارات استراتيجية زرع السياق لحماية المحادثة عند غياب checkpointer."""

from __future__ import annotations

import pytest
from langchain_core.messages import AIMessage, HumanMessage

from microservices.orchestrator_service.src.api import routes


def test_build_graph_messages_includes_short_anchor_with_checkpointer() -> None:
    """يتأكد من إبقاء مرساة سياقية قصيرة حتى مع checkpointer فعّال."""
    messages = routes._build_graph_messages(
        objective="ما هي عاصمتها؟",
        history_messages=[
            {"role": "user", "content": "أين تقع الجزائر؟"},
            {"role": "assistant", "content": "تقع الجزائر في شمال أفريقيا."},
        ],
        checkpointer_available=True,
        checkpoint_has_state=True,
    )

    assert len(messages) == 1
    assert isinstance(messages[0], HumanMessage)


def test_build_graph_messages_seeds_recent_history_without_checkpointer() -> None:
    """يتأكد من تمرير آخر الرسائل عند غياب checkpointer لمنع عمى السياق."""
    messages = routes._build_graph_messages(
        objective="ما هي عاصمتها؟",
        history_messages=[
            {"role": "user", "content": "أين تقع الجزائر؟"},
            {"role": "assistant", "content": "تقع الجزائر في شمال أفريقيا."},
        ],
        checkpointer_available=False,
        checkpoint_has_state=False,
    )

    assert len(messages) == 3
    assert isinstance(messages[0], HumanMessage)
    assert isinstance(messages[1], AIMessage)
    assert isinstance(messages[2], HumanMessage)
    assert messages[2].content == "ما هي عاصمتها؟"


def test_build_graph_messages_seeds_history_when_checkpointer_has_no_state() -> None:
    """يتأكد من زرع التاريخ إذا كان checkpointer متاحًا لكن الخيط جديد بلا حالة."""
    messages = routes._build_graph_messages(
        objective="ما هي عاصمتها؟",
        history_messages=[
            {"role": "user", "content": "أين تقع فرنسا؟"},
            {"role": "assistant", "content": "تقع فرنسا في أوروبا الغربية."},
        ],
        checkpointer_available=True,
        checkpoint_has_state=False,
    )
    assert len(messages) == 3


def test_build_graph_messages_forces_seed_on_ambiguous_followup() -> None:
    """يتأكد من عدم تكرار التاريخ عند توفر الـ checkpoint."""
    messages = routes._build_graph_messages(
        objective="ما هي عاصمتها؟",
        history_messages=[
            {"role": "user", "content": "أين تقع فرنسا؟"},
            {"role": "assistant", "content": "تقع فرنسا في أوروبا الغربية."},
        ],
        checkpointer_available=True,
        checkpoint_has_state=True,
    )
    assert len(messages) == 1


def test_resolve_effective_conversation_id_prefers_incoming_value() -> None:
    """يتأكد من أولوية conversation_id القادم من الرسالة عند صلاحيته."""
    resolved = routes._resolve_effective_conversation_id(
        incoming_value="42",
        sticky_value=7,
    )
    assert resolved == 42


def test_resolve_effective_conversation_id_falls_back_to_sticky_value() -> None:
    """يتأكد من استخدام conversation_id المحفوظ عند غياب قيمة صالحة من العميل."""
    resolved = routes._resolve_effective_conversation_id(
        incoming_value="",
        sticky_value=99,
    )
    assert resolved == 99


def test_resolve_thread_id_prefers_explicit_thread_key() -> None:
    """يتأكد من أولوية conversation_id لعزل المحادثات عن session عام مشترك."""
    context: routes.ChatRunContext = {
        "thread_id": "thread-abc",
        "session_id": "session-xyz",
        "conversation_id": 50,
        "user_id": 99,
    }
    resolved = routes._resolve_thread_id(context, fallback_conversation_id=7)
    assert resolved == "thread-abc"


def test_resolve_thread_id_uses_fallback_when_context_empty() -> None:
    """يتأكد من الرجوع إلى fallback conversation id عند غياب مفاتيح السياق."""
    context: routes.ChatRunContext = {"user_id": 99}
    resolved = routes._resolve_thread_id(context, fallback_conversation_id=123)
    assert resolved == "u99:c123"


@pytest.mark.asyncio
async def test_detect_checkpoint_state_when_unavailable(monkeypatch) -> None:
    """يتأكد من الإرجاع الآمن عند غياب checkpointer."""
    monkeypatch.setattr(routes, "get_checkpointer", lambda: None)
    available, has_state = await routes._detect_checkpoint_state("thread-1")
    assert available is False
    assert has_state is False


@pytest.mark.asyncio
async def test_detect_checkpoint_state_when_state_exists(monkeypatch) -> None:
    """يتأكد من اكتشاف حالة محفوظة عندما يعيد checkpointer قيمة غير فارغة."""

    class _FakeCheckpointer:
        async def aget_tuple(self, _config: dict[str, object]) -> object:
            return {"checkpoint": "exists"}

    monkeypatch.setattr(routes, "get_checkpointer", _FakeCheckpointer)
    available, has_state = await routes._detect_checkpoint_state("thread-1")
    assert available is True
    assert has_state is True


def test_is_ambiguous_followup_detects_capital_pronoun() -> None:
    """يتأكد من اكتشاف صيغة سؤال مرجعي تحتاج سياقًا سابقًا."""
    assert routes._is_ambiguous_followup("ما هي عاصمتها؟") is True


def test_is_ambiguous_followup_detects_population_pronoun() -> None:
    """يتأكد من التقاط أسئلة السكان الإحالية لمنع فقدان السياق في المتابعة."""
    assert routes._is_ambiguous_followup("كم عدد سكانها؟") is True


def test_is_ambiguous_followup_detects_demonstrative_state_reference() -> None:
    """يتأكد من التقاط أسئلة مثل (هذه الدولة) كمتابعة تعتمد على السياق السابق."""
    assert routes._is_ambiguous_followup("كم ولاية في هذه الدولة؟") is True


def test_is_ambiguous_followup_detects_vague_math_followup() -> None:
    """يتأكد من التقاط صيغ رياضية مبهمة تبدأ بـ(كيف جاءت) وتحتاج سياقًا سابقًا."""
    assert routes._is_ambiguous_followup("كيف جاءت الدالة معدومة؟") is True


def test_is_ambiguous_followup_rejects_explicit_query() -> None:
    """يتأكد من عدم تفعيل نمط المتابعة عند السؤال الواضح المستقل."""
    assert routes._is_ambiguous_followup("ما هي عاصمة فرنسا؟") is False


def test_extract_recent_entity_anchor_prefers_recent_user_entity() -> None:
    """يتأكد من استخراج كيان مرجعي من آخر رسالة مستخدم مناسبة."""
    anchor = routes._extract_recent_entity_anchor(
        [
            {"role": "user", "content": "حدثني عن الجزائر"},
            {"role": "assistant", "content": "الجزائر دولة عربية في شمال أفريقيا."},
            {"role": "user", "content": "وماذا عن فرنسا؟"},
        ]
    )
    assert anchor == "فرنسا"


def test_augment_ambiguous_objective_injects_anchor_when_entity_missing() -> None:
    """يتأكد من إضافة مرجع إلزامي عندما يكون السؤال إحاليًا بلا كيان صريح."""
    prepared = routes._augment_ambiguous_objective(
        "ما هي عاصمتها؟",
        [
            {"role": "user", "content": "حدثني عن الجزائر"},
            {"role": "assistant", "content": "تقع الجزائر في شمال أفريقيا."},
        ],
    )
    assert "مرجع سياقي إلزامي" in prepared
    assert "الجزائر" in prepared


def test_augment_ambiguous_objective_keeps_explicit_entity_unchanged() -> None:
    """يتأكد من عدم تعديل السؤال عندما يكون الكيان مذكورًا صراحةً."""
    prepared = routes._augment_ambiguous_objective(
        "ما هي عاصمة فرنسا؟",
        [{"role": "user", "content": "حدثني عن الجزائر"}],
    )
    assert prepared == "ما هي عاصمة فرنسا؟"
