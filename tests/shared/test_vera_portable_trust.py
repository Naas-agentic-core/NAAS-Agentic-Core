"""اختبارات VEP — الشقّ الاقتصادي: كلفة التحقّق، قرار القبول، وأجل الترحيل.

تثبت هذه الاختبارات أنّ المعرفة الجديدة قابلة **للدحض** لا للتأويل:
1. عدمُ النضج يُرجع `None` لا صفراً — الجهل يُعلن جهلاً
2. الفتراتُ محصورةٌ في مجالها، وتضيق مع العيّنة (قانونٌ إحصائي لا رأي)
3. قاعدة القبول لها حدٌّ معلن، والحدودُ تُختبر عند التماسّ نفسه
4. القيمة تُحسب على **الحدّ الأدنى المحافظ** لا على المتوسط (البيع على الرجاء ممنوع)
5. أجل الترحيل قيدُ تصميمِ عقد، والدالة العكسية تُسترجِع الهدف (اختبار ذهاباً وعودة)
6. الحزمة stdlib فقط — تُشحن إلى عميلٍ بلا تبعياتنا
"""

from __future__ import annotations

import ast
import math
from pathlib import Path

import pytest

from shared.research.portable_trust import (
    DEFAULT_ACCEPT_THETA,
    DEFAULT_REPATRIATION_DEADLINE_DAYS,
    MIN_N_FOR_ESTIMATE,
    AcceptDecision,
    BreachVerdict,
    EscapeDelta,
    Interval,
    acceptance_decision,
    compute_prv,
    compute_ptc,
    contract_term_ceiling,
    estimate_escape_delta,
    newcombe_difference,
    presence_substitution_index,
    repatriation_breach_risk,
    wilson_interval,
)

Z_90 = 1.2815515655446004  # z لمستوى 90% — مستقلّ عن الثابت الداخلي كي يكشف تغييره


def mature_delta(
    baseline_failures: int = 20,
    baseline_runs: int = 200,
    injected_failures: int = 60,
    injected_runs: int = 200,
):
    delta = estimate_escape_delta(
        baseline_failures=baseline_failures,
        baseline_runs=baseline_runs,
        injected_failures=injected_failures,
        injected_runs=injected_runs,
    )
    assert delta is not None
    return delta


# --------------------------------------------------------------------------- #
# 1) النضج: غيرُ الناضج `None` لا صفر
# --------------------------------------------------------------------------- #
def test_wilson_returns_none_below_maturity() -> None:
    assert wilson_interval(1, 2) is None
    assert wilson_interval(29, 29) is None
    assert wilson_interval(30, 30) is not None


def test_newcombe_returns_none_when_either_sample_is_immature() -> None:
    assert newcombe_difference(1, 2, 10, 200) is None
    assert newcombe_difference(10, 200, 1, 2) is None
    assert newcombe_difference(10, 200, 20, 200) is not None


def test_escape_delta_is_none_when_immature() -> None:
    assert (
        estimate_escape_delta(
            baseline_failures=2, baseline_runs=5, injected_failures=4, injected_runs=5
        )
        is None
    )


def test_maturity_threshold_is_declared_not_implicit() -> None:
    assert MIN_N_FOR_ESTIMATE == 30


# --------------------------------------------------------------------------- #
# 2) سلوك الفترات
# --------------------------------------------------------------------------- #
def test_wilson_interval_matches_the_classical_value() -> None:
    """نقطةُ ارتكاز: 50/100 → نحو [0.4038, 0.5962] (ويلسون 95%)."""
    interval = wilson_interval(50, 100)
    assert interval is not None
    assert interval.low == pytest.approx(0.4038, abs=1e-3)
    assert interval.high == pytest.approx(0.5962, abs=1e-3)


def test_wilson_stays_inside_the_unit_interval() -> None:
    for successes, n in ((0, 30), (30, 30), (1, 30), (29, 30)):
        interval = wilson_interval(successes, n)
        assert interval is not None
        assert 0.0 <= interval.low <= interval.high <= 1.0


def test_wilson_rejects_impossible_counts() -> None:
    with pytest.raises(ValueError):
        wilson_interval(11, 10)
    with pytest.raises(ValueError):
        wilson_interval(-1, 10)


def test_confidence_width_shrinks_as_the_sample_grows() -> None:
    """قانونٌ إحصائي لا رأي: إن لم يتحقق، فالمقياس نفسه فاسد."""
    widths = [
        newcombe_difference(
                successes_a=base,
                n_a=n,
                successes_b=2 * base,
                n_b=n,
            ).width
        for n, base in ((50, 5), (200, 20), (800, 80), (3200, 320))
    ]
    assert widths == sorted(widths, reverse=True)
    assert widths[0] > widths[-1]
    assert all(width > 0 for width in widths)


def test_newcombe_interval_contains_the_point_estimate() -> None:
    delta = mature_delta()
    assert delta.ci.low <= delta.delta_hat <= delta.ci.high
    assert delta.ci.low > 0, "أثرٌ مقيسٌ موجب: الحقن كشف فشلاً لم يظهر في المسار السعيد"


