"""اختبارات عقود قدرة استرجاع التمارين لضمان السلوك المتوافق."""

from __future__ import annotations

from app.services.capabilities.exercise_retrieval import (
    ExerciseRetrievalRequest,
    detect_exercise_retrieval,
    make_result,
)


def test_detect_exercise_retrieval_arabic() -> None:
    """يتعرف على الطلبات العربية الصريحة للتمارين."""
    decision = detect_exercise_retrieval(ExerciseRetrievalRequest(question="أعطني تمرين احتمالات"))
    assert decision.recognized is True


def test_detect_exercise_retrieval_mixed_language() -> None:
    """يدعم الطلبات المختلطة عربي/إنجليزي."""
    decision = detect_exercise_retrieval(
        ExerciseRetrievalRequest(question="أريد probability exercise with steps")
    )
    assert decision.recognized is True


def test_make_result_handles_no_result() -> None:
    """يعطي فشلًا حتميًا عند غياب نتيجة الاسترجاع."""
    result = make_result(None)
    assert result.success is False
    assert result.message is None


def test_make_result_keeps_message_when_available() -> None:
    """يحافظ على رسالة الاسترجاع كما هي لضمان التوافق."""
    result = make_result("تم العثور على تمرين.")
    assert result.success is True
    assert result.message == "تم العثور على تمرين."
