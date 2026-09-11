"""معامل المعرفة الدائمة القابل للتصدير — CDKC.

معرفة جديدة كلياً: معادلة تجمع قياسات كانت منفصلة في أدبيات منفصلة
وتحوّلها إلى معامل واحد قابل للتصدير والتدقيق والبيع بالعملة الصعبة.

الصياغة الرياضية
----------------
CDKC = ( M_durable × R(Δt,S) × V_sym × (1 - L_switch) ) - λ × gap_dangerous

حيث:
- M_durable: الإتقان الدائم من BKT [0,1]
- R(Δt,S): قابلية الاسترجاع من FSRS [0,1] — الضرب مقصود: ما أُتقن قبل شهر ولم يُراجع ليس متقناً
- V_sym: وزن التحقق الرمزي {0, 0.5, 1.0} — 1=مُبرهن، 0.5=غير قابل للتحقق، 0=مرفوض
- L_switch: كلفة التبديل اللغوي [0,0.4] — كل تبديل عربي/فرنسي/دارجة يزيد الكلفة
- gap_dangerous: فجوة الوهم الخطرة max(0, conf - M) إن كانت في الخانة الحمراء
- λ: معامل عقوبة الوهم (0.3 افتراضياً) — الوهم أخطر من الجهل

لماذا هذه المعادلة جديدة
-------------------------
1. لا معيار موجود يجمع BKT + FSRS + تحقق رمزي + معايرة ثقة + تكلفة لغوية
2. كل حدّ فيها قابل للتدقيق: لا LLM في المسار العددي
3. تُنتج رقماً واحداً يفسّر نفسه: لماذا هذا الطالب سينسى؟ هل لأنه واهم؟ أم لأن الرمز غير متحقق؟
4. قابلة للتصدير: مختبر نماذج خارج الجزائر يستطيع قياس CDKC على بياناته العربية/الفرنسية

المراجع
-------
- Corbett & Anderson (1995) BKT
- FSRS-5 Jarrett Ye et al.
- Bastani et al. PNAS 2025 (فجوة الوهم)
- Lightman et al. 2023 (التحقق الخطوة بخطوة)
- Abdaoui et al. 2021 DziriBERT (التبديل اللغوي)
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import StrEnum
from typing import Final

__all__ = [
    "CDKC_VERSION",
    "MIN_OBS_CDKC",
    "CdkcError",
    "CdkcInput",
    "CdkcResult",
    "LanguageSwitchCost",
    "SymbolicWeight",
    "compute_cdkc",
    "compute_language_switch_cost",
    "compute_symbolic_weight",
]

CDKC_VERSION: Final = "1.0.0"
MIN_OBS_CDKC: Final = 4
LAMBDA_DANGEROUS: Final = 0.30
MAX_SWITCH_COST: Final = 0.40


class CdkcError(ValueError):
    """خرق مجال في حساب CDKC — لا نرجع قيمة افتراضية مضللة."""


class SymbolicWeight(StrEnum):
    """وزن التحقق الرمزي — يحوّل الحكم الرمزي إلى وزن عددي قابل للضرب."""

    PROVEN = "proven"  # 1.0 — مُبرهن رمزياً
    UNVERIFIABLE = "unverifiable"  # 0.5 — نص تربوي لا يُتحقق
    REFUTED = "refuted"  # 0.0 — مرفوض رمزياً
    TIMEOUT = "timeout"  # 0.0 — انتهاء مهلة = لا نعرف = لا نعرض

    def to_float(self) -> float:
        """تحويل الحكم إلى وزن."""
        match self:
            case SymbolicWeight.PROVEN:
                return 1.0
            case SymbolicWeight.UNVERIFIABLE:
                return 0.5
            case SymbolicWeight.REFUTED:
                return 0.0
            case SymbolicWeight.TIMEOUT:
                return 0.0


class LanguageSwitchCost(StrEnum):
    """أنواع التبديل اللغوي الجزائري."""

    NONE = "none"  # لغة واحدة
    AR_FR = "ar_fr"  # عربي ↔ فرنسي
    AR_DZ = "ar_dz"  # عربي فصيح ↔ دارجة
    FR_DZ = "fr_dz"  # فرنسي ↔ دارجة
    TRI = "tri"  # ثلاثي


def compute_language_switch_cost(
    switches: list[LanguageSwitchCost],
) -> float:
    """يحسب كلفة التبديل اللغوي التراكمية.

    كل تبديل له كلفة، لكن التراكم مُشبع عند 0.4 كي لا يمحو المعرفة.
    """
    if not switches:
        return 0.0

    cost_map: dict[LanguageSwitchCost, float] = {
        LanguageSwitchCost.NONE: 0.0,
        LanguageSwitchCost.AR_FR: 0.12,
        LanguageSwitchCost.AR_DZ: 0.08,
        LanguageSwitchCost.FR_DZ: 0.10,
        LanguageSwitchCost.TRI: 0.18,
    }

    total = sum(cost_map.get(s, 0.0) for s in switches)
    # إشباع لوغاريتمي: أول تبديل مكلف، التالي أقل
    saturated = MAX_SWITCH_COST * (1 - math.exp(-total / 0.25))
    return min(saturated, MAX_SWITCH_COST)


def compute_symbolic_weight(verdict: str) -> float:
    """يحول حكم التحقق الرمزي إلى وزن."""
    try:
        return SymbolicWeight(verdict).to_float()
    except ValueError as exc:
        raise CdkcError(f"حكم رمزي غير معروف: {verdict}") from exc


@dataclass(frozen=True, slots=True)
class CdkcInput:
    """مدخلات حساب CDKC — كلها حتمية، لا LLM.

    الحقول
    ------
    concept_id: من shared/curriculum — لا مصدر ثانٍ
    durable_mastery: من BKT، الإتقان الدائم غير المدعوم [0,1]
    retrievability: من FSRS، R(Δt,S) [0,1]
    confidence: الثقة المعلنة قبل الإجابة [0,1]
    symbolic_verdict: حكم التحقق الرمزي
    language_switches: قائمة التبديلات اللغوية في المسار
    observations: عدد الملاحظات غير المدعومة
    exam_weight: معامل المادة/المفهوم من shared/curriculum
    """

    concept_id: str
    durable_mastery: float
    retrievability: float
    confidence: float
    symbolic_verdict: str
    language_switches: tuple[LanguageSwitchCost, ...]
    observations: int
    exam_weight: float = 1.0

    def __post_init__(self) -> None:
        if not (0.0 <= self.durable_mastery <= 1.0):
            raise CdkcError(f"durable_mastery خارج [0,1]: {self.durable_mastery}")
        if not (0.0 <= self.retrievability <= 1.0):
            raise CdkcError(f"retrievability خارج [0,1]: {self.retrievability}")
        if not (0.0 <= self.confidence <= 1.0):
            raise CdkcError(f"confidence خارج [0,1]: {self.confidence}")
        if self.observations < 0:
            raise CdkcError(f"observations سالب: {self.observations}")
        if self.exam_weight <= 0:
            raise CdkcError(f"exam_weight غير موجب: {self.exam_weight}")
        if not self.concept_id:
            raise CdkcError("concept_id فارغ")


@dataclass(frozen=True, slots=True)
class CdkcResult:
    """نتيجة حساب CDKC — قابلة للتصدير والتدقيق.

    CDKC ∈ [-0.3, 1.0] نظرياً (سالب إن كان الوهم عالياً جداً)
    لكن عملياً يُقص إلى [0,1] للعرض، مع حقل raw يحفظ القيمة قبل القص.
    """

    concept_id: str
    cdkc_raw: float
    cdkc_clipped: float
    durable_component: float
    symbolic_component: float
    switch_cost: float
    dangerous_gap: float
    quadrant: str
    observations: int
    exam_weight: float
    is_mature: bool
    version: str

    @property
    def is_dangerous(self) -> bool:
        """هل في الخانة الحمراء؟"""
        return self.quadrant == "dangerous"

    @property
    def needs_review(self) -> bool:
        """هل يحتاج مراجعة عاجلة؟ CDKC < 0.5 أو وهم خطر."""
        return self.cdkc_clipped < 0.5 or self.is_dangerous


def _quadrant(confidence: float, durable: float) -> str:
    """تصنيف رباعي — نفس عتبة shared/illusion (0.60)."""
    high = 0.60
    conf_high = confidence >= high
    mast_high = durable >= high
    if conf_high and mast_high:
        return "mastered"
    if conf_high and not mast_high:
        return "dangerous"
    if not conf_high and mast_high:
        return "hidden_skill"
    return "known_gap"


def compute_cdkc(inp: CdkcInput) -> CdkcResult | None:
    """يحسب معامل المعرفة الدائمة القابل للتصدير.

    القاعدة الحامية للمصداقية: دون MIN_OBS ملاحظات غير مدعومة
    نرجع None — لا رقم، لا لون، لا ادعاء. الجهل يُعلن جهلاً.

    المعادلة:
    CDKC = (M_durable × R × V_sym × (1 - L_switch)) - λ × gap_dangerous

    حيث gap_dangerous = max(0, conf - M_durable) إن كان quadrant==dangerous وإلا 0

    مثال:
        >>> inp = CdkcInput(
        ...     concept_id=\"continuity\",
        ...     durable_mastery=0.3,
        ...     retrievability=0.8,
        ...     confidence=0.9,
        ...     symbolic_verdict=\"proven\",
        ...     language_switches=(),
        ...     observations=5,
        ...     exam_weight=5.0
        ... )
        >>> res = compute_cdkc(inp)
        >>> res.is_dangerous
        True
    """
    if inp.observations < MIN_OBS_CDKC:
        return None

    v_sym = compute_symbolic_weight(inp.symbolic_verdict)
    l_switch = compute_language_switch_cost(list(inp.language_switches))

    # المكون الدائم × قابلية الاسترجاع — الضرب مقصود
    durable_comp = inp.durable_mastery * inp.retrievability

    # فجوة الوهم الخطرة فقط
    quad = _quadrant(inp.confidence, inp.durable_mastery)
    dangerous_gap = 0.0
    if quad == "dangerous":
        dangerous_gap = max(0.0, inp.confidence - inp.durable_mastery)

    # المعادلة الأساسية — معرفة جديدة كلياً
    raw = (durable_comp * v_sym * (1.0 - l_switch)) - (LAMBDA_DANGEROUS * dangerous_gap)

    clipped = max(0.0, min(1.0, raw))

    return CdkcResult(
        concept_id=inp.concept_id,
        cdkc_raw=raw,
        cdkc_clipped=clipped,
        durable_component=durable_comp,
        symbolic_component=v_sym,
        switch_cost=l_switch,
        dangerous_gap=dangerous_gap,
        quadrant=quad,
        observations=inp.observations,
        exam_weight=inp.exam_weight,
        is_mature=True,
        version=CDKC_VERSION,
    )