# --------------------------------------------------------------------------- #
# 3) معامل الثقة القابلة للحمل
# --------------------------------------------------------------------------- #
def test_ptc_is_one_when_verification_becomes_free() -> None:
    assert compute_ptc(0.0, 100.0) == pytest.approx(1.0)


def test_ptc_is_zero_when_the_artifact_saves_nothing() -> None:
    assert compute_ptc(100.0, 100.0) == pytest.approx(0.0)


def test_ptc_is_negative_when_the_artifact_adds_burden() -> None:
    """نتيجةٌ ممكنة ومهمة: برهانٌ معقّد أكثر من التقرير أسوأ من لا برهان."""
    assert (compute_ptc(150.0, 100.0) or 0.0) < 0


def test_ptc_is_none_on_a_zero_baseline() -> None:
    assert compute_ptc(0.0, 0.0) is None


def test_ptc_rejects_negative_costs() -> None:
    with pytest.raises(ValueError):
        compute_ptc(-1.0, 100.0)


# --------------------------------------------------------------------------- #
# 4) قاعدة القبول
# --------------------------------------------------------------------------- #
def test_acceptance_accepts_at_the_boundary_and_just_beyond() -> None:
    decision, _ = acceptance_decision(c_check_usd=500.0, gross_low_usd=10_000.0, theta=0.05)
    assert decision is AcceptDecision.ACCEPT_ON_ARTIFACT
    decision, _ = acceptance_decision(c_check_usd=501.0, gross_low_usd=10_000.0, theta=0.05)
    assert decision is AcceptDecision.PILOT_REQUIRED


def test_acceptance_declines_when_the_conservative_value_is_not_positive() -> None:
    decision, reason = acceptance_decision(c_check_usd=0.0, gross_low_usd=0.0)
    assert decision is AcceptDecision.DECLINE
    assert "القيمة المحافظة" in reason


def test_acceptance_rejects_an_absurd_theta() -> None:
    with pytest.raises(ValueError):
        acceptance_decision(c_check_usd=1.0, gross_low_usd=100.0, theta=0.0)
    with pytest.raises(ValueError):
        acceptance_decision(c_check_usd=1.0, gross_low_usd=100.0, theta=1.5)


def test_default_theta_is_declared_as_a_hypothesis() -> None:
    """عتبةٌ افتراضية معلنة كي تكون قابلة للدحض، لا مضمرة في جسم الدالة."""
    assert 0.0 < DEFAULT_ACCEPT_THETA < 1.0


# --------------------------------------------------------------------------- #
# 5) القيمة القابلة للحمل
# --------------------------------------------------------------------------- #
def test_prv_refuses_to_price_immature_evidence() -> None:
    """قياسٌ غير ناضج ⇒ لا قيمة تُحسب: العرض يبقى `PROPOSED` لا نتيجة تُباع."""
    assert (
        estimate_escape_delta(
            baseline_failures=1, baseline_runs=3, injected_failures=2, injected_runs=3
        )
        is None
    )
    immature = EscapeDelta(
        baseline_failures=1,
        baseline_runs=3,
        injected_failures=2,
        injected_runs=3,
        delta_hat=0.333,
        ci=Interval(low=-0.45, high=0.92),
        mature=False,
    )
    result = compute_prv(
        escape_delta=immature,
        annual_task_volume=100_000,
        cost_per_escaped_failure_usd=50.0,
        price_usd=1_000.0,
        c_check_usd=100.0,
    )
    assert result.decision is AcceptDecision.DECLINE
    assert "غير ناضج" in result.reason
    assert result.gross_point == 0.0 and result.gross_low == 0.0


def test_prv_uses_the_conservative_bound_not_the_mean() -> None:
    delta = mature_delta()
    result = compute_prv(
        escape_delta=delta,
        annual_task_volume=100_000,
        cost_per_escaped_failure_usd=25.0,
        horizon_years=1.0,
        price_usd=20_000.0,
        c_check_usd=2_000.0,
    )
    assert result.gross_low < result.gross_point, "الحدّ الأدنى المحافظ أدنى من المتوسط دائماً"
    assert result.gross_low == pytest.approx(delta.ci.low * 100_000 * 25.0)
    assert result.net_low == pytest.approx(result.gross_low - result.costs_total)


def test_prv_drives_the_acceptance_decision() -> None:
    delta = mature_delta()
    cheap_to_verify = compute_prv(
        escape_delta=delta,
        annual_task_volume=200_000,
        cost_per_escaped_failure_usd=25.0,
        price_usd=10_000.0,
        c_check_usd=200.0,  # إعادة تشغيل آلية: ساعات قليلة
    )
    expensive_to_verify = compute_prv(
        escape_delta=delta,
        annual_task_volume=2_000,
        cost_per_escaped_failure_usd=25.0,
        price_usd=10_000.0,
        c_check_usd=20_000.0,  # إعادة تشغيل يدوية + سفر: العبء الذي نزيله
    )
    assert cheap_to_verify.decision is AcceptDecision.ACCEPT_ON_ARTIFACT
    assert expensive_to_verify.decision is not AcceptDecision.ACCEPT_ON_ARTIFACT


