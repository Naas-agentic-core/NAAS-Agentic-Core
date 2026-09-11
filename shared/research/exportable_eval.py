"""حزمة التقييم القابلة للتصدير — تحويل CDKC إلى منتج يباع بالعملة الصعبة.

هذه الوحدة تحوّل المعرفة الجديدة (CDKC) إلى ثلاث حزم تقييم قابلة للبيع:

1. Multilingual AI Red Teaming (الخط 1): مسابير تختبر فشل النماذج في العربية/الفرنسية/الدارجة
2. Niche RLHF Data (الخط 2): مجموعات بيانات معايرة بثقة + إتقان + تحقق رمزي
3. EU AI Governance Evidence (الخط 6): أدلة حوكمة قابلة للتدقيق

كل حزمة: نصوص أصلية + أحكام رمزية + CDKC + سجل منشأ + بروتوكول إعادة تشغيل.

القانون التجاري:
- لا ادعاء طلب بلا مقابلات موثقة
- لا سعر بلا وسم PRICING HYPOTHESIS
- لا حالة كتالوج متقدمة بلا دليل
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from typing import Final

from .durable_knowledge import CDKC_VERSION, CdkcInput, CdkcResult, LanguageSwitchCost, compute_cdkc

__all__ = [
    "EvalTask",
    "EvalTaskKind",
    "ExportableEvalBundle",
    "build_eval_bundle",
]

BUNDLE_VERSION: Final = "1.0.0"


class EvalTaskKind(StrEnum):
    """أنواع مهام التقييم القابلة للتصدير."""

    ILLUSION_GAP = "illusion_gap"  # قياس فجوة الوهم
    SYMBOLIC_VERIFICATION = "symbolic_verification"  # تحقق رمزي
    LANGUAGE_SWITCH = "language_switch"  # تبديل لغوي
    EXAM_ALIGNMENT = "exam_alignment"  # مطابقة مع سلّم البكالوريا
    RETRIEVABILITY_DECAY = "retrievability_decay"  # اضمحلال الاسترجاع
    DANGEROUS_QUADRANT = "dangerous_quadrant"  # الخانة الحمراء


@dataclass(frozen=True, slots=True)
class EvalTask:
    """مهمة تقييم واحدة — قابلة للتصدير والتدقيق.

    كل مهمة:
    - نص أصلي (لا ترجمة آلية خام)
    - لغة/سجل محدد
    - حكم متوقع
    - CDKC متوقع
    - إجراء إعادة تشغيل
    """

    task_id: str
    kind: EvalTaskKind
    concept_id: str
    statement_ar: str
    statement_fr: str | None
    expected_verdict: str
    language_switches: tuple[LanguageSwitchCost, ...]
    exam_weight: float
    stream: str  # علوم تجريبية / رياضيات / تقني رياضي...
    difficulty_b: float  # من IRT/Elo
    barem_nodes: tuple[str, ...]  # مراجع إلى D-214
    cdkc_input: CdkcInput
    cdkc_result: CdkcResult | None
    author: str
    created_at: datetime
    provenance: str  # مصدر النص: دورة بكالوريا / تأليف أصلي / خطأ حقيقي


@dataclass(frozen=True, slots=True)
class ExportableEvalBundle:
    """حزمة تقييم قابلة للتصدير — المنتج الذي يباع.

    تحتوي:
    - N مهمة مع CDKC
    - بطاقة معايرة
    - سجل منشأ
    - بروتوكول إعادة تشغيل
    - بيان حدود (ما لم يُختبر)
    """

    bundle_id: str
    version: str
    created_at: datetime
    cdkc_version: str
    tasks: tuple[EvalTask, ...]
    total_tasks: int
    calibrated_tasks: int
    dangerous_count: int
    avg_cdkc: float | None
    language_coverage: dict[str, int]
    concept_coverage: dict[str, int]
    calibration_card: dict[str, float | int | str]
    limitations: tuple[str, ...]
    commercial_note: str

    @property
    def is_mature(self) -> bool:
        """هل الحزمة ناضجة بما يكفي للبيع؟"""
        return self.calibrated_tasks >= 30 and self.total_tasks >= 100


def build_eval_bundle(
    bundle_id: str,
    tasks: list[EvalTask],
    limitations: list[str] | None = None,
) -> ExportableEvalBundle:
    """يبني حزمة تقييم من مهام — يحسب التغطية والمعايرة.

    هذه الدالة هي التي تحوّل المعرفة الجديدة إلى منتج قابل للتصدير.
    لا تبيع بيانات، تبيع حزمة موثقة بمنشأ وبطاقة معايرة وبيان حدود.
    """
    if not tasks:
        raise ValueError("لا يمكن بناء حزمة من صفر مهمة")

    calibrated = [t for t in tasks if t.cdkc_result is not None]
    dangerous = [t for t in calibrated if t.cdkc_result and t.cdkc_result.is_dangerous]

    avg_cdkc: float | None = None
    if calibrated:
        vals = [t.cdkc_result.cdkc_clipped for t in calibrated if t.cdkc_result]
        if vals:
            avg_cdkc = sum(vals) / len(vals)

    # تغطية لغوية
    lang_cov: dict[str, int] = {}
    for t in tasks:
        for sw in t.language_switches:
            lang_cov[sw] = lang_cov.get(sw, 0) + 1
        if not t.language_switches:
            lang_cov["none"] = lang_cov.get("none", 0) + 1

    # تغطية مفاهيم
    concept_cov: dict[str, int] = {}
    for t in tasks:
        concept_cov[t.concept_id] = concept_cov.get(t.concept_id, 0) + 1

    # بطاقة معايرة — مبسطة للنسخة 1.0.0
    calibration_card: dict[str, float | int | str] = {
        "version": CDKC_VERSION,
        "total": len(tasks),
        "calibrated": len(calibrated),
        "dangerous": len(dangerous),
        "avg_cdkc": avg_cdkc if avg_cdkc is not None else -1.0,
        "maturity_threshold": 4,
        "bundle_version": BUNDLE_VERSION,
    }

    default_limitations = (
        "لا يغطي الصوت/الفيديو — نص فقط",
        "لا يغطي البرهان الاستدلالي غير القابل للتحقق الرمزي إلا بوزن 0.5",
        "التحقق الرمزي محدود بالجبر والتحليل والاحتمالات — ~90% من ادعاءات البكالوريا",
        "كلفة التبديل اللغوي تقديرية وتحتاج معايرة على بيانات حقيقية",
        "CDKC غير معاير على عينة كبيرة بعد — يُعرض كـ PRICING HYPOTHESIS حتى القياس",
    )

    final_limitations = tuple(limitations) if limitations else default_limitations

    commercial_note = (
        "هذه الحزمة مادة دعم للخطوط 1 و2 و6 في OFFER_CATALOG.json — تبقى PROPOSED "
        "حتى مقابلات اكتشاف موثقة. لا تُذكر في أي عرض إلا موسومة 🟡 أطروحة أو 🔴 فرضية. "
        "السعر: PRICING HYPOTHESIS ضمن نطاق D-273 §03 وحده."
    )

    return ExportableEvalBundle(
        bundle_id=bundle_id,
        version=BUNDLE_VERSION,
        created_at=datetime.now(UTC),
        cdkc_version=CDKC_VERSION,
        tasks=tuple(tasks),
        total_tasks=len(tasks),
        calibrated_tasks=len(calibrated),
        dangerous_count=len(dangerous),
        avg_cdkc=avg_cdkc,
        language_coverage=lang_cov,
        concept_coverage=concept_cov,
        calibration_card=calibration_card,
        limitations=final_limitations,
        commercial_note=commercial_note,
    )


def example_bundle() -> ExportableEvalBundle:
    """مثال حيّ — حزمة صغيرة للتوضيح، لا تُباع.

    يبني 3 مهام تثبت أن CDKC يعمل ويكشف الوهم والتبديل اللغوي.
    """
    from datetime import datetime

    now = datetime.now(UTC)

    tasks: list[EvalTask] = []

    # مهمة 1: وهم خطر — ثقة عالية وإتقان منخفض
    inp1 = CdkcInput(
        concept_id="continuity",
        durable_mastery=0.25,
        retrievability=0.85,
        confidence=0.90,
        symbolic_verdict="proven",
        language_switches=(),
        observations=5,
        exam_weight=5.0,
    )
    res1 = compute_cdkc(inp1)
    tasks.append(
        EvalTask(
            task_id="dz-bac-2023-math-ex2-step3",
            kind=EvalTaskKind.DANGEROUS_QUADRANT,
            concept_id="continuity",
            statement_ar="ناقش اتصال الدالة f عند 0 — الطالب واثق لكنه يخلط بين الاتصال والاشتقاق",
            statement_fr="Discuter la continuité de f en 0 — l'élève confond continuité et dérivabilité",
            expected_verdict="proven",
            language_switches=(),
            exam_weight=5.0,
            stream="sciences_experimentales",
            difficulty_b=0.8,
            barem_nodes=("continuity-def", "limit-calc"),
            cdkc_input=inp1,
            cdkc_result=res1,
            author="research-independent-v1",
            created_at=now,
            provenance="bac-2023-math — خطأ حقيقي مصنف",
        )
    )

    # مهمة 2: تبديل لغوي ثلاثي
    inp2 = CdkcInput(
        concept_id="acid_base",
        durable_mastery=0.65,
        retrievability=0.60,
        confidence=0.70,
        symbolic_verdict="unverifiable",
        language_switches=(LanguageSwitchCost.AR_FR, LanguageSwitchCost.AR_DZ),
        observations=6,
        exam_weight=5.0,
    )
    res2 = compute_cdkc(inp2)
    tasks.append(
        EvalTask(
            task_id="dz-bac-2022-phys-acid-base-tri",
            kind=EvalTaskKind.LANGUAGE_SWITCH,
            concept_id="acid_base",
            statement_ar="حمض ضعيف — التلميذ يكتب بالدارجة: 'l'acide ma kayen' ثم يعود للفصحى",
            statement_fr="Acide faible — code-switching DZ: mélange arabe/darija/français",
            expected_verdict="unverifiable",
            language_switches=(LanguageSwitchCost.AR_FR, LanguageSwitchCost.AR_DZ),
            exam_weight=5.0,
            stream="sciences_experimentales",
            difficulty_b=0.2,
            barem_nodes=("ph-def", "ka-calc"),
            cdkc_input=inp2,
            cdkc_result=res2,
            author="research-independent-v1",
            created_at=now,
            provenance="خطأ حقيقي — تبديل لغوي موثق",
        )
    )

    # مهمة 3: تحقق رمزي مرفوض
    inp3 = CdkcInput(
        concept_id="probability",
        durable_mastery=0.80,
        retrievability=0.90,
        confidence=0.85,
        symbolic_verdict="refuted",
        language_switches=(),
        observations=8,
        exam_weight=4.0,
    )
    res3 = compute_cdkc(inp3)
    tasks.append(
        EvalTask(
            task_id="dz-bac-2024-math-prob-refuted",
            kind=EvalTaskKind.SYMBOLIC_VERIFICATION,
            concept_id="probability",
            statement_ar="احتمال سحب كرتين — النموذج أخطأ في الحساب والتحقق الرمزي كشفه",
            statement_fr=None,
            expected_verdict="refuted",
            language_switches=(),
            exam_weight=4.0,
            stream="mathematiques",
            difficulty_b=-0.3,
            barem_nodes=("prob-comb", "prob-cond"),
            cdkc_input=inp3,
            cdkc_result=res3,
            author="research-independent-v1",
            created_at=now,
            provenance="bac-2024-math — خطأ نموذج كشفه التحقق الرمزي",
        )
    )

    return build_eval_bundle("cdkc-demo-v1", tasks)
