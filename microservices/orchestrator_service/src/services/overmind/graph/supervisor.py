"""Supervisor routing for Overmind graph."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Iterable
from types import SimpleNamespace

try:
    import dspy
except ModuleNotFoundError:

    def _dspy_input_field(*_: object, **__: object) -> str:
        return ""

    def _dspy_output_field(*_: object, **__: object) -> str:
        return ""

    def _dspy_chain_of_thought(*_: object, **__: object):
        def _runner(**_: object) -> SimpleNamespace:
            return SimpleNamespace(
                intent="educational",
                confidence=0.0,
                resolved_question="",
            )

        return _runner

    class _DSPySettings:
        def __init__(self) -> None:
            self.lm: object | None = None

        def configure(self, *, lm: object | None = None) -> None:
            self.lm = lm

    class _DSPySignature:
        pass

    class _DSPyModule:
        Signature = _DSPySignature
        settings = _DSPySettings()
        InputField = staticmethod(_dspy_input_field)
        OutputField = staticmethod(_dspy_output_field)
        ChainOfThought = staticmethod(_dspy_chain_of_thought)

    dspy = _DSPyModule()  # type: ignore[assignment]

logger = logging.getLogger(__name__)

INTENT_THRESHOLDS: dict[str, float] = {
    "admin": 0.75,
    "general_knowledge": 0.60,
    "educational": 0.55,
    "chat": 0.65,
}


def _iter_recent_messages(messages: Iterable[object], limit: int = 6) -> list[object]:
    recent = list(messages)
    return recent[-limit:]


def _message_to_text(message: object) -> tuple[str, str]:
    if isinstance(message, dict):
        role = str(message.get("role", "user"))
        content = message.get("content", "")
        return role, str(content)

    role = getattr(message, "type", getattr(message, "role", "user"))
    content = getattr(message, "content", "")
    return str(role), str(content)


def format_conversation_history(messages: list[object]) -> str:
    """Formats recent messages into a readable transcript."""
    parts: list[str] = []
    for message in _iter_recent_messages(messages, limit=6):
        role, content = _message_to_text(message)
        if not isinstance(content, str) or not content.strip():
            continue
        prefix = "User: " if role in ("human", "user") else "Assistant: "
        parts.append(f"{prefix}{content.strip()}")
    return "\n".join(parts)


class IntentClassifier(dspy.Signature):
    """Classify the user's intent into one of four mutually exclusive classes.

    - educational: BAC exercises, lessons, subjects, branches, school-years.
    - general_knowledge: general facts outside BAC content (geography, history, science, language).
    - admin: system metrics, service counts, operational information.
    - chat: greetings, thanks, small talk, no real question.
    """

    history: str = dspy.InputField(desc="Previous conversation context to resolve pronouns.")
    question: str = dspy.InputField(desc="Current user question.")
    intent: str = dspy.OutputField(
        desc="One of: educational | general_knowledge | admin | chat"
    )
    confidence: float = dspy.OutputField(desc="Confidence score from 0.0 to 1.0")
    resolved_question: str = dspy.OutputField(
        desc="Question rewritten with explicit entities resolved from history."
    )


class SupervisorNode:
    def __init__(self) -> None:
        self.dspy_classifier = dspy.ChainOfThought(IntentClassifier)

    async def __call__(self, state: dict) -> dict:
        """Route requests by intent and preserve the resolved query."""
        query = str(state.get("query", "")).strip()
        messages = state.get("messages", [])
        history = format_conversation_history(messages)

        if not query:
            return {"intent": "educational", "query": query}

        try:
            result = await asyncio.to_thread(
                self.dspy_classifier,
                history=history,
                question=query,
            )
            intent = str(getattr(result, "intent", "educational")).strip().lower()
            resolved_question = str(getattr(result, "resolved_question", "")).strip() or query
            try:
                confidence = float(getattr(result, "confidence", 0.0) or 0.0)
            except (TypeError, ValueError):
                confidence = 0.0

            threshold = INTENT_THRESHOLDS.get(intent, 0.60)
            if intent in INTENT_THRESHOLDS and confidence >= threshold:
                return {"intent": intent, "query": resolved_question}
        except Exception as exc:
            logger.debug("Supervisor intent classification failed: %s", exc)

        return {"intent": "educational", "query": query}