def test_prv_rejects_nonsense_inputs() -> None:
    delta = mature_delta()
    with pytest.raises(ValueError):
        compute_prv(
            escape_delta=delta,
            annual_task_volume=0,
            cost_per_escaped_failure_usd=1.0,
            price_usd=1.0,
            c_check_usd=1.0,
        )
    with pytest.raises(ValueError):
        compute_prv(
            escape_delta=delta,
            annual_task_volume=10,
            cost_per_escaped_failure_usd=-1.0,
            price_usd=1.0,
            c_check_usd=1.0,
        )


def test_prv_is_deterministic() -> None:
    delta = mature_delta()
    kwargs = {
        "escape_delta": delta,
        "annual_task_volume": 50_000,
        "cost_per_escaped_failure_usd": 30.0,
        "price_usd": 15_000.0,
        "c_check_usd": 1_500.0,
    }
    assert compute_prv(**kwargs) == compute_prv(**kwargs)


# --------------------------------------------------------------------------- #
# 6) أجل الترحيل: قيدُ تصميمِ عقد
# --------------------------------------------------------------------------- #
def test_repatriation_default_deadline_is_declared() -> None:
    assert DEFAULT_REPATRIATION_DEADLINE_DAYS == 120


def test_short_settlement_is_tolerable_and_long_is_severe() -> None:
    tight = repatriation_breach_risk(settle_p50_days=30.0, settle_p90_days=45.0)
    loose = repatriation_breach_risk(settle_p50_days=90.0, settle_p90_days=200.0)
    assert tight.verdict is BreachVerdict.TOLERABLE
    assert loose.verdict is BreachVerdict.SEVERE
    assert tight.p_breach < loose.p_breach


def test_breach_risk_is_monotone_in_settlement_time() -> None:
    risks = [
        repatriation_breach_risk(settle_p50_days=p50, settle_p90_days=p50 * 1.8).p_breach
        for p50 in (15.0, 30.0, 60.0, 90.0)
    ]
    assert risks == sorted(risks)


def test_deadline_relaxation_lowers_the_risk() -> None:
    strict = repatriation_breach_risk(
        settle_p50_days=60.0, settle_p90_days=120.0, deadline_days=120
    )
    relaxed = repatriation_breach_risk(
        settle_p50_days=60.0, settle_p90_days=120.0, deadline_days=306
    )
    assert relaxed.p_breach < strict.p_breach


def test_contract_term_ceiling_round_trips_to_the_target() -> None:
    """ذهاباً وعودة: أجل السداد المشتقّ يحقّق هدف الخرق نفسه — الدالة ليست تخميناً."""
    sigma = 0.55
    ceiling = contract_term_ceiling(settle_sigma=sigma, deadline_days=120, target_breach=0.04)
    p90 = ceiling * math.exp(sigma * Z_90)
    risk = repatriation_breach_risk(
        settle_p50_days=ceiling, settle_p90_days=p90, deadline_days=120
    )
    assert risk.p_breach == pytest.approx(0.04, abs=1e-3)
    assert risk.verdict is BreachVerdict.TOLERABLE


def test_contract_term_ceiling_tightens_as_dispersion_grows() -> None:
    calm = contract_term_ceiling(settle_sigma=0.3, deadline_days=120)
    volatile = contract_term_ceiling(settle_sigma=0.9, deadline_days=120)
    assert volatile < calm


def test_repatriation_model_is_declared_not_hidden() -> None:
    risk = repatriation_breach_risk(settle_p50_days=30.0, settle_p90_days=60.0)
    assert "LogNormal" in risk.model


def test_repatriation_rejects_impossible_dispersions() -> None:
    with pytest.raises(ValueError):
        repatriation_breach_risk(settle_p50_days=60.0, settle_p90_days=40.0)
    with pytest.raises(ValueError):
        repatriation_breach_risk(settle_p50_days=0.0, settle_p90_days=10.0)


# --------------------------------------------------------------------------- #
# 7) مؤشّر إحلال الحضور
# --------------------------------------------------------------------------- #
def test_presence_substitution_is_none_without_deals() -> None:
    assert presence_substitution_index(0, 0) is None


def test_presence_substitution_bounds() -> None:
    assert presence_substitution_index(0, 5) == pytest.approx(0.0)
    assert presence_substitution_index(5, 5) == pytest.approx(1.0)
    with pytest.raises(ValueError):
        presence_substitution_index(6, 5)


# --------------------------------------------------------------------------- #
# 8) نقاء الحزمة
# --------------------------------------------------------------------------- #
def test_module_imports_nothing_but_the_standard_library() -> None:
    module_path = Path(__file__).resolve().parents[2] / "shared" / "research" / "portable_trust.py"
    tree = ast.parse(module_path.read_text(encoding="utf-8"))
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module.split(".")[0])
    forbidden = imported - {"math", "dataclasses", "enum", "typing", "__future__"}
    assert not forbidden, f"استيرادٌ خارج المسموح: {sorted(forbidden)}"
