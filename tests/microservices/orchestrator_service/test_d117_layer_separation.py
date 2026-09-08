"""D-117 — فصل الطبقات: الطالب يرى التعليم لا هندسة التعليم.

الكارثة (transcript حي): النموذج المجاني كان يُردّد التفكير الداخلي للنظام حرفياً
على الشاشة — «[توجيه تربوي] ... مستوى الدعم: ...»، «نوع المسألة: ... سؤال تشخيصي
واحد: ... أصغر خطوة صحيحة ... اطلب من الطالب» + هلوسة «Konzept». المنصة «تتكلّم من
داخل عقلها». هذا الاختبار يحرس الإصلاحات الأربعة (stdlib + source-inspection —
يعمل في الـ sandbox بلا pydantic):

1. حذف prepend «[توجيه تربوي]» من orchestrator_client (التوجيه عبر support_level فقط).
2. البرومبت السقراطي سلوكي طبيعي — لا قالب مُرقَّم بعناوين يَنسخها النموذج.
3. المُطهّر المُصفّح (المونوليث + الـ orchestrator) يحذف كل العلامات الداخلية المُسرَّبة.
4. متابعات حيرة الاحتمالات تُعيد بثّ البصري الحتمي من history.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

from app.infrastructure.clients.orchestrator.tutor_sources import read_tutor_source

REPO_ROOT = Path(__file__).resolve().parents[3]
# CLIENT_SRC stays client-only for the "no `[توجيه تربوي]` prepend in the client" negative check.
CLIENT_SRC = read_tutor_source()
# D-164: `_build_calculated_ui` moved to ProbabilityUIMixin; positive assertions of its inner
# strings read the full tutor source via the manifest.
TUTOR_SRC = read_tutor_source()
SEARCH_SRC = (
    REPO_ROOT / "microservices/orchestrator_service/src/services/overmind/graph/search.py"
).read_text(encoding="utf-8")
CONTENT_INTEGRITY_SRC = (REPO_ROOT / "app/services/skills/content_integrity_skill.py").read_text(
    encoding="utf-8"
)

#: العلامات الداخلية التي يجب ألّا تصل الطالب أبداً (لغة النظام لا التعليم).
_INTERNAL_MARKERS = (
    "توجيه تربوي",
    "مستوى الدعم",
    "نوع المسألة",
    "سؤال تشخيصي",
    "أصغر خطوة",
    "اطلب من الطالب",
    "وضع الشرح العميق",
    "فهمت المطلوب",
    "Konzept",
)


def _load_response_sanitizer():
    p = REPO_ROOT / "microservices/orchestrator_service/src/services/overmind/response_sanitizer.py"
    spec = importlib.util.spec_from_file_location("rs_d117", p)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# ── 1. لا prepend للتوجيه التربوي (قتل التسرّب #1 من المصدر) ────────────────────
class TestNoDirectivePrepend:
    def test_client_has_no_directive_prepend(self):
        # الصيغة الكودية للتسرّب (f-string)، لا الذكر في التعليق (بـ guillemet «»)
        assert 'f"[توجيه تربوي]' not in CLIENT_SRC

    def test_client_reads_support_level_for_depth(self):
        assert 'get("support_level")' in CLIENT_SRC

    def test_directive_not_consumed_by_orchestrator(self):
        # الـ orchestrator يستهلك support_level فقط — لا pedagogy_directive (لا leak path)
        # D-168: الفحص السلبي يمسح كل ملفات API_SOURCE_FILES (لا يمرّ زوراً بعد التفكيك)
        from microservices.orchestrator_service.src.api.api_sources import (
            API_SOURCE_FILES,
        )

        for f in (
            *API_SOURCE_FILES,
            "microservices/orchestrator_service/src/services/overmind/graph/main.py",
            "microservices/orchestrator_service/src/services/overmind/graph/search.py",
            "microservices/orchestrator_service/src/services/overmind/graph/nodes.py",
            "microservices/orchestrator_service/src/services/overmind/graph/state.py",
        ):
            src = (REPO_ROOT / f).read_text(encoding="utf-8")
            assert "pedagogy_directive" not in src, f


# ── 2. البرومبت السقراطي سلوكي طبيعي (قتل التسرّب #2) ───────────────────────────
class TestBehavioralSocraticPrompt:
    def test_no_labeled_numbered_template(self):
        # القالب المُرقَّم القديم (D-115) كان النموذج يَنسخ عناوينه حرفياً
        assert "اتبع هذا القالب حرفياً" not in SEARCH_SRC
        assert "1) أعِد صياغة" not in SEARCH_SRC
        assert "فهمت المطلوب: ..." not in SEARCH_SRC

    def test_natural_behavioral_and_no_reveal(self):
        assert "لننظر إلى هذا الجزء فقط" in SEARCH_SRC
        assert "لا تكشف الجواب النهائي" in SEARCH_SRC

    def test_explicitly_forbids_internal_labels(self):
        assert "لا يراها الطالب" in SEARCH_SRC
        for label in ("نوع المسألة", "سؤال تشخيصي", "أصغر خطوة", "مستوى الدعم"):
            assert label in SEARCH_SRC, f"forbidden-label clause missing: {label}"


# ── 3. المُطهّر المُصفّح يحذف كل علامة داخلية (دفاع عميق) ───────────────────────
class TestSanitizerStripsInternalMarkers:
    def test_orchestrator_sanitizer_strips_all_markers(self):
        rs = _load_response_sanitizer()
        catastrophe = (
            "[توجيه تربوي] الطالب ما زال يبني هذا المفهوم. مستوى الدعم: مثال كامل.\n"
            "فهمت المطلوب: حساب الاحتمال.\n"
            "نوع المسألة: شرح خطوة Konzeptية.\n"
            "سؤال تشخيصي واحد: كم كرة حمراء؟\n"
            "أصغر خطوة صحيحة التالية: عُدّ الكرات.\n"
            "اطلب من الطالب أن يُكمل بنفسه.\n"
            "[وضع الشرح العميق] الطالب يعبّر عن حيرة.\n"
            "لننظر إلى هذا الجزء فقط — جرّب أن تعدّ كم كرة حمراء، وأخبرني لنُكمل."
        )
        out = rs.strip_garbage_markers(catastrophe)
        for marker in _INTERNAL_MARKERS:
            assert marker not in out, f"internal marker leaked: {marker!r}"
        # النص التعليمي الطبيعي يبقى
        assert "لننظر إلى هذا الجزء فقط" in out
        assert "جرّب أن تعدّ كم كرة حمراء" in out

    def test_orchestrator_preserves_natural_arabic_and_latex(self):
        rs = _load_response_sanitizer()
        assert "مثال محلول" in rs.strip_garbage_markers("هذا مثال محلول بسيط")
        assert "x^2" in rs.sanitize_chunk("النتيجة $x^2$ هنا")

    def test_monolith_leak_regex_lists_all_markers(self):
        # regex التسرّب في المونوليث يذكر كل علامة داخلية (defense-in-depth موازٍ)
        seg = CONTENT_INTEGRITY_SRC[
            CONTENT_INTEGRITY_SRC.index("_INSTRUCTION_LEAK_RE") : CONTENT_INTEGRITY_SRC.index(
                "_INSTRUCTION_LEAK_RE"
            )
            + 600
        ]
        for marker in _INTERNAL_MARKERS:
            assert marker in seg, f"monolith leak regex missing marker: {marker!r}"


# ── 4. متابعات حيرة الاحتمالات تُعيد البصري الحتمي من history ───────────────────
class TestProbabilityConfusionReEmitsVisual:
    def test_generic_confusion_reextracts_from_history(self):
        # D-117 Fix 4: حيرة عامة + history احتمالات ⇒ إعادة تحليل بنص الـ history
        # D-164: هذا المنطق يعيش داخل `_build_calculated_ui` في ProbabilityUIMixin الآن.
        # ISS-131 (D-169 — قاعدة D-102): الاستخراج صار من حوار الطالب/المساعد حصراً
        # (`_dialogue_history` — رسائل system لا تدخل الكاشف).
        assert "_is_deep_pedagogy\n                and _dialogue_history" in TUTOR_SRC
        assert (
            "ProbabilityInput(\n                            question=_history_context" in TUTOR_SRC
        )
