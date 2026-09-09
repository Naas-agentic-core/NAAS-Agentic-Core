"""اختبارات `scripts/verify_model_registry_live.py` — منطق القرار بلا شبكة.

المسبار نفسه يُجرَّب حيّاً في CI/Codespaces؛ هنا نُثبِت **قراره** فقط: ماذا يعدّه
عطلاً، ومتى يحذّر، ومتى يرفض إصدار حكم (كي لا تُخضرّ الرحلة على عمياء — وهو
بالضبط ما حدث في D-280: CI أخضرُ بـ override والمنتج ميت).
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SCRIPT = _REPO_ROOT / "scripts" / "verify_model_registry_live.py"


def _load_probe():
    spec = importlib.util.spec_from_file_location("verify_model_registry_live", _SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


_probe = _load_probe()


def _alive(model: str) -> object:
    return _probe.ModelStatus(model=model, in_catalog=True, endpoints=1, best_provider="Stub")


def _dead(model: str) -> object:
    return _probe.ModelStatus(model=model, in_catalog=True, endpoints=0)


def _absent(model: str) -> object:
    return _probe.ModelStatus(model=model, in_catalog=False)


class TestEvaluate:
    def test_alive_primary_clean_chain_passes(self) -> None:
        results = [_alive("a/one:free"), _alive("a/two:free"), _dead("a/three:free")]
        errors, warnings, code = _probe.evaluate(
            results, key_ok=None, key_msg="", allow_dead_primary=False
        )
        assert errors == [] and code == 0
        # موتُ الذيل **بلاغٌ لا إفشال**: السلسلة القانونية تحتوي فعلاً فتحتي gpt-oss
        # بلا endpoint — وإسكاتُ ذلك ادّعاءٌ بالخُلُوّ، وإفشالُه عقابٌ على ما لا سبيل له.
        assert any("فتحاتُ تعافٍ" in w for w in warnings)

    def test_dead_primary_with_live_fallback_is_an_error(self) -> None:
        """الحالة الإنتاجية لـ 2026-09-09: PRIMARY بلا endpoint وخلفه نماذج حيّة."""
        results = [_dead("a/dead-primary:free"), _alive("a/one:free"), _alive("a/two:free")]
        errors, warnings, code = _probe.evaluate(
            results, key_ok=None, key_msg="", allow_dead_primary=False
        )
        assert code == 1 and any("PRIMARY" in e for e in errors)
        assert any("أول نموذج قابلٍ للخدمة" in w for w in warnings)

    def test_allow_dead_primary_downgrades_to_warning(self) -> None:
        """break-glass: تجاوزُ المُشغِّل للـ PRIMARY يُبقي التحذير ولا يُخفيه."""
        results = [_dead("a/dead-primary:free"), _alive("a/one:free")]
        errors, _warnings, code = _probe.evaluate(
            results, key_ok=None, key_msg="", allow_dead_primary=True
        )
        assert errors == [] and code == 0

    def test_no_servable_model_fails_closed(self) -> None:
        results = [_dead("a/one:free"), _absent("a/two:free")]
        errors, _warnings, code = _probe.evaluate(
            results, key_ok=None, key_msg="", allow_dead_primary=True
        )
        assert code == 1
        assert any("المزوّد أعمى" in e for e in errors)

    def test_blindness_loudly_declares_no_verdict_instead_of_red(self) -> None:
        """
        عمًى كامل (شبكة · 429 · 5xx) ⇒ **بلاغةٌ صاخبةٌ برمزٍ نظيف**.

        الخطّ الفاصل الذي يُصلِح دَينَ ISS-199: بوّابةٌ تُحمِّر الرحلة لانقطاعٍ لا تراه
        تُعلِّم الفريق تجاهلها، فيوم يقع عطبٌ حقيقي لا يصدّقه أحد. العَمى ليس حكماً —
        لا أخضر ولا أحمر؛ هو بلاغٌ يُقرأ في السجلّ.
        """
        results = [_probe.ModelStatus(model="a/one:free", error="URLError: connection closed")]
        errors, warnings, code = _probe.evaluate(
            results, key_ok=None, key_msg="", allow_dead_primary=False
        )
        assert code == 0 and errors == []
        assert any("لا حكم" in w for w in warnings)

    def test_strict_turns_blindness_into_a_refusal(self) -> None:
        """من يرفض التشغيل بلا رؤية يطلب ‎--strict‎ — والعَمى يصير خطأً مُسمّى."""
        results = [_probe.ModelStatus(model="a/one:free", error="HTTP 429")]
        errors, _warnings, code = _probe.evaluate(
            results, key_ok=None, key_msg="", allow_dead_primary=False, strict=True
        )
        assert code == 2 and any("لا حكم" in e for e in errors)

    def test_partial_sight_judges_only_what_it_read(self) -> None:
        """PRIMARY لم يُقرأ، وغيرُه خدَم ⇒ لا نجزم بموت الصدارة — تحذيرٌ لا إفشال."""
        results = [
            _probe.ModelStatus(model="a/dead?unknown:free", error="HTTP 429"),
            _alive("a/one:free"),
        ]
        errors, warnings, code = _probe.evaluate(
            results, key_ok=None, key_msg="", allow_dead_primary=False
        )
        assert code == 0 and errors == []
        assert any("لم يُقرأ وضع PRIMARY" in w for w in warnings)

    def test_rejected_api_key_is_reported(self) -> None:
        results = [_alive("a/one:free")]
        errors, _warnings, code = _probe.evaluate(
            results, key_ok=False, key_msg="HTTP 401 — المفتاح مرفوض", allow_dead_primary=False
        )
        assert code == 1 and any("المفتاح مرفوض" in e for e in errors)

    def test_unreachable_key_check_is_not_a_verdict(self) -> None:
        """`/auth/key` لم يُجب ≠ مفتاحٌ مرفوض — الأول تحذير، والثاني خطأ يقيني."""
        results = [_alive("a/one:free")]
        errors, warnings, code = _probe.evaluate(
            results, key_ok=False, key_msg="TimeoutError: read timed out", allow_dead_primary=False
        )
        assert code == 0 and errors == [] and any("لم يُتحقَّق من المفتاح" in w for w in warnings)

    def test_dead_lead_of_two_warns_about_latency_tax(self) -> None:
        """كل ميتٍ في الرأس يُدفَع ثمنه في أول ثانية من كل دور — تحذير لا خطأ."""
        results = [_dead("a/one:free"), _absent("a/two:free"), _alive("a/three:free")]
        _errors, warnings, _code = _probe.evaluate(
            results, key_ok=None, key_msg="", allow_dead_primary=True
        )
        assert any("ميتة" in w for w in warnings)


class TestChainComposition:
    def test_chain_follows_operator_override_and_dedups(self, monkeypatch) -> None:
        monkeypatch.setenv("OPENROUTER_PRIMARY_MODEL", "custom/override:free")
        monkeypatch.setenv("OPENROUTER_EXTRA_MODELS", "extra/model:free, extra/model:free")
        chain = _probe.chain_from_config()
        assert chain[0] == "custom/override:free"
        assert chain.count("extra/model:free") == 1
        # كل نماذج السلسلة المشتركة حاضرة بعد التجاوز
        from shared.ai_models.model_chain import FALLBACK_CHAIN

        assert all(m in chain for m in FALLBACK_CHAIN)
