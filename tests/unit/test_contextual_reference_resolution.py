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
