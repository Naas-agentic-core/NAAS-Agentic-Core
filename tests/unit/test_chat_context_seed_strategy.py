"""اختبارات استراتيجية زرع السياق لحماية المحادثة عند غياب checkpointer."""

from __future__ import annotations

from langchain_core.messages import AIMessage, HumanMessage

from microservices.orchestrator_service.src.api import routes


def test_build_graph_messages_uses_only_objective_with_checkpointer() -> None:
    """يتأكد من منع التكرار عند توفر checkpointer والاعتماد على thread history."""
    messages = routes._build_graph_messages(
        objective="ما هي عاصمتها؟",
        history_messages=[
            {"role": "user", "content": "أين تقع الجزائر؟"},
            {"role": "assistant", "content": "تقع الجزائر في شمال أفريقيا."},
        ],
        has_checkpointer=True,
    )

    assert len(messages) == 1
    assert isinstance(messages[0], HumanMessage)
    assert messages[0].content == "ما هي عاصمتها؟"


def test_build_graph_messages_seeds_recent_history_without_checkpointer() -> None:
    """يتأكد من تمرير آخر الرسائل عند غياب checkpointer لمنع عمى السياق."""
    messages = routes._build_graph_messages(
        objective="ما هي عاصمتها؟",
        history_messages=[
            {"role": "user", "content": "أين تقع الجزائر؟"},
            {"role": "assistant", "content": "تقع الجزائر في شمال أفريقيا."},
        ],
        has_checkpointer=False,
    )

    assert len(messages) == 3
    assert isinstance(messages[0], HumanMessage)
    assert isinstance(messages[1], AIMessage)
    assert isinstance(messages[2], HumanMessage)
    assert messages[2].content == "ما هي عاصمتها؟"


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
