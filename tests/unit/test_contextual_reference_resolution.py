from __future__ import annotations

from app.services.chat.agents.orchestrator import OrchestratorAgent as AppOrchestratorAgent
from microservices.orchestrator_service.src.services.overmind.agents.orchestrator import (
    OrchestratorAgent as MicroserviceOrchestratorAgent,
)


def test_app_orchestrator_resolves_pronoun_from_last_user_message() -> None:
    agent = object.__new__(AppOrchestratorAgent)
    question = "كم عدد سكانها؟"
    context = {
        "history_messages": [
            {"role": "assistant", "content": "اذكر الدولة"},
            {"role": "user", "content": "الجزائر"},
        ]
    }

    resolved = agent._resolve_contextual_reference(question, context)

    assert "مرجع سياقي إلزامي" in resolved
    assert "الجزائر" in resolved


def test_microservice_orchestrator_resolves_pronoun_from_last_user_message() -> None:
    agent = object.__new__(MicroserviceOrchestratorAgent)
    question = "ما هي عاصمتها؟"
    context = {
        "history_messages": [
            {"role": "assistant", "content": "أي دولة تقصد؟"},
            {"role": "user", "content": "فرنسا"},
        ]
    }

    resolved = agent._resolve_contextual_reference(question, context)

    assert "مرجع سياقي إلزامي" in resolved
    assert "فرنسا" in resolved


def test_pronoun_resolution_is_noop_for_explicit_question() -> None:
    agent = object.__new__(AppOrchestratorAgent)
    question = "كم عدد سكان الجزائر؟"

    resolved = agent._resolve_contextual_reference(question, {"history_messages": []})

    assert resolved == question


def test_microservice_orchestrator_skips_current_question_and_uses_previous_anchor() -> None:
    agent = object.__new__(MicroserviceOrchestratorAgent)
    question = "كم عدد سكانها؟"
    context = {
        "history_messages": [
            {"role": "assistant", "content": "تقع فرنسا في أوروبا الغربية."},
            {"role": "user", "content": "كم عدد سكانها؟"},
        ]
    }

    resolved = agent._resolve_contextual_reference(question, context)

    assert "مرجع سياقي إلزامي" in resolved
    assert "تقع فرنسا في أوروبا الغربية." in resolved
    assert resolved.count("كم عدد سكانها؟") == 1


def test_microservice_orchestrator_resolves_demonstrative_followup() -> None:
    agent = object.__new__(MicroserviceOrchestratorAgent)
    question = "كم ولاية في هذه الدولة؟"
    context = {
        "history_messages": [
            {"role": "assistant", "content": "الجزائر تقع في شمال أفريقيا."},
            {"role": "user", "content": "كم ولاية في هذه الدولة؟"},
        ]
    }

    resolved = agent._resolve_contextual_reference(question, context)

    assert "مرجع سياقي إلزامي" in resolved
    assert "الجزائر تقع في شمال أفريقيا." in resolved


def test_app_orchestrator_resolves_vague_math_followup() -> None:
    agent = object.__new__(AppOrchestratorAgent)
    question = "كيف جاءت الدالة معدومة؟"
    context = {
        "history_messages": [
            {"role": "assistant", "content": "لأن x يساوي 0 فإن الدالة تنعدم في هذا الموضع."},
            {"role": "user", "content": "كيف جاءت الدالة معدومة؟"},
        ]
    }

    resolved = agent._resolve_contextual_reference(question, context)

    assert "مرجع سياقي إلزامي" in resolved
    assert "لأن x يساوي 0" in resolved


def test_microservice_orchestrator_injects_history_for_non_pronoun_followup() -> None:
    agent = object.__new__(MicroserviceOrchestratorAgent)
    question = "كم الولايات؟"
    context = {
        "history_messages": [
            {"role": "assistant", "content": "نحن نتحدث عن الجزائر."},
            {"role": "user", "content": "كم الولايات؟"},
        ]
    }

    resolved = agent._inject_recent_history_context(question, context)

    assert "سياق المحادثة السابق (موجز)" in resolved
    assert "نحن نتحدث عن الجزائر." in resolved
    assert "السؤال الحالي: كم الولايات؟" in resolved


def test_app_orchestrator_injects_history_for_non_pronoun_followup() -> None:
    agent = object.__new__(AppOrchestratorAgent)
    question = "ما السبب؟"
    context = {
        "history_messages": [
            {"role": "assistant", "content": "الدالة تصبح معدومة عندما x = 0."},
            {"role": "user", "content": "ما السبب؟"},
        ]
    }

    resolved = agent._inject_recent_history_context(question, context)

    assert "سياق المحادثة السابق (موجز)" in resolved
    assert "الدالة تصبح معدومة" in resolved
    assert "السؤال الحالي: ما السبب؟" in resolved
