"""
الرسم البياني للمفاهيم (Concept Graph).
======================================

يربط المفاهيم التعليمية ببعضها ويحدد العلاقات والمتطلبات السابقة.

المعايير:
- CS50 2025: توثيق عربي
- SICP: Data Abstraction
"""

import logging
from dataclasses import dataclass, field
from enum import StrEnum
from typing import ClassVar

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class RelationType(StrEnum):
    """أنواع العلاقات بين المفاهيم."""

    PREREQUISITE = "prerequisite"  # متطلب سابق
    LEADS_TO = "leads_to"  # يؤدي إلى
    RELATED = "related"  # مرتبط
    PART_OF = "part_of"  # جزء من
    APPLIES_IN = "applies_in"  # يُطبق في
    GENERALIZES = "generalizes"  # يعمم
    SPECIALIZES = "specializes"  # يخصص


class Concept(BaseModel):
    """مفهوم تعليمي."""

    concept_id: str = Field(..., description="معرف المفهوم")
    name_ar: str = Field(..., description="الاسم بالعربية")
    name_en: str = Field("", description="الاسم بالإنجليزية")
    description: str = Field("", description="وصف المفهوم")
    subject: str = Field("Mathematics", description="المادة")
    level: str = Field("", description="المستوى")
    difficulty: float = Field(0.5, ge=0.0, le=1.0, description="الصعوبة")
    tags: list[str] = Field(default_factory=list)


class ConceptRelation(BaseModel):
    """علاقة بين مفهومين."""

    source_id: str
    target_id: str
    relation_type: RelationType
    strength: float = Field(1.0, ge=0.0, le=1.0, description="قوة العلاقة")


@dataclass
class ConceptNode:
    """عقدة في الرسم البياني."""

    concept: Concept
    prerequisites: list[str] = field(default_factory=list)
    leads_to: list[str] = field(default_factory=list)
    related: list[str] = field(default_factory=list)


