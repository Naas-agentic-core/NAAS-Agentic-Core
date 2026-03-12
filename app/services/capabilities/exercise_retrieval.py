"""قدرة استرجاع التمارين التعليمية بعقد صريح وتدهور عادل متوافق مع الواجهات."""

from __future__ import annotations

from pydantic import Field

from app.core.schemas import RobustBaseModel


class ExerciseRetrievalRequest(RobustBaseModel):
    """طلب استرجاع تعليمي منسّق."""

    question: str = Field(..., min_length=1)


class ExerciseRetrievalDecision(RobustBaseModel):
    """قرار التعرف على نية الاسترجاع التعليمي."""

    recognized: bool


class ExerciseRetrievalResult(RobustBaseModel):
    """نتيجة استرجاع التمارين مع semantics واضحة."""

    success: bool
    message: str | None = None


def detect_exercise_retrieval(request: ExerciseRetrievalRequest) -> ExerciseRetrievalDecision:
    """يتعرف على أسئلة التمارين لضبط fallback eligibility بشكل حتمي."""
    normalized = request.question.strip().lower()
    retrieval_hints = (
        "تمرين",
        "تمارين",
        "درس",
        "احتمالات",
        "بكالوريا",
        "exercise",
        "lesson",
        "probability",
    )
    return ExerciseRetrievalDecision(recognized=any(hint in normalized for hint in retrieval_hints))


def make_result(raw_result: str | None) -> ExerciseRetrievalResult:
    """يحوّل النتيجة الخام إلى عقد موحد دون كسر السلوك التاريخي."""
    if raw_result is None or not raw_result.strip():
        return ExerciseRetrievalResult(success=False)
    return ExerciseRetrievalResult(success=True, message=raw_result)
