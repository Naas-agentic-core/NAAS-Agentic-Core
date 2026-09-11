"""الثقة القابلة للحمل — قياسُ كلفة التحقّق وقرار القبول عن بُعد.

هذه الوحدة هي **الشقّ الاقتصادي** من المعرفة الجديدة (VEP). الوحدة السابقة
(`verifiable_evidence.py`) تجعل البرهان قابلاً لإعادة التشغيل؛ هذه تجعل قيمته
قابلة للحساب — بغيرها يبقى الإيصالُ قطعةَ تشفيرٍ بلا معنى تجاري.

المساهمة المركزية (أطروحة 🟡، لا حقيقة)
---------------------------------------
سلعةُ الثقة (credence good) تُشترى على الثقة لأنّ كلفة تحقّق المشتري أعلى من قيمة
الكشف. فإذا هبطت كلفة التحقّق (`C_check`) إلى ما دون عتبةٍ معلنة من القيمة المحافظة،
ينتقل القرار من «تجربة ميدانية + حضور شخصي» إلى «قبولٌ على الإيصال» — وهذا بالضبط
ما يفتح باب التصدير لبائعٍ لا يستطيع السفر إلى عميله ولا يستضيفه عنده.

المقاييس
--------
- `PTC`  معامل الثقة القابلة للحمل = 1 − كلفة التحقّق بالإيصال ÷ كلفة التحقّق بلا إيصال.
- `PRV`  القيمة القابلة للحمل للاعتمادية = (الخسارة المتجنَّبة بالحدّ الأدنى المحافظ)
  مطروحاً منها السعر وكلفة التحقّق وكلفة الدمج.
- `AcceptDecision` قاعدةُ قبولٍ منطوقة: يقبل على الإيصال · يطلب تجربة · يرفض.

حدودٌ معلنة (تُقرأ مع كل رقمٍ يخرج من هنا)
-------------------------------------------
1. **لا أرقام سوق**: كلّ ما يُدخل من كلفة الوحدة (`cost_per_escaped_failure_usd`) وحجم
   المهام هو مُدخلُ عميلٍ بعينه أو `PRICING HYPOTHESIS` — لا متوسطٌ سوقي.
2. **لا ادّعاء جودة**: هذه الوحدة تقيس **قيمةً مشروطة** بصحّة القياس، ولا تقيس الصحّة.
3. **عدمُ النضج يُرجع `None`** لا صفراً: عينةٌ صغيرة تعني «لا نعرف»، والصفر يُقرأ
   «لا قيمة» (قاعدة D-212: القياس غير الناضج يُرجع `None`).
4. نموذجُ الترحيل البنكي لوغاريتميٌّ طبيعي (lognormal) بافتراضين معلنين (p50 · p90) —
   نموذجٌ لا حقيقة، ويُوسم 🔴 في الوثائق.

المراجع
-------
- Darby & Karni (1973) — سلع الثقة وأثر كلفة التحقّق على الاستعداد للدفع.
- Dulleck & Kerschbamer (2006) — مسح أدبيات سلع الثقة.
- Newcombe (1998) — الفرق بين نسبتين بطريقة النتيجة الهجينة (Method 10).
- Wilson (1927) — فترة ثقة للنسبة لا تنهار عند الصفر والواحد.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import StrEnum
from typing import Final

__all__ = [
    "MIN_N_FOR_ESTIMATE",
    "WILSON_Z_95",
    "AcceptDecision",
    "BreachVerdict",
    "EscapeDelta",
    "Interval",
    "PrvResult",
    "RepatriationRisk",
    "acceptance_decision",
    "compute_prv",
    "compute_ptc",
    "contract_term_ceiling",
    "estimate_escape_delta",
    "newcombe_difference",
    "presence_substitution_index",
    "repatriation_breach_risk",
    "wilson_interval",
]

#: حدّ النضج الإحصائي: دون ثلاثين ملاحظةً الفاصلُ أوسعُ من أن يحكم قراراً.
#: اختيارُ الرقم معلنٌ هنا كي يكون قابلاً للدحض لا مضمراً.
MIN_N_FOR_ESTIMATE: Final = 30

#: z لمستوى 95% — ثابتٌ معلن، لا قيمةٌ مقتبسةٌ بلا مصدر.
WILSON_Z_95: Final = 1.959963984540054

#: z لمستوى 90% — يُستعمل في نموذج الترحيل (من p50 و p90).
_Z_90: Final = 1.2815515655446004

#: العتبة الافتراضية لقاعدة القبول: كلفة التحقّق ≤ 5% من القيمة المحافظة.
#: 🔴 **فرضية تسعير/قرار** — تُعاير بعشر مقابلات على الأقل (بروتوكول N2).
DEFAULT_ACCEPT_THETA: Final = 0.05

#: الأجل التنظيمي الافتراضي لترحيل عائدات الخدمات (يوماً) — يُقرأ من الوثائق،
#: وهو **موضعُ سؤالٍ مفتوح** بين ٣٠٦ و١٢٠ يوماً؛ يُمرَّر صراحةً ولا يُخفّأ ثابتاً.
DEFAULT_REPATRIATION_DEADLINE_DAYS: Final = 120


class AcceptDecision(StrEnum):
    """قرار المشتري العقلاني — ثلاثةُ مآلاتٍ لا أكثر، ولا مآلَ رماديّ."""

    ACCEPT_ON_ARTIFACT = "accept_on_artifact"
    PILOT_REQUIRED = "pilot_required"
    DECLINE = "decline"


class BreachVerdict(StrEnum):
    """حكمُ خرق أجل الترحيل: درجاتٌ منطوقة لا احتمالٌ يُقرأ كما يشتهي قارئه."""

    TOLERABLE = "tolerable"
    ELEVATED = "elevated"
    SEVERE = "severe"


@dataclass(frozen=True, slots=True)
class Interval:
    """فترة ثقة: طرفان، والفرقُ بينهما هو ما يقرَّر به لا مركزُه."""

    low: float
    high: float

    @property
    def width(self) -> float:
        """عرض الفترة: مقياسُ «هل نعرف أصلاً؟» — أهمّ من المركز عند صغر العيّنة."""
        return self.high - self.low


@dataclass(frozen=True, slots=True)
class EscapeDelta:
    """أثرُ حقن الأعطال مقيساً: كم فشلاً إضافياً كشفه الحقن؟"""

    baseline_failures: int
    baseline_runs: int
    injected_failures: int
    injected_runs: int
    delta_hat: float
    ci: Interval
    mature: bool

    @property
    def reason(self) -> str:
        """سببُ الحالة: غيرُ الناضج يجب أن يقول لماذا لا يُعتمد رقمه."""
        if self.mature:
            return "العينة ناضجة: الفاصل صالح للحكم."
        return (
            f"العينة غير ناضجة (n<{MIN_N_FOR_ESTIMATE}) — الرقم معروضٌ للتشخيص "
            "لا للقرار، ولا يجوز إعلانُه نتيجةً."
        )


@dataclass(frozen=True, slots=True)
class PrvResult:
    """القيمة القابلة للحمل: إجماليٌّ وصافٍ، بنقطةٍ وبحدٍّ أدنى محافظ."""

    gross_point: float
    gross_low: float
    costs_total: float
    net_point: float
    net_low: float
    decision: AcceptDecision
    reason: str


@dataclass(frozen=True, slots=True)
class RepatriationRisk:
    """خطر خرق أجل الترحيل تحت نموذجٍ معلن."""

    deadline_days: int
    settle_p50_days: float
    settle_p90_days: float
    sigma: float
    p_breach: float
    verdict: BreachVerdict
    model: str


# --------------------------------------------------------------------------- #
# إحصاءٌ بلا تبعيات
# --------------------------------------------------------------------------- #
def _phi(z: float) -> float:
    """دالة التوزيع التراكمي الطبيعي عبر `math.erf` — بلا SciPy."""
    return 0.5 * (1.0 + math.erf(z / math.sqrt(2.0)))


def _probit(probability: float) -> float:
    """معكوس التوزيع الطبيعي بالتنصيف: حتميٌّ، دقّتُه كافية لقرارٍ تجاري."""
    if not 0.0 < probability < 1.0:
        raise ValueError("الاحتمال يجب أن يكون داخل (0,1).")
    low, high = -10.0, 10.0
    for _ in range(200):
        middle = (low + high) / 2.0
        if _phi(middle) < probability:
            low = middle
        else:
            high = middle
    return (low + high) / 2.0


def wilson_interval(successes: int, n: int, z: float = WILSON_Z_95) -> Interval | None:
    """فترة ويلسون للنسبة: لا تنهار عند الحدود، ولا تتظاهر بدقّةٍ بلا عيّنة.

    تُرجع `None` دون `MIN_N_FOR_ESTIMATE` — الجهل يُعلن جهلاً (الصفر يُقرأ معرفةً).
    """
    if not 0 <= successes <= n:
        raise ValueError(f"عدد النجاحات {successes} خارج مجال العيّنة {n}.")
    if n < MIN_N_FOR_ESTIMATE:
        return None
    phat = successes / n
    denominator = 1.0 + (z * z) / n
    centre = phat + (z * z) / (2.0 * n)
    margin = z * math.sqrt((phat * (1.0 - phat)) / n + (z * z) / (4.0 * n * n))
    return Interval(
        low=max(0.0, (centre - margin) / denominator),
        high=min(1.0, (centre + margin) / denominator),
    )


def newcombe_difference(
    successes_a: int,
    n_a: int,
    successes_b: int,
    n_b: int,
    z: float = WILSON_Z_95,
) -> Interval | None:
    """فترة نيوكومب (الطريقة 10) للفرق p_b − p_a: فرقٌ بلا انهيارٍ عند الحدود.

    لماذا لا الفاصل الطبيعي المدرسي؟ لأنّه عند نسبتي فشلٍ قريبتين من الصفر يعطي
    فتراتٍ تتجاوز [−1, 1]، فيُقرأ «أثرٌ سالب مستحيل» كأنه قياس.
    """
    interval_a = wilson_interval(successes_a, n_a, z)
    interval_b = wilson_interval(successes_b, n_b, z)
    if interval_a is None or interval_b is None:
        return None
    p_a = successes_a / n_a
    p_b = successes_b / n_b
    delta = p_b - p_a
    low = delta - math.sqrt((p_b - interval_b.low) ** 2 + (interval_a.high - p_a) ** 2)
    high = delta + math.sqrt((interval_b.high - p_b) ** 2 + (p_a - interval_a.low) ** 2)
    return Interval(low=max(-1.0, low), high=min(1.0, high))


# --------------------------------------------------------------------------- #
# المقاييس الاقتصادية
# --------------------------------------------------------------------------- #
def compute_ptc(c_check_with_artifact: float, c_check_baseline: float) -> float | None:
    """معامل الثقة القابلة للحمل (PTC) = 1 − كلفة التحقّق بالإيصال ÷ كلفتها بلا إيصال.

    PTC = 1 ⇒ المشتري يتحقّق مجاناً: السلعة صارت **سلعة فحص**.
    PTC = 0 ⇒ الإيصال لم يخفّف عبئاً: بقيت سلعة ثقة.
    PTC < 0 ⇒ الإيصال أضاف عبئاً (برهانٌ معقّد أكثر من التقرير) — نتيجةٌ ممكنة ومهمة.

    تُرجع `None` إن كانت كلفة الأساس صفراً أو سالبة: نسبةٌ على صفر ليست قياساً.
    """
    if c_check_baseline <= 0:
        return None
    if c_check_with_artifact < 0:
        raise ValueError("كلفة التحقّق غير سالبة.")
    return 1.0 - (c_check_with_artifact / c_check_baseline)


def estimate_escape_delta(
    *,
    baseline_failures: int,
    baseline_runs: int,
    injected_failures: int,
    injected_runs: int,
    z: float = WILSON_Z_95,
) -> EscapeDelta | None:
    """يُقدّر أثر حقن الأعطال: الفرق في معدّل الفشل بين الشرطين بفاصل نيوكومب.

    هذا هو المُدخل الوحيد المقبول لحساب القيمة: أثرٌ مقيسٌ بفاصل، لا ادّعاءُ «كشفنا
    أعطالاً». تُرجع `None` إن كانت أيّ عيّنةٍ دون حدّ النضج.
    """
    interval = newcombe_difference(
        successes_a=baseline_failures,
        n_a=baseline_runs,
        successes_b=injected_failures,
        n_b=injected_runs,
        z=z,
    )
    if interval is None:
        return None
    p_base = baseline_failures / baseline_runs
    p_injected = injected_failures / injected_runs
    return EscapeDelta(
        baseline_failures=baseline_failures,
        baseline_runs=baseline_runs,
        injected_failures=injected_failures,
        injected_runs=injected_runs,
        delta_hat=p_injected - p_base,
        ci=interval,
        mature=True,
    )


def acceptance_decision(
    c_check_usd: float,
    gross_low_usd: float,
    theta: float = DEFAULT_ACCEPT_THETA,
) -> tuple[AcceptDecision, str]:
    """قاعدة القبول: يقبل المشتري على الإيصال وحده iff `C_check ≤ θ × القيمة المحافظة`.

    لماذا الحدّ الأدنى المحافظ لا المتوسط؟ لأنّ قرار الشراء يُتَّخذ على ما **يُخشى** أن
    تكون القيمة، لا على ما يُرجى. بيعٌ على المتوسط هو بيعٌ على الرجاء — وأوّلُ مراجعةٍ
    جدّية تُسقطه.

    `θ` فرضية تسعير/قرار (🔴) تُعاير بعشر مقابلات (بروتوكول N2).
    """
    if c_check_usd < 0:
        raise ValueError("كلفة التحقّق غير سالبة.")
    if not 0.0 < theta < 1.0:
        raise ValueError(f"العتبة θ يجب أن تكون داخل (0,1): {theta}")
    if gross_low_usd <= 0:
        return (
            AcceptDecision.DECLINE,
            "القيمة المحافظة ≤ صفر: الحدّ الأدنى للفاصل لا يبرّر الشراء، وأيّ بيعٍ هنا بيعٌ على الرجاء.",
        )
    threshold = theta * gross_low_usd
    if c_check_usd <= threshold:
        return (
            AcceptDecision.ACCEPT_ON_ARTIFACT,
            f"كلفة التحقّق {c_check_usd:,.0f} ≤ العتبة {threshold:,.0f} "
            f"(θ={theta} × قيمة محافظة {gross_low_usd:,.0f}) — يُقبل على الإيصال.",
        )
    return (
        AcceptDecision.PILOT_REQUIRED,
        f"كلفة التحقّق {c_check_usd:,.0f} > العتبة {threshold:,.0f}: التجربة الميدانية "
        "هي الوسيط، لا الإيصال — وهذا يعني زمناً وسفراً واجتماعات.",
    )


def compute_prv(
    *,
    escape_delta: EscapeDelta,
    annual_task_volume: int,
    cost_per_escaped_failure_usd: float,
    horizon_years: float = 1.0,
    price_usd: float,
    c_check_usd: float,
    c_integration_usd: float = 0.0,
    theta: float = DEFAULT_ACCEPT_THETA,
) -> PrvResult:
    """القيمة القابلة للحمل للاعتمادية (PRV) — الرقم الذي يُباع على أساسه.

    الصيغة
    ------
        Gross       = Δp × N × C_fail × H
        Gross_low   = Δp_low × N × C_fail × H     ← الحدّ الأدنى المحافظ من الفاصل
        Costs       = السعر + كلفة التحقّق + كلفة الدمج
        Net         = Gross − Costs

    `Δp_low` يُقصّ عند الصفر: أثرٌ سالب يعني «لا قيمة» لا «قيمةً سالبة» (الضرب في حجمٍ
    ضخم يحوّل ضجيجاً إحصائياً إلى كارثةٍ وهمية).

    ⚠️ كلّ مُدخلٍ من `annual_task_volume` و`cost_per_escaped_failure_usd` إمّا من بيانات
    العميل نفسه أو `PRICING HYPOTHESIS` معلنة — لا يجوز تعبئته من «متوسط السوق».
    """
    if annual_task_volume <= 0:
        raise ValueError("حجم المهام السنوي موجب.")
    if cost_per_escaped_failure_usd < 0 or horizon_years <= 0:
        raise ValueError("كلفة الفشل غير سالبة، والأفق الزمني موجب.")
    if price_usd < 0 or c_integration_usd < 0:
        raise ValueError("الأسعار والكلف غير سالبة.")
    if not escape_delta.mature:
        return PrvResult(
            gross_point=0.0,
            gross_low=0.0,
            costs_total=price_usd + c_check_usd + c_integration_usd,
            net_point=0.0,
            net_low=0.0,
            decision=AcceptDecision.DECLINE,
            reason=(
                "قياسٌ غير ناضج: لا تُحسَب قيمةٌ من فاصلٍ غير صالح، والعرضُ هنا "
                "يُقدَّم `PROPOSED` لا نتيجة. " + escape_delta.reason
            ),
        )

    scale = annual_task_volume * cost_per_escaped_failure_usd * horizon_years
    gross_point = max(0.0, escape_delta.delta_hat) * scale
    gross_low = max(0.0, escape_delta.ci.low) * scale
    costs_total = price_usd + c_check_usd + c_integration_usd
    decision, reason = acceptance_decision(c_check_usd, gross_low, theta)
    return PrvResult(
        gross_point=gross_point,
        gross_low=gross_low,
        costs_total=costs_total,
        net_point=gross_point - costs_total,
        net_low=gross_low - costs_total,
        decision=decision,
        reason=reason,
    )


# --------------------------------------------------------------------------- #
# مسار العملة الصعبة: أجل الترحيل بوصفه قيدَ تصميمِ عقد
# --------------------------------------------------------------------------- #
def repatriation_breach_risk(
    *,
    settle_p50_days: float,
    settle_p90_days: float,
    deadline_days: int = DEFAULT_REPATRIATION_DEADLINE_DAYS,
) -> RepatriationRisk:
    """احتمال خرق أجل الترحيل تحت لوغاريتميٍّ طبيعي مُعلَن بـp50 وp90.

    لماذا هذا مهمّ؟ لأنّ أجل الترحيل يبدأ — في الخدمات — من **تاريخ إنجاز الخدمة**،
    لا من تاريخ الفاتورة ولا من تاريخ التوقيع. فمهلةُ سدادٍ تبدو عادية (Net-60) مع
    بطءٍ في مشتريات العميل قد تخرق الأجل دون أن يخطئ أحد.

    ⚠️ النموذج افتراض: `S ~ LogNormal(μ=ln p50, σ=(ln p90 − ln p50)/z90)`.
    ليس قياساً لتوزيعٍ حقيقي، بل أداةُ تصميمٍ تُظهر أنّ الأجل قيدٌ عقديّ لا إجراءٌ إداري.
    """
    if settle_p50_days <= 0 or settle_p90_days <= 0:
        raise ValueError("أجلا السداد موجبان.")
    if settle_p90_days <= settle_p50_days:
        raise ValueError("p90 يجب أن يتجاوز p50: توزيعٌ بلا تشتّتٍ لا يُنمذج.")
    if deadline_days <= 0:
        raise ValueError("أجل الترحيل موجب.")
    mu = math.log(settle_p50_days)
    sigma = (math.log(settle_p90_days) - mu) / _Z_90
    p_breach = 1.0 - _phi((math.log(deadline_days) - mu) / sigma)
    if p_breach > 0.20:
        verdict = BreachVerdict.SEVERE
    elif p_breach > 0.05:
        verdict = BreachVerdict.ELEVATED
    else:
        verdict = BreachVerdict.TOLERABLE
    return RepatriationRisk(
        deadline_days=deadline_days,
        settle_p50_days=settle_p50_days,
        settle_p90_days=settle_p90_days,
        sigma=sigma,
        p_breach=p_breach,
        verdict=verdict,
        model="LogNormal(mu=ln p50, sigma=(ln p90 - ln p50)/z90) — نموذج تصميم، لا قياس",
    )


def contract_term_ceiling(
    *,
    settle_sigma: float,
    deadline_days: int = DEFAULT_REPATRIATION_DEADLINE_DAYS,
    target_breach: float = 0.05,
) -> float:
    """أقصى p50 سدادٍ يُبقي خطر الخرق دون الهدف — الرقم الذي يُكتب في العقد.

    مقلوبُ الدالة السابقة: بدل أن نسأل «هل سنخرق؟» نسأل «ما أجل السداد الذي يجوز
    منحُه؟» — فيتحوّل القيد التنظيمي إلى بندٍ تفاوضيٍّ معلوم قبل توقيع العقد.
    """
    if settle_sigma <= 0:
        raise ValueError("التشتّت موجب.")
    if not 0.0 < target_breach < 1.0:
        raise ValueError("هدف الخرق داخل (0,1).")
    z_target = _probit(1.0 - target_breach)
    return deadline_days * math.exp(-z_target * settle_sigma)


def presence_substitution_index(closed_without_visit: int, closed_total: int) -> float | None:
    """مؤشّر إحلال الحضور (PSI): كم صفقةً أُغلقت بلا زيارة أو لقاء شخصي؟

    0 ⇒ الحضور شرطٌ لكل صفقة (حالةُ التعهيد الخارجي كما تصفها الأدبيات).
    1 ⇒ الحضور لم يعد شرطاً: الإيصال حلّ محلّه.

    تُرجع `None` بلا صفقات: نسبةٌ على صفر ليست قياساً، والفراغ يُقرأ نجاحاً (D-228).
    """
    if closed_total <= 0:
        return None
    if not 0 <= closed_without_visit <= closed_total:
        raise ValueError("الصفقات بلا زيارة يجب أن تكون داخل مجال المجموع.")
    return closed_without_visit / closed_total
