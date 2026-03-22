import logging

from pydantic import BaseModel, Field, field_validator, model_validator

logger = logging.getLogger("orchestrator.services.tools.schemas")


class SearchContentSchema(BaseModel):
    """
    Schema for the search_content tool.
    Strictly validates inputs and handles alias mapping (Adapter Layer).
    """

    q: str | None = Field(None, alias="query")
    level: str | None = None
    subject: str | None = None
    branch: str | None = None
    set_name: str | None = None
    year: int | None = None
    type: str | None = None
    lang: str | None = None
    limit: int = Field(10, ge=1, le=50)

    # Catch-all for extra fields to prevent crashes, but log them
    # This allows us to inspect what the LLM is hallucinating without breaking execution
    class Config:
        extra = "ignore"
        populate_by_name = True

    @model_validator(mode="before")
    @classmethod
    def log_unexpected_fields(cls, data: object) -> object:
        if isinstance(data, dict):
            known_fields = set(cls.model_fields.keys()) | {"query"}  # Add known aliases
            unexpected = set(data.keys()) - known_fields
            if unexpected:
                logger.warning(f"SearchContentSchema received unexpected fields: {unexpected}")
        return data

    @field_validator("year", mode="before")
    @classmethod
    def parse_year(cls, v):
        if v is None:
            return None
        if isinstance(v, str):
            if v.isdigit():
                return int(v)
            return None  # Fail gracefully or raise error depending on strictness policy
        return v
