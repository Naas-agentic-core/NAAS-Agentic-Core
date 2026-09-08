from pydantic import BaseModel, Field


class ReadinessRequest(BaseModel):
    """طلب فحص الجاهزية."""

    concept_id: str = Field(..., description="معرف المفهوم المراد تعلمه")
    mastery_levels: dict[str, float] = Field(
        ..., description="خريطة مستوى إتقان المفاهيم (concept_id -> score)"
    )


class BatchRelationsRequest(BaseModel):
    """طلب فحص العلاقات بالجملة."""

    concept_ids: list[str] = Field(..., description="قائمة معرفات المفاهيم")


class BatchRelationsResponse(BaseModel):
    """استجابة العلاقات بالجملة."""

    prerequisites: dict[str, list[str]] = Field(
        ...,
        description="المتطلبات السابقة لكل مفهوم (المفاتيح هي concept_id، والقيم هي قائمة المتطلبات)",
    )


class ReadinessResponse(BaseModel):
    """نتيجة فحص الجاهزية."""

    concept_id: str = Field(..., description="معرف المفهوم")
    concept_name: str = Field(..., description="اسم المفهوم")
    is_ready: bool = Field(..., description="هل الطالب جاهز؟")
    readiness_score: float = Field(..., ge=0.0, le=1.0, description="درجة الجاهزية")
    missing_prerequisites: list[str] = Field(..., description="أسماء المتطلبات المفقودة تماماً")
    weak_prerequisites: list[str] = Field(..., description="أسماء المتطلبات الضعيفة")
    recommendation: str = Field(..., description="توصية للطالب")
