"""
موجهات المعرفة (Knowledge API).
=============================
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from microservices.memory_agent.src.domain.concept_graph import Concept
from microservices.memory_agent.src.schemas.knowledge_schemas import (
    ReadinessRequest,
    ReadinessResponse,
)
from microservices.memory_agent.src.services.knowledge_service import KnowledgeService

router = APIRouter(prefix="/knowledge", tags=["Knowledge"])


def get_service() -> KnowledgeService:
    """Dependency injection for KnowledgeService."""
    return KnowledgeService()


@router.get("/concepts/search", response_model=Concept)
async def find_concept(
    topic: str = Query(..., description="الموضوع للبحث عنه"),
    service: KnowledgeService = Depends(get_service),
):
    """يبحث عن مفهوم."""
    concept = await service.find_concept_by_topic(topic)
    if not concept:
        raise HTTPException(status_code=404, detail="Concept not found")
    return concept


@router.get("/concepts/{concept_id}", response_model=Concept)
async def get_concept(
    concept_id: str,
    service: KnowledgeService = Depends(get_service),
):
    """يحصل على مفهوم بواسطة معرفه."""
    concept = await service.get_concept(concept_id)
    if not concept:
        raise HTTPException(status_code=404, detail="Concept not found")
    return concept


@router.get("/concepts/{concept_id}/prerequisites", response_model=list[Concept])
async def get_prerequisites(
    concept_id: str,
    service: KnowledgeService = Depends(get_service),
):
    """يحصل على المتطلبات السابقة."""
    return await service.get_prerequisites(concept_id)


@router.get("/concepts/{concept_id}/related", response_model=list[Concept])
async def get_related(
    concept_id: str,
    service: KnowledgeService = Depends(get_service),
):
    """يحصل على المفاهيم المرتبطة."""
    return await service.get_related_concepts(concept_id)


@router.get("/concepts/{concept_id}/next", response_model=list[Concept])
async def get_next(
    concept_id: str,
    service: KnowledgeService = Depends(get_service),
):
    """يحصل على المفاهيم التالية."""
    return await service.get_next_concepts(concept_id)


class PathRequest(BaseModel):
    from_concept: str
    to_concept: str


@router.post("/paths", response_model=list[Concept])
async def get_learning_path(
    payload: PathRequest,
    service: KnowledgeService = Depends(get_service),
):
    """يجد مسار تعلم."""
    return await service.get_learning_path(payload.from_concept, payload.to_concept)


@router.post("/readiness", response_model=ReadinessResponse)
async def check_readiness(
    payload: ReadinessRequest,
    service: KnowledgeService = Depends(get_service),
):
    """يتحقق من جاهزية الطالب لمفهوم معين."""
    return await service.check_readiness(payload)
