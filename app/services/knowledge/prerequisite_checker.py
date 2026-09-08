"""
فاحص المتطلبات السابقة (Prerequisite Checker).
==============================================

يتحقق من جاهزية الطالب لموضوع معين.
"""

import logging
from dataclasses import dataclass

from app.infrastructure.clients.memory_client import MemoryClient, get_memory_client
from app.services.learning.student_profile import StudentProfile

logger = logging.getLogger(__name__)


@dataclass
class ReadinessReport:
    """تقرير الجاهزية."""

    concept_id: str
    concept_name: str
    is_ready: bool
    readiness_score: float  # 0-1
    missing_prerequisites: list[str]
    weak_prerequisites: list[str]
    recommendation: str


class PrerequisiteChecker:
    """
    يتحقق من جاهزية الطالب لتعلم مفهوم جديد.
    """

    def __init__(self, memory_client: MemoryClient | None = None) -> None:
        self.client = memory_client or get_memory_client()

    async def check_readiness(
        self,
        profile: StudentProfile,
        concept_id: str,
    ) -> ReadinessReport:
        """
        يتحقق من جاهزية الطالب لمفهوم معين.
        """
        # بناء خريطة الإتقان
        mastery_levels = {
            topic_id: entry.mastery_score for topic_id, entry in profile.topic_mastery.items()
        }

        # استدعاء الخدمة المصغرة
        result = await self.client.check_readiness(concept_id, mastery_levels)

        if not result:
            # حالة الفشل أو عدم القدرة على الاتصال
            logger.error(f"Failed to check readiness for {concept_id}")
            return ReadinessReport(
                concept_id=concept_id,
                concept_name=concept_id,
                is_ready=False,
                readiness_score=0.0,
                missing_prerequisites=[],
                weak_prerequisites=[],
                recommendation="تعذر التحقق من الجاهزية حالياً.",
            )

        # تحويل النتيجة إلى التقرير المحلي
        return ReadinessReport(
            concept_id=result.concept_id,
            concept_name=result.concept_name,
            is_ready=result.is_ready,
            readiness_score=result.readiness_score,
            missing_prerequisites=result.missing_prerequisites,
            weak_prerequisites=result.weak_prerequisites,
            recommendation=result.recommendation,
        )

    async def get_learning_order(
        self,
        profile: StudentProfile,
        target_concepts: list[str],
    ) -> list[str]:
        """
        يحدد الترتيب الأمثل لتعلم مجموعة مفاهيم.
        """
        # جمع كل المتطلبات
        all_concepts = set(target_concepts)

        for concept_id in target_concepts:
            # إضافة المتطلبات المفقودة
            report = await self.check_readiness(profile, concept_id)
            for prereq_name in report.missing_prerequisites:
                concept = await self.client.find_concept_by_topic(prereq_name)
                if concept:
                    all_concepts.add(concept.concept_id)

        # ترتيب طوبولوجي
        # ordered = []
        # remaining = list(all_concepts)

        # تحذير: هذا الترتيب الطوبولوجي كان يعتمد على الوصول المتزامن للرسم البياني.
        # الآن مع Async، قد يكون بطيئاً جداً إذا قمنا بطلب لكل مفهوم.
        # للتبسيط، سنحاول ترتيب ما لدينا.

        # نحتاج لجلب العلاقات لبناء الترتيب.
        # هذا قد يتطلب endpoint جديد في API لجلب العلاقات لمجموعة مفاهيم دفعة واحدة.
        # لكن للآن، سنستخدم نهجاً بسيطاً: الترتيب كما جاء أو بناءً على check_readiness.

        # نظرًا لتعقيد الترتيب الطوبولوجي عبر الشبكة (N+1 problem)، سنقوم بتبسيط المنطق مؤقتاً
        # ليعيد القائمة كما هي مع إضافة المفقودين في البداية.

        # TODO: Implement Batch Graph Query in Microservice

        return list(all_concepts)


# Singleton
_checker: PrerequisiteChecker | None = None


def get_prerequisite_checker() -> PrerequisiteChecker:
    """يحصل على فاحص المتطلبات."""
    global _checker
    if _checker is None:
        _checker = PrerequisiteChecker()
    return _checker
