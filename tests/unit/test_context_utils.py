from microservices.orchestrator_service.src.api.context_utils import (
    _extract_client_context_messages,
    _merge_history_with_client_context,
)


def test_extract_client_context_messages_limits_and_sanitizes() -> None:
    payload = {
        "client_context_messages": [
            {"role": "system", "content": "ignore"},
            {"role": "user", "content": "  أين تقع فرنسا؟  "},
            {"role": "assistant", "content": "تقع في أوروبا."},
            {"role": "user", "content": ""},
        ]
    }

    extracted = _extract_client_context_messages(payload)

    assert extracted == [
        {"role": "user", "content": "أين تقع فرنسا؟"},
        {"role": "assistant", "content": "تقع في أوروبا."},
    ]


def test_merge_history_rejects_unrelated_client_context() -> None:
    persisted = [
        {"role": "user", "content": "أين تقع الجزائر؟"},
        {"role": "assistant", "content": "تقع في شمال أفريقيا."},
    ]
    unrelated = [
        {"role": "user", "content": "السلام عليكم"},
        {"role": "assistant", "content": "وعليكم السلام"},
        {"role": "user", "content": "أين تقع فرنسا؟"},
    ]

    merged = _merge_history_with_client_context(persisted, unrelated)

    assert merged == persisted


def test_merge_history_accepts_only_tail_after_overlap() -> None:
    persisted = [
        {"role": "user", "content": "أين تقع فرنسا؟"},
        {"role": "assistant", "content": "تقع في أوروبا."},
    ]
    client_context = [
        {"role": "user", "content": "نص قديم من صفحة أخرى"},
        {"role": "assistant", "content": "رد غير متعلق"},
        {"role": "user", "content": "أين تقع فرنسا؟"},
        {"role": "assistant", "content": "تقع في أوروبا."},
        {"role": "user", "content": "ما هي عاصمتها؟"},
    ]

    merged = _merge_history_with_client_context(persisted, client_context)

    assert merged[-1] == {"role": "user", "content": "ما هي عاصمتها؟"}
    assert {"role": "user", "content": "نص قديم من صفحة أخرى"} not in merged
