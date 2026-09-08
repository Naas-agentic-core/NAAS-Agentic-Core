"""
فاحص المتطلبات السابقة (Prerequisite Checker).
==============================================

يتحقق من جاهزية الطالب لموضوع معين.
"""

import logging
from collections import deque
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

        # الترتيب الطوبولوجي باستخدام Kahn's algorithm
        all_concepts_list = list(all_concepts)

        # استدعاء العلاقات دفعة واحدة
        relations = await self.client.get_batch_prerequisites(all_concepts_list)

        # حساب in_degree وبناء قائمة الجوار
        in_degree = dict.fromkeys(all_concepts_list, 0)
        graph = {cid: [] for cid in all_concepts_list}

        for cid, prereqs in relations.items():
            for prereq in prereqs:
                if prereq in graph:
                    graph[prereq].append(cid)
                    in_degree[cid] += 1

        # استخدام الترتيب الأصلي في الإضافة كترتيب ثانوي عند التعادل لضمان الحتمية
        # لضمان ترتيب مستقر، نقوم بفرز العقد التي ليس لها متطلبات
        ready_nodes = [cid for cid in all_concepts_list if in_degree[cid] == 0]
        # ترتيب العقد الجاهزة أبجدياً لضمان ترتيب حتمي
        ready_nodes.sort()

        queue = deque(ready_nodes)
        ordered = []

        while queue:
            current = queue.popleft()
            ordered.append(current)

            # للحفاظ على الترتيب الحتمي للأبناء
            neighbors = sorted(graph[current])
            for neighbor in neighbors:
                in_degree[neighbor] -= 1
                if in_degree[neighbor] == 0:
                    queue.append(neighbor)

        if len(ordered) != len(all_concepts_list):
            logger.warning("تم اكتشاف حلقة (cycle) في ترتيب المفاهيم الطوبولوجي.")
            # في حال وجود حلقة، نعيد جميع المفاهيم مرتبة أبجدياً بشكل حتمي لتجنب فقدان مفاهيم أو تعطل النظام
            return sorted(all_concepts_list)

        return ordered


# Singleton
_checker: PrerequisiteChecker | None = None


def get_prerequisite_checker() -> PrerequisiteChecker:
    """يحصل على فاحص المتطلبات."""
    global _checker
    if _checker is None:
        _checker = PrerequisiteChecker()
    return _checker
