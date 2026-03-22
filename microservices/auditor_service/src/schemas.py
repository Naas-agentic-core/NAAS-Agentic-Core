from typing import Any

from pydantic import BaseModel, Field


class ReviewRequest(BaseModel):
    """
    Request payload for reviewing work or plans.
    """

    result: dict[str, object] = Field(
        ..., description="The execution result or proposed plan to review."
    )
    original_objective: str = Field(..., description="The original objective of the mission.")
    context: dict[str, object] = Field(
        default_factory=dict, description="Contextual information (shared memory)."
    )


class ReviewResponse(BaseModel):
    """
    Structured review feedback from the Auditor.
    """

    approved: bool = Field(..., description="Whether the work is approved.")
    feedback: str = Field(..., description="Detailed feedback in Arabic.")
    score: float = Field(..., ge=0.0, le=1.0, description="Quality score between 0.0 and 1.0.")
    final_response: str = Field(
        ..., description="A professional markdown-formatted response for the user."
    )


class ConsultRequest(BaseModel):
    """
    Request payload for safety/strategic consultation.
    """

    situation: str = Field(..., description="Description of the situation.")
    analysis: dict[str, object] = Field(..., description="Analysis data.")


class ConsultResponse(BaseModel):
    """
    Consultation recommendation.
    """

    recommendation: str = Field(..., description="Safety recommendation (English).")
    confidence: float = Field(..., ge=0.0, le=100.0, description="Confidence score (0-100).")
