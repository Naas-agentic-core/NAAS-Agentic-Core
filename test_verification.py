import os
import sys

sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from microservices.orchestrator_service.src.api.context_utils import (
    _extract_client_context_messages,
    _merge_history_with_client_context,
)


def test_extract():
    payload = {
        "client_context_messages": [
            {"role": "user", "content": "أين تقع الجزائر؟"},
            {"role": "assistant", "content": "تقع الجزائر في شمال أفريقيا."},
            {"role": "user", "content": "ما هي عاصمتها؟"},
        ]
    }
    extracted = _extract_client_context_messages(payload)
    assert len(extracted) == 3
    assert extracted[-1]["content"] == "ما هي عاصمتها؟"


def test_merge():
    db_history = [
        {"role": "user", "content": "أين تقع الجزائر؟"},
        {"role": "assistant", "content": "تقع الجزائر في شمال أفريقيا."},
    ]
    client_context = [
        {"role": "user", "content": "أين تقع الجزائر؟"},
        {"role": "assistant", "content": "تقع الجزائر في شمال أفريقيا."},
        {"role": "user", "content": "ما هي عاصمتها؟"},
    ]
    merged = _merge_history_with_client_context(db_history, client_context)
    assert len(merged) == 3
    assert merged[-1]["content"] == "ما هي عاصمتها؟"


def test_graceful_degradation():
    db_history = [{"role": "user", "content": "أين تقع الجزائر؟"}]
    client_context = []
    merged = _merge_history_with_client_context(db_history, client_context)
    assert len(merged) == 1
    assert merged[0]["content"] == "أين تقع الجزائر؟"


if __name__ == "__main__":
    test_extract()
    test_merge()
    test_graceful_degradation()
    print("Tests passed!")
