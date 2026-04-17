from __future__ import annotations

from microservices.orchestrator_service.src.api.routes import _context_gap_reason_for_followup


def test_context_gap_detects_missing_anchor_for_ambiguous_followup() -> None:
    reason = _context_gap_reason_for_followup("ما هي عاصمتها؟", history_messages=[])
    assert reason == "MISSING_ENTITY_ANCHOR"


def test_context_gap_allows_ambiguous_followup_when_anchor_exists() -> None:
    history = [
        {"role": "user", "content": "أين تقع الجزائر؟"},
        {"role": "assistant", "content": "تقع الجزائر في شمال أفريقيا."},
    ]
    reason = _context_gap_reason_for_followup("ما هي عاصمتها؟", history_messages=history)
    assert reason is None


def test_context_gap_allows_question_with_explicit_entity() -> None:
    reason = _context_gap_reason_for_followup("ما عاصمة الجزائر؟", history_messages=[])
    assert reason is None
