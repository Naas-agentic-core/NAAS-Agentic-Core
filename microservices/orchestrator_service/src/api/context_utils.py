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
    """يدمج سياق العميل بأمان مع التاريخ المخزّن مع منع تسرّب محادثات أخرى."""
    if not client_context:
        return persisted_history
    if not persisted_history:
        return client_context[-12:]

    persisted_tail = persisted_history[-3:] if len(persisted_history) >= 3 else persisted_history
    if not persisted_tail:
        return persisted_history

    overlap_index: int | None = None
    max_start = len(client_context) - len(persisted_tail)
    for start in range(max_start, -1, -1):
        window = client_context[start : start + len(persisted_tail)]
        if window == persisted_tail:
            overlap_index = start + len(persisted_tail)
            break

    if overlap_index is None:
        return persisted_history

    safe_client_tail = client_context[overlap_index:][-12:]
    merged_history = list(persisted_history)
    for message in safe_client_tail:
        if message not in merged_history:
            merged_history.append(message)
    return merged_history[-80:]
