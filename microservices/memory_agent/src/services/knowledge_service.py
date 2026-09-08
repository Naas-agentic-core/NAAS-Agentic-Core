"""
خدمة المعرفة (Knowledge Service).
================================

تدير العمليات المتعلقة بالرسم البياني للمفاهيم.
"""

from microservices.memory_agent.src.domain.concept_graph import (
    Concept,
    ConceptGraph,
    get_concept_graph,
)
from microservices.memory_agent.src.schemas.knowledge_schemas import (
    ReadinessRequest,
    ReadinessResponse,
)


class KnowledgeService:
    """خدمة المعرفة."""

    MINIMUM_MASTERY = 0.5  # الحد الأدنى للإتقان

    def __init__(self) -> None:
        self.graph: ConceptGraph = get_concept_graph()

    async def get_concept(self, concept_id: str) -> Concept | None:
        """يحصل على مفهوم بواسطة معرفه."""
        return self.graph.concepts.get(concept_id)

    async def get_prerequisites(self, concept_id: str) -> list[Concept]:
        """يحصل على المتطلبات السابقة."""
        return self.graph.get_prerequisites(concept_id)

    async def get_related_concepts(self, concept_id: str) -> list[Concept]:
        """يحصل على المفاهيم المرتبطة."""
        return self.graph.get_related_concepts(concept_id)

    async def get_next_concepts(self, concept_id: str) -> list[Concept]:
        """يحصل على المفاهيم التالية."""
        return self.graph.get_next_concepts(concept_id)

    async def find_concept_by_topic(self, topic: str) -> Concept | None:
        """يبحث عن مفهوم."""
        return self.graph.find_concept_by_topic(topic)

    async def get_learning_path(self, from_concept: str, to_concept: str) -> list[Concept]:
        """يجد مسار تعلم."""
        return self.graph.get_learning_path(from_concept, to_concept)

    async def check_readiness(self, payload: ReadinessRequest) -> ReadinessResponse:
        """
        يتحقق من جاهزية الطالب لمفهوم معين.
        """
        concept_id = payload.concept_id
        mastery_levels = payload.mastery_levels

        # البحث عن المفهوم
        concept = self.graph.concepts.get(concept_id)

        if not concept:
            # محاولة البحث بالموضوع
            concept = self.graph.find_concept_by_topic(concept_id)
            if concept:
                concept_id = concept.concept_id
            else:
                return ReadinessResponse(
                    concept_id=concept_id,
                    concept_name=concept_id,
                    is_ready=True,  # مفهوم غير معروف، نسمح بالمتابعة
                    readiness_score=0.5,
                    missing_prerequisites=[],
                    weak_prerequisites=[],
                    recommendation="هذا المفهوم غير موجود في قاعدة البيانات.",
                )

        prerequisites = self.graph.get_prerequisites(concept_id)

        missing = []
        weak = []
        total_score = 0.0

        for prereq in prerequisites:
            if prereq.concept_id in mastery_levels:
                mastery = mastery_levels[prereq.concept_id]
                total_score += mastery

                if mastery < self.MINIMUM_MASTERY:
                    weak.append(prereq.name_ar)
            else:
                missing.append(prereq.name_ar)
                total_score += 0  # لم يُدرس بعد

        # حساب الجاهزية
        readiness_score = (
            total_score / len(prerequisites) if prerequisites else 1.0
        )  # لا توجد متطلبات

        is_ready = len(missing) == 0 and readiness_score >= self.MINIMUM_MASTERY

        # بناء التوصية
        recommendation = self._build_recommendation(concept.name_ar, missing, weak, readiness_score)

        return ReadinessResponse(
            concept_id=concept_id,
            concept_name=concept.name_ar,
            is_ready=is_ready,
            readiness_score=readiness_score,
            missing_prerequisites=missing,
            weak_prerequisites=weak,
            recommendation=recommendation,
        )

    def _build_recommendation(
        self,
        concept_name: str,
        missing: list[str],
        weak: list[str],
        score: float,
    ) -> str:
        """يبني توصية للطالب."""

        if not missing and not weak:
            return f"🚀 أنت جاهز لتعلم {concept_name}! ابدأ الآن."

        if missing:
            topics = "، ".join(missing[:3])
            return f"📚 قبل البدء بـ {concept_name}، تحتاج دراسة: {topics}"

        if weak:
            topics = "، ".join(weak[:3])
            return f"📖 يُفضل مراجعة {topics} قبل البدء بـ {concept_name}"

        if score < 0.5:
            return f"⚠️ تحتاج تعزيز الأساسيات قبل {concept_name}"

        return f"✅ يمكنك البدء بـ {concept_name} مع بعض المراجعة"

    async def visualize(self) -> str:
        """يولّد تمثيلاً نصياً للرسم البياني."""
        return self.graph.visualize()