class ConceptGraph:
    """
    الرسم البياني للمفاهيم التعليمية.

    المميزات:
    - تحديد المتطلبات السابقة
    - اقتراح المفاهيم التالية
    - إيجاد مسارات التعلم
    - كشف الفجوات المعرفية
    """

    # قاعدة بيانات المفاهيم الافتراضية (Mathematics - BAC)
    DEFAULT_CONCEPTS: ClassVar = {
        # الاحتمالات
        "prob_basics": Concept(
            concept_id="prob_basics",
            name_ar="أساسيات الاحتمالات",
            name_en="Probability Basics",
            subject="Mathematics",
            difficulty=0.3,
            tags=["احتمالات", "probability"],
        ),
        "combinations": Concept(
            concept_id="combinations",
            name_ar="التوفيقات",
            name_en="Combinations",
            subject="Mathematics",
            difficulty=0.4,
            tags=["توفيقات", "combinations"],
        ),
        "permutations": Concept(
            concept_id="permutations",
            name_ar="الترتيبات",
            name_en="Permutations",
            subject="Mathematics",
            difficulty=0.4,
            tags=["ترتيبات", "permutations"],
        ),
        "conditional_prob": Concept(
            concept_id="conditional_prob",
            name_ar="الاحتمال الشرطي",
            name_en="Conditional Probability",
            subject="Mathematics",
            difficulty=0.5,
            tags=["احتمالات", "شرطي"],
        ),
        "random_variable": Concept(
            concept_id="random_variable",
            name_ar="المتغير العشوائي",
            name_en="Random Variable",
            subject="Mathematics",
            difficulty=0.6,
            tags=["متغير عشوائي", "random variable"],
        ),
        # الأعداد المركبة
        "complex_basics": Concept(
            concept_id="complex_basics",
            name_ar="أساسيات الأعداد المركبة",
            name_en="Complex Numbers Basics",
            subject="Mathematics",
            difficulty=0.4,
            tags=["أعداد مركبة", "complex"],
        ),
        "complex_operations": Concept(
            concept_id="complex_operations",
            name_ar="العمليات على الأعداد المركبة",
            name_en="Complex Operations",
            subject="Mathematics",
            difficulty=0.5,
            tags=["أعداد مركبة", "عمليات"],
        ),
        "complex_polar": Concept(
            concept_id="complex_polar",
            name_ar="الشكل المثلثي",
            name_en="Polar Form",
            subject="Mathematics",
            difficulty=0.6,
            tags=["أعداد مركبة", "مثلثي"],
        ),
        "complex_exponential": Concept(
            concept_id="complex_exponential",
            name_ar="الشكل الأسي",
            name_en="Exponential Form",
            subject="Mathematics",
            difficulty=0.7,
            tags=["أعداد مركبة", "أسي"],
        ),
        # المتتاليات
        "sequences_basics": Concept(
            concept_id="sequences_basics",
            name_ar="أساسيات المتتاليات",
            name_en="Sequences Basics",
            subject="Mathematics",
            difficulty=0.4,
            tags=["متتاليات", "sequences"],
        ),
        "arithmetic_seq": Concept(
            concept_id="arithmetic_seq",
            name_ar="المتتالية الحسابية",
            name_en="Arithmetic Sequence",
            subject="Mathematics",
            difficulty=0.5,
            tags=["متتاليات", "حسابية"],
        ),
        "geometric_seq": Concept(
            concept_id="geometric_seq",
            name_ar="المتتالية الهندسية",
            name_en="Geometric Sequence",
            subject="Mathematics",
            difficulty=0.5,
            tags=["متتاليات", "هندسية"],
        ),
        "sequence_limits": Concept(
            concept_id="sequence_limits",
            name_ar="نهايات المتتاليات",
            name_en="Sequence Limits",
            subject="Mathematics",
            difficulty=0.7,
            tags=["متتاليات", "نهايات"],
        ),
        # الدوال
        "function_basics": Concept(
            concept_id="function_basics",
            name_ar="أساسيات الدوال",
            name_en="Function Basics",
            subject="Mathematics",
            difficulty=0.3,
            tags=["دوال", "functions"],
        ),
        "limits": Concept(
            concept_id="limits",
            name_ar="النهايات",
            name_en="Limits",
            subject="Mathematics",
            difficulty=0.5,
            tags=["نهايات", "limits"],
        ),
        "continuity": Concept(
            concept_id="continuity",
            name_ar="الاستمرارية",
            name_en="Continuity",
            subject="Mathematics",
            difficulty=0.6,
            tags=["استمرارية", "continuity"],
        ),
        "derivatives": Concept(
            concept_id="derivatives",
            name_ar="الاشتقاق",
            name_en="Derivatives",
            subject="Mathematics",
            difficulty=0.6,
            tags=["اشتقاق", "derivatives"],
        ),
        "integrals": Concept(
            concept_id="integrals",
            name_ar="التكامل",
            name_en="Integrals",
            subject="Mathematics",
            difficulty=0.7,
            tags=["تكامل", "integrals"],
        ),
        "exp_functions": Concept(
            concept_id="exp_functions",
            name_ar="الدوال الأسية",
            name_en="Exponential Functions",
            subject="Mathematics",
            difficulty=0.6,
            tags=["دوال", "أسية"],
        ),
        "log_functions": Concept(
            concept_id="log_functions",
            name_ar="الدوال اللوغاريتمية",
            name_en="Logarithmic Functions",
            subject="Mathematics",
            difficulty=0.6,
            tags=["دوال", "لوغاريتم"],
        ),
    }

    # العلاقات الافتراضية
    DEFAULT_RELATIONS: ClassVar = [
        # الاحتمالات
        ConceptRelation(
            source_id="prob_basics", target_id="combinations", relation_type=RelationType.LEADS_TO
        ),
        ConceptRelation(
            source_id="prob_basics", target_id="permutations", relation_type=RelationType.LEADS_TO
        ),
        ConceptRelation(
            source_id="combinations",
            target_id="conditional_prob",
            relation_type=RelationType.PREREQUISITE,
        ),
        ConceptRelation(
            source_id="conditional_prob",
            target_id="random_variable",
            relation_type=RelationType.LEADS_TO,
        ),
        # الأعداد المركبة
        ConceptRelation(
            source_id="complex_basics",
            target_id="complex_operations",
            relation_type=RelationType.LEADS_TO,
        ),
        ConceptRelation(
            source_id="complex_operations",
            target_id="complex_polar",
            relation_type=RelationType.LEADS_TO,
        ),
        ConceptRelation(
            source_id="complex_polar",
            target_id="complex_exponential",
            relation_type=RelationType.LEADS_TO,
        ),
        # المتتاليات
        ConceptRelation(
            source_id="sequences_basics",
            target_id="arithmetic_seq",
            relation_type=RelationType.LEADS_TO,
        ),
        ConceptRelation(
            source_id="sequences_basics",
            target_id="geometric_seq",
            relation_type=RelationType.LEADS_TO,
        ),
        ConceptRelation(
            source_id="arithmetic_seq",
            target_id="sequence_limits",
            relation_type=RelationType.LEADS_TO,
        ),
        ConceptRelation(
            source_id="geometric_seq",
            target_id="sequence_limits",
            relation_type=RelationType.LEADS_TO,
        ),
        # الدوال
        ConceptRelation(
            source_id="function_basics", target_id="limits", relation_type=RelationType.LEADS_TO
        ),
        ConceptRelation(
            source_id="limits", target_id="continuity", relation_type=RelationType.LEADS_TO
        ),
        ConceptRelation(
            source_id="continuity", target_id="derivatives", relation_type=RelationType.LEADS_TO
        ),
        ConceptRelation(
            source_id="derivatives", target_id="integrals", relation_type=RelationType.LEADS_TO
        ),
        ConceptRelation(
            source_id="derivatives",
            target_id="exp_functions",
            relation_type=RelationType.APPLIES_IN,
        ),
        ConceptRelation(
            source_id="derivatives",
            target_id="log_functions",
            relation_type=RelationType.APPLIES_IN,
        ),
        # علاقات متقاطعة
        ConceptRelation(
            source_id="exp_functions",
            target_id="complex_exponential",
            relation_type=RelationType.RELATED,
        ),
        ConceptRelation(
            source_id="geometric_seq", target_id="exp_functions", relation_type=RelationType.RELATED
        ),
    ]

    def __init__(self) -> None:
        self.concepts: dict[str, Concept] = self.DEFAULT_CONCEPTS.copy()
        self.relations: list[ConceptRelation] = self.DEFAULT_RELATIONS.copy()
        self._build_graph()

    def _build_graph(self) -> None:
        """يبني الرسم البياني من العلاقات."""

        self.nodes: dict[str, ConceptNode] = {}

        # إنشاء العقد
        for concept_id, concept in self.concepts.items():
            self.nodes[concept_id] = ConceptNode(concept=concept)

        # إضافة العلاقات
        for relation in self.relations:
            if relation.source_id not in self.nodes or relation.target_id not in self.nodes:
                continue

            source_node = self.nodes[relation.source_id]

            if relation.relation_type == RelationType.PREREQUISITE:
                self.nodes[relation.target_id].prerequisites.append(relation.source_id)
            elif relation.relation_type == RelationType.LEADS_TO:
                source_node.leads_to.append(relation.target_id)
            elif relation.relation_type == RelationType.RELATED:
                source_node.related.append(relation.target_id)

    def get_prerequisites(self, concept_id: str) -> list[Concept]:
        """يحصل على المتطلبات السابقة لمفهوم."""

        if concept_id not in self.nodes:
            return []

        node = self.nodes[concept_id]
        return [
            self.concepts[prereq_id]
            for prereq_id in node.prerequisites
            if prereq_id in self.concepts
        ]

    def get_next_concepts(self, concept_id: str) -> list[Concept]:
        """يحصل على المفاهيم التالية."""

        if concept_id not in self.nodes:
            return []

        node = self.nodes[concept_id]
        return [self.concepts[next_id] for next_id in node.leads_to if next_id in self.concepts]

    def get_related_concepts(self, concept_id: str) -> list[Concept]:
        """يحصل على المفاهيم المرتبطة."""

        if concept_id not in self.nodes:
            return []

        node = self.nodes[concept_id]
        return [self.concepts[rel_id] for rel_id in node.related if rel_id in self.concepts]

    def find_concept_by_topic(self, topic: str) -> Concept | None:
        """يبحث عن مفهوم بالموضوع أو الكلمة المفتاحية."""

        topic_lower = topic.lower()

        for concept in self.concepts.values():
            # البحث في الاسم العربي
            if topic in concept.name_ar:
                return concept

            # البحث في الاسم الإنجليزي
            if topic_lower in concept.name_en.lower():
                return concept

            # البحث في التاغات
            for tag in concept.tags:
                if topic_lower in tag.lower() or tag.lower() in topic_lower:
                    return concept

        return None

    def get_learning_path(
        self,
        from_concept: str,
        to_concept: str,
    ) -> list[Concept]:
        """يجد مسار تعلم بين مفهومين."""

        if from_concept not in self.nodes or to_concept not in self.nodes:
            return []

        # BFS للعثور على أقصر مسار
        from collections import deque

        queue: deque[tuple[str, list[str]]] = deque([(from_concept, [from_concept])])
        visited: set[str] = {from_concept}

        while queue:
            current, path = queue.popleft()

            if current == to_concept:
                return [self.concepts[cid] for cid in path]

            node = self.nodes[current]
            for next_id in node.leads_to + node.related:
                if next_id not in visited:
                    visited.add(next_id)
                    queue.append((next_id, [*path, next_id]))

        return []

    def identify_knowledge_gaps(
        self,
        mastered_concepts: list[str],
        target_concept: str,
    ) -> list[Concept]:
        """يحدد الفجوات المعرفية."""

        gaps = []

        if target_concept not in self.nodes:
            return gaps

        # الحصول على كل المتطلبات السابقة (تراكمي)
        all_prereqs = self._get_all_prerequisites(target_concept)

        # الفجوات = المتطلبات غير المُتقنة
        for prereq_id in all_prereqs:
            if prereq_id not in mastered_concepts and prereq_id in self.concepts:
                gaps.append(self.concepts[prereq_id])

        # ترتيب حسب الصعوبة
        gaps.sort(key=lambda c: c.difficulty)

        return gaps

    def _get_all_prerequisites(self, concept_id: str) -> set[str]:
        """يحصل على كل المتطلبات السابقة بشكل تراكمي."""

        all_prereqs: set[str] = set()
        to_process = [concept_id]

        while to_process:
            current = to_process.pop()
            if current in self.nodes:
                for prereq in self.nodes[current].prerequisites:
                    if prereq not in all_prereqs:
                        all_prereqs.add(prereq)
                        to_process.append(prereq)

        return all_prereqs

    def visualize(self) -> str:
        """يولّد تمثيل نصي للرسم البياني."""

        lines = ["📊 خريطة المفاهيم:", ""]

        for _concept_id, node in self.nodes.items():
            lines.append(f"📌 {node.concept.name_ar}")

            if node.prerequisites:
                prereq_names = [
                    self.concepts[p].name_ar for p in node.prerequisites if p in self.concepts
                ]
                lines.append(f"   ⬅️ يتطلب: {', '.join(prereq_names)}")

            if node.leads_to:
                next_names = [self.concepts[n].name_ar for n in node.leads_to if n in self.concepts]
                lines.append(f"   ➡️ يؤدي إلى: {', '.join(next_names)}")

            lines.append("")

        return "\n".join(lines)


# Singleton
_concept_graph: ConceptGraph | None = None


def get_concept_graph() -> ConceptGraph:
    """يحصل على الرسم البياني للمفاهيم."""
    global _concept_graph
    if _concept_graph is None:
        _concept_graph = ConceptGraph()
    return _concept_graph
