"""
Context hydration utilities.
Ported from app/api/routers/customer_chat.py.
DO NOT modify without updating the monolith counterpart.
"""


def _extract_client_context_messages(payload: dict[str, object]) -> list[dict[str, str]]:
    """استخراج سياق المحادثة المرسل من الواجهة بشكل آمن ومحدود الحجم."""
    raw_context = payload.get("client_context_messages")
    if not isinstance(raw_context, list):
        return []

    sanitized: list[dict[str, str]] = []
    for item in raw_context:
        if not isinstance(item, dict):
            continue
        role = item.get("role")
        content = item.get("content")
        if role not in {"user", "assistant"}:
            continue
        if not isinstance(content, str):
            continue
        text = content.strip()
        if not text:
            continue
        sanitized.append({"role": role, "content": text})
        if len(sanitized) >= 50:
            break
    return sanitized


def _merge_history_with_client_context(
    persisted_history: list[dict[str, str]],
    client_context: list[dict[str, str]],
) -> list[dict[str, str]]:
    """دمج تاريخ قاعدة البيانات مع سياق العميل للحفاظ على الاستمرارية بدون تكرار."""
    if not client_context:
        return persisted_history
    if not persisted_history:
        return client_context

    merged_history = list(persisted_history)
    for message in client_context:
        if message not in merged_history:
            merged_history.append(message)
    return merged_history[-80:]
