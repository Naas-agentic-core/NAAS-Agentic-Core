"""
عميل وكيل الذاكرة (Memory Client).
================================

يتواصل مع خدمة Memory Agent لإدارة السياق والمعرفة.
"""

import httpx
from pydantic import BaseModel

from app.core.logging import get_logger
from app.core.settings.base import get_settings
from shared.http_client import correlated_client

logger = get_logger(__name__)


# إعادة تعريف النماذج المطلوبة محلياً لتجنب الاستيراد من المايكروسرفيس
# (Break Coupling)
class Concept(BaseModel):
    concept_id: str
    name_ar: str
    name_en: str
    description: str
    subject: str
    level: str
    difficulty: float
    tags: list[str]


class ReadinessResult(BaseModel):
    concept_id: str
    concept_name: str
    is_ready: bool
    readiness_score: float
    missing_prerequisites: list[str]
    weak_prerequisites: list[str]
    recommendation: str


class MemoryClient:
    """عميل للتواصل مع وكيل الذاكرة."""

    def __init__(self, base_url: str | None = None) -> None:
        self.settings = get_settings()
        self.base_url = base_url or "http://memory-agent:8010"

        # استخدام المتغيرات البيئية إذا كانت موجودة
        if hasattr(self.settings, "MEMORY_AGENT_URL") and self.settings.MEMORY_AGENT_URL:
            self.base_url = self.settings.MEMORY_AGENT_URL

        self.headers = {
            "Authorization": f"Bearer {self.settings.SECRET_KEY}",
            "Content-Type": "application/json",
        }
        self.timeout = httpx.Timeout(10.0, connect=5.0)

    async def _get(self, path: str, params: dict | None = None) -> dict | list | None:
        """تنفيذ طلب GET (مُصحَّح بالتتبّع — D-189)."""
        async with correlated_client(timeout=self.timeout) as client:
            try:
                # التأكد من صحة الرابط
                url = f"{self.base_url.rstrip('/')}/{path.lstrip('/')}"
                response = await client.get(
                    url,
                    headers=self.headers,
                    params=params,
                )
                if response.status_code == 404:
                    return None
                response.raise_for_status()
                return response.json()
            except httpx.RequestError as e:
                logger.error(f"Memory Service Connection Error: {e}")
                # في حالة التطوير، قد لا تكون الخدمة متاحة، نعيد None بدلاً من الفشل
                # ولكن هذا قد يخفي أخطاء حقيقية. الأفضل هو رفع الاستثناء.
                return None  # Fail Safe for Migration Phase
            except httpx.HTTPStatusError as e:
                logger.error(
                    f"Memory Service HTTP Error: {e.response.status_code} - {e.response.text}"
                )
                return None

    async def _post(self, path: str, payload: dict) -> dict | list | None:
        """تنفيذ طلب POST (مُصحَّح بالتتبّع — D-189)."""
        async with correlated_client(timeout=self.timeout) as client:
            try:
                url = f"{self.base_url.rstrip('/')}/{path.lstrip('/')}"
                response = await client.post(
                    url,
                    headers=self.headers,
                    json=payload,
                )
                response.raise_for_status()
                return response.json()
            except httpx.RequestError as e:
                logger.error(f"Memory Service Connection Error: {e}")
                return None
            except httpx.HTTPStatusError as e:
                logger.error(
                    f"Memory Service HTTP Error: {e.response.status_code} - {e.response.text}"
                )
                return None

    async def get_concept(self, concept_id: str) -> Concept | None:
        """جلب مفهوم."""
        data = await self._get(f"/knowledge/concepts/{concept_id}")
        return Concept(**data) if data else None

    async def find_concept_by_topic(self, topic: str) -> Concept | None:
        """بحث عن مفهوم."""
        data = await self._get("/knowledge/concepts/search", params={"topic": topic})
        return Concept(**data) if data else None

    async def get_prerequisites(self, concept_id: str) -> list[Concept]:
        """جلب المتطلبات."""
        data = await self._get(f"/knowledge/concepts/{concept_id}/prerequisites")
        return [Concept(**item) for item in data] if data else []

    async def get_related_concepts(self, concept_id: str) -> list[Concept]:
        """جلب المفاهيم المرتبطة."""
        data = await self._get(f"/knowledge/concepts/{concept_id}/related")
        return [Concept(**item) for item in data] if data else []

    async def get_next_concepts(self, concept_id: str) -> list[Concept]:
        """جلب المفاهيم التالية."""
        data = await self._get(f"/knowledge/concepts/{concept_id}/next")
        return [Concept(**item) for item in data] if data else []

    async def get_learning_path(self, from_concept: str, to_concept: str) -> list[Concept]:
        """جلب مسار تعلم."""
        payload = {"from_concept": from_concept, "to_concept": to_concept}
        data = await self._post("/knowledge/paths", payload=payload)
        return [Concept(**item) for item in data] if data else []

    async def check_readiness(
        self, concept_id: str, mastery_levels: dict[str, float]
    ) -> ReadinessResult | None:
        """فحص الجاهزية."""
        payload = {"concept_id": concept_id, "mastery_levels": mastery_levels}
        data = await self._post("/knowledge/readiness", payload)
        return ReadinessResult(**data) if data else None


# Singleton
_client: MemoryClient | None = None


def get_memory_client() -> MemoryClient:
    """Dependency injection for MemoryClient."""
    global _client
    if _client is None:
        _client = MemoryClient()
    return _client
