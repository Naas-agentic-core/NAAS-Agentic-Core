"""اختبارات CDKC — معرفة جديدة كلياً: BKT × FSRS × تحقق رمزي × ثقة × لغة.

تثبت هذه الاختبارات أن المعادلة الجديدة:
1. ترجع None دون نضج — الجهل يُعلن جهلاً
2. تكشف الخانة الحمراء — الوهم الخطر
3. تعاقب التبديل اللغوي — لكن بإشباع
4. تصفر عند تحقق مرفوض — لا معرفة بلا برهان
5. تثبت أن M×R يختلف عن M وحده — جوهر المعرفة الجديدة
"""

from __future__ import annotations

import pytest

from shared.research.durable_knowledge import (
    CDKC_VERSION,
    MIN_OBS_CDKC,
    CdkcError,
    CdkcInput,
    LanguageSwitchCost,
    compute_cdkc,
    compute_language_switch_cost,
    compute_symbolic_weight,
)


def _base_input(**overrides) -> CdkcInput:
    base = {
        "concept_id": "continuity",
        "durable_mastery": 0.7,
        "retrievability": 0.8,
        "confidence": 0.75,
        "symbolic_verdict": "proven",
        "language_switches": (),
        "observations": 5,
        "exam_weight": 5.0,
    }
    base.update(overrides)
    return CdkcInput(**base)


class TestMaturityGuard:
    def test_immature_returns_none(self) -> None:
        """دون MIN_OBS لا تصنيف — الجهل يُعلن جهلاً."""
        inp = _base_input(observations=MIN_OBS_CDKC - 1)
        assert compute_cdkc(inp) is None

    def test_mature_returns_result(self) -> None:
        inp = _base_input(observations=MIN_OBS_CDKC)
        res = compute_cdkc(inp)
        assert res is not None
        assert res.is_mature is True
        assert res.version == CDKC_VERSION


class TestDangerousQuadrant:
    def test_confident_and_wrong_is_dangerous(self) -> None:
        """🔴 الخانة الحمراء — المنتج."""
        inp = _base_input(durable_mastery=0.2, confidence=0.9, retrievability=0.9)
        res = compute_cdkc(inp)
        assert res is not None
        assert res.quadrant == "dangerous"
        assert res.is_dangerous is True
        assert res.dangerous_gap == pytest.approx(0.7)

    def test_dangerous_penalizes_cdkc(self) -> None:
        """الوهم يعاقب CDKC — نفس M,R لكن بثقة عالية وهمية ينخفض."""
        inp_safe = _base_input(durable_mastery=0.3, confidence=0.3, retrievability=0.8)
        inp_danger = _base_input(durable_mastery=0.3, confidence=0.9, retrievability=0.8)
        res_safe = compute_cdkc(inp_safe)
        res_danger = compute_cdkc(inp_danger)
        assert res_safe is not None and res_danger is not None
        assert res_danger.cdkc_clipped < res_safe.cdkc_clipped


class TestSymbolicWeight:
    def test_proven_is_one(self) -> None:
        assert compute_symbolic_weight("proven") == pytest.approx(1.0)

    def test_unverifiable_is_half(self) -> None:
        assert compute_symbolic_weight("unverifiable") == pytest.approx(0.5)

    def test_refuted_is_zero(self) -> None:
        assert compute_symbolic_weight("refuted") == pytest.approx(0.0)

    def test_timeout_is_zero(self) -> None:
        """⛔ TIMEOUT ليس نجاحاً."""
        assert compute_symbolic_weight("timeout") == pytest.approx(0.0)

    def test_refuted_zeroes_cdkc(self) -> None:
        inp = _base_input(symbolic_verdict="refuted", durable_mastery=0.9, retrievability=0.9)
        res = compute_cdkc(inp)
        assert res is not None
        assert res.cdkc_clipped == pytest.approx(0.0)


class TestLanguageSwitch:
    def test_no_switch_zero_cost(self) -> None:
        assert compute_language_switch_cost([]) == pytest.approx(0.0)

    def test_switch_has_cost(self) -> None:
        cost = compute_language_switch_cost([LanguageSwitchCost.AR_FR])
        assert cost > 0

    def test_cost_saturated(self) -> None:
        """التراكم مُشبع عند 0.4 — لا يمحو المعرفة."""
        many = [LanguageSwitchCost.TRI] * 10
        cost = compute_language_switch_cost(many)
        assert cost <= 0.40
        assert cost > 0.18

    def test_switch_reduces_cdkc(self) -> None:
        inp_no = _base_input(language_switches=())
        inp_yes = _base_input(language_switches=(LanguageSwitchCost.AR_FR, LanguageSwitchCost.TRI))
        res_no = compute_cdkc(inp_no)
        res_yes = compute_cdkc(inp_yes)
        assert res_no is not None and res_yes is not None
        assert res_yes.cdkc_clipped < res_no.cdkc_clipped


class TestDurableTimesRetrievability:
    def test_new_knowledge_m_times_r_differs_from_m(self) -> None:
        """جوهر المعرفة الجديدة: M×R ≠ M — مفهوم أُتقن قبل شهر ولم يُراجع ليس متقناً."""
        inp_high_r = _base_input(durable_mastery=0.8, retrievability=0.9)
        inp_low_r = _base_input(durable_mastery=0.8, retrievability=0.2)
        res_high = compute_cdkc(inp_high_r)
        res_low = compute_cdkc(inp_low_r)
        assert res_high is not None and res_low is not None
        assert res_high.durable_component == pytest.approx(0.72)
        assert res_low.durable_component == pytest.approx(0.16)
        assert res_high.cdkc_clipped > res_low.cdkc_clipped

    def test_version_present(self) -> None:
        assert CDKC_VERSION == "1.0.0"


class TestValidation:
    def test_invalid_mastery_raises(self) -> None:
        with pytest.raises(CdkcError):
            _base_input(durable_mastery=1.5)

    def test_invalid_confidence_raises(self) -> None:
        with pytest.raises(CdkcError):
            _base_input(confidence=-0.1)

    def test_empty_concept_raises(self) -> None:
        with pytest.raises(CdkcError):
            _base_input(concept_id="")
