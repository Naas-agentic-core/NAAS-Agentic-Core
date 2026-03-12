"""عقود أحداث الدردشة المعيارية لمنع انجراف المخطط بين المسارات المختلفة."""

from __future__ import annotations

from enum import StrEnum
from typing import Literal

from pydantic import Field

from app.core.schemas import RobustBaseModel


class ChatEventType(StrEnum):
    """أنواع أحداث الدردشة المسموح بها في الواجهة الموحدة."""

    ASSISTANT_DELTA = "assistant_delta"
    ASSISTANT_FINAL = "assistant_final"
    ASSISTANT_ERROR = "assistant_error"
    STATUS = "status"


class ChatEventPayload(RobustBaseModel):
    """حمولة حدث الدردشة مع حقول متوافقة إضافية دون كسر العقود الحالية."""

    content: str | None = None
    details: str | None = None
    status_code: int | None = None
    request_id: str | None = None
    retry_hint: str | None = None


class ChatEventEnvelope(RobustBaseModel):
    """مغلف حدث الدردشة الموحّد عبر HTTP/WS/Orchestrator adapters."""

    type: ChatEventType = Field(..., description="نوع الحدث")
    payload: ChatEventPayload = Field(..., description="حمولة الحدث")
    contract_version: Literal["v1"] = Field("v1", description="نسخة عقد الحدث")
