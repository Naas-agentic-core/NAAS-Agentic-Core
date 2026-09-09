"""
ISS-079 (D-067 — 2026-05-17) — اختبارات الكوارث الثلاث المُكتشفة حياً.

الكوارث الموثَّقة من جلسة مستخدم حقيقية:

**كارثة #1**: "السلام عليكم" → رد etymological طويل
  - السبب: orchestrator-service غير متاح → local_graph بلا greeting fastpath
  - الحل: `_greeting_fastpath_response` في local_graph + `GreetingSkill` رسمي

**كارثة #2**: "كيف نبين أن الرباعي معين" بعد BAC 2024 → هلوسة لغوية
  - السبب: detect_explanation_with_context يعمل لكن LLM يفشل بـ content=None
  - الحل: استبدال PRIMARY model بـ openai/gpt-oss-20b:free

**كارثة #3**: "اشرح لي خطوة خطوة السؤال 1 ج" → garbage "pepepe aaaa"
  - السبب: nemotron-nano-30b يضع كل المحتوى في reasoning (إنجليزي)
  - الحل: تغيير PRIMARY + إيقاف reasoning→content leak + تبسيط prompt
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import importlib.util


# Load local_graph WITHOUT going through app/__init__ to avoid heavy imports
def _load_module(name: str, path: str):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


_REPO_ROOT = Path(__file__).parent.parent.parent
_local_graph = _load_module("lg", str(_REPO_ROOT / "app/services/chat/local_graph.py"))


class TestCatastrophe1GreetingFastpath:
    """ISS-079 #1: السلام عليكم → fastpath response (no LLM, no etymology)."""

    def test_simple_islamic_greeting(self):
        r = _local_graph._greeting_fastpath_response("السلام عليكم")
        assert r is not None
        assert "وعليكم السلام" in r

    def test_full_islamic_greeting(self):
        r = _local_graph._greeting_fastpath_response("السلام عليكم ورحمة الله وبركاته")
        assert r is not None
        assert "وعليكم السلام" in r

    def test_response_to_greeting(self):
        r = _local_graph._greeting_fastpath_response("وعليكم السلام")
        assert r is not None

    def test_simple_marhaba(self):
        r = _local_graph._greeting_fastpath_response("مرحبا")
        assert r is not None
        assert "أهلاً" in r

    def test_english_hello(self):
        r = _local_graph._greeting_fastpath_response("hello")
        assert r is not None
        assert "Hi" in r or "help" in r.lower()

    def test_kayfa_halak(self):
        r = _local_graph._greeting_fastpath_response("كيف حالك")
        assert r is not None
        assert "بخير" in r

    def test_morning_greeting(self):
        r = _local_graph._greeting_fastpath_response("صباح الخير")
        assert r is not None
        assert "صباح النور" in r

    def test_thanks(self):
        r = _local_graph._greeting_fastpath_response("شكرا")
        assert r is not None
        assert "العفو" in r


class TestCatastrophe1Blockers:
    """ISS-079 #1: السؤال بفعل تعليمي يُلغي fastpath حتى لو بدأ بتحية."""

    def test_greeting_with_educational_verb(self):
        r = _local_graph._greeting_fastpath_response("السلام عليكم اشرح قانون نيوتن")
        assert r is None, "must NOT fastpath when educational verb is present"

    def test_greeting_with_tamreen_request(self):
        r = _local_graph._greeting_fastpath_response("مرحبا اعطني تمرين")
        assert r is None

    def test_kayfa_interrogative_blocker(self):
        # "كيف نبين" — interrogative, not greeting
        r = _local_graph._greeting_fastpath_response("كيف نبين أن الرباعي معين")
        assert r is None

    def test_ma_huwa_blocker(self):
        r = _local_graph._greeting_fastpath_response("ما هو التكامل")
        assert r is None

    def test_calculate_blocker(self):
        r = _local_graph._greeting_fastpath_response("احسب التكامل")
        assert r is None

    def test_explain_blocker(self):
        r = _local_graph._greeting_fastpath_response("اشرح لي الدالة")
        assert r is None

    def test_empty_input(self):
        r = _local_graph._greeting_fastpath_response("")
        assert r is None


class TestGreetingSkillContract:
    """ISS-079 D-067: GreetingSkill رسمي بـ Pydantic contract.

    نختبر عبر file-based source inspection لتجنُّب الاعتماد على pydantic_settings
    وبقية app/core/* الثقيلة عند تشغيل اختبار جراحي.
    """

    def test_greeting_skill_file_exists(self):
        path = _REPO_ROOT / "app/services/skills/greeting_skill.py"
        assert path.exists(), "GreetingSkill file must exist (D-067)"

    def test_greeting_skill_exports_required_symbols(self):
        source = (_REPO_ROOT / "app/services/skills/greeting_skill.py").read_text(encoding="utf-8")
        for sym in (
            "class GreetingSkill",
            "class GreetingSkillInput",
            "class GreetingSkillOutput",
            "class GreetingSkillFailure",
        ):
            assert sym in source, f"GreetingSkill must export {sym}"

    def test_greeting_skill_has_prometheus_metrics(self):
        source = (_REPO_ROOT / "app/services/skills/greeting_skill.py").read_text(encoding="utf-8")
        assert "skill.greeting.invocations.total" in source, (
            "GreetingSkill must record Prometheus metrics (CLAUDE.md §0.5)"
        )

    def test_greeting_skill_has_blockers(self):
        source = (_REPO_ROOT / "app/services/skills/greeting_skill.py").read_text(encoding="utf-8")
        assert "_EDUCATIONAL_BLOCKERS" in source, (
            "GreetingSkill must have blockers preventing fastpath on educational requests"
        )

    def test_greeting_skill_in_init_exports(self):
        source = (_REPO_ROOT / "app/services/skills/__init__.py").read_text(encoding="utf-8")
        assert "GreetingSkill" in source
        assert "greeting_skill" in source


class TestPrimaryModelConfig:
    """ISS-079 D-067 → D-088 → D-167: PRIMARY model.

    D-067 (2026-05-17): PRIMARY تغيَّر من nemotron-nano إلى gpt-oss-20b.
    D-088 (2026-05-27): PRIMARY تغيَّر من gpt-oss-20b إلى gpt-oss-120b بسبب
      rate-limiting دائم لـ gpt-oss-20b على OpenRouter (ISS-082).
    D-167 (2026-07-14 / ISS-130): OpenRouter أزال النسخة المجانية من
      gpt-oss-120b نهائياً (404) ⇒ إعادة ترقية gpt-oss-20b (تعافى من 429 —
      مُتحقَّق حياً عربي+LaTeX finish=stop). gpt-oss-120b يبقى في ذيل السلسلة
      كفتحة تعافٍ آلي.
    """

    def _read(self, path: str) -> str:
        return (_REPO_ROOT / path).read_text(encoding="utf-8")

    def test_app_core_ai_config_primary(self):
        source = self._read("app/core/ai_config.py")
        # D-167: PRIMARY عاد إلى gpt-oss-20b (120b المجاني أُزيل نهائياً — 404)
        assert 'PRIMARY = _resolve_primary_model("openai/gpt-oss-20b:free")' in source, (
            "app/core/ai_config.py PRIMARY must be openai/gpt-oss-20b:free (D-167). "
            "gpt-oss-120b:free أُزيل نهائياً من OpenRouter (ISS-130)."
        )

    def test_app_core_ai_config_has_recovery_slot(self):
        source = self._read("app/core/ai_config.py")
        # gpt-oss-120b يبقى في ذيل السلسلة كفتحة تعافٍ آلي (لا يُحذف)
        assert "openai/gpt-oss-120b:free" in source, (
            "app/core/ai_config.py يجب أن يحتوي gpt-oss-120b:free كفتحة تعافٍ في الذيل."
        )

    def test_orchestrator_ai_config_primary(self):
        source = self._read("microservices/orchestrator_service/src/core/ai_config.py")
        assert "GPT_OSS_20B_FREE" in source, (
            "orchestrator ai_config must have GPT_OSS_20B_FREE constant"
        )
        # D-167: PRIMARY يستخدم GPT_OSS_20B_FREE (mirror لسلسلة المونوليث)
        assert "PRIMARY = _resolve_primary_model(AvailableModels.GPT_OSS_20B_FREE)" in source, (
            "orchestrator ai_config PRIMARY must use GPT_OSS_20B_FREE (D-167)"
        )

    def test_conversation_math_pipeline_default(self):
        source = self._read("microservices/conversation_service/src/math_pipeline.py")
        # D-167: _DEFAULT_MODEL عاد إلى gpt-oss-20b (120b المجاني أُزيل — 404)
        assert '_DEFAULT_MODEL = "openai/gpt-oss-20b:free"' in source, (
            "math_pipeline default model must be gpt-oss-20b:free (D-167/ISS-130)."
        )

    def test_conversation_graph_default(self):
        source = self._read("microservices/conversation_service/src/conversation_graph.py")
        # D-167: _DEFAULT_MODEL عاد إلى gpt-oss-20b (120b المجاني أُزيل — 404)
        assert '_DEFAULT_MODEL = "openai/gpt-oss-20b:free"' in source, (
            "conversation_graph default model must be gpt-oss-20b:free (D-167/ISS-130)."
        )


class TestNoBoxDrawingInExplanationPrompt:
    """ISS-079 D-067: prompt الشرح يجب ألا يحوي box-drawing chars (تُربك tokenizer)."""

    def test_no_box_drawing_chars_in_prompt(self):
        text = _local_graph._EXERCISE_EXPLANATION_SYSTEM_PROMPT
        # box drawings (U+2500-U+257F) — تُسبب garbage في النماذج المجانية
        # لا نسمح بأكثر من 2 من هذه الـ chars (مسموح حالات نادرة في tests).
        box_count = sum(1 for c in text if 0x2500 <= ord(c) <= 0x257F)
        assert box_count <= 2, (
            f"Explanation prompt has {box_count} box-drawing chars — "
            f"these confuse free OpenRouter tokenizers and trigger 'pepepe aaaa' "
            f"garbage. D-067 reduced from 78×6=468 to 0."
        )

    def test_prompt_is_concise(self):
        """Prompt يجب أن يكون < 1000 chars — الـ long ones يُسببون reasoning leak."""
        text = _local_graph._EXERCISE_EXPLANATION_SYSTEM_PROMPT
        assert len(text) < 1000, (
            f"Prompt is {len(text)} chars; ISS-079 showed prompts > 1500 chars cause "
            f"nemotron-nano to return content=None. Keep short."
        )


class TestNoReasoningContentLeak:
    """ISS-079 D-067: gateway لم يعد يُمرِّر reasoning كـ content."""

    def test_simple_client_does_not_redirect_reasoning_to_content(self):
        """فحص source code: لا يُسمح بسطر `delta['content'] = delta['reasoning']`."""
        source = (_REPO_ROOT / "app/core/gateway/simple_client.py").read_text(encoding="utf-8")
        # Old code (D-067 removed): `delta["content"] = delta["reasoning"]`
        forbidden_patterns = [
            'delta["content"] = delta["reasoning"]',
            "delta['content'] = delta['reasoning']",
            'delta.get("content") or delta.get("reasoning"',
            "delta.get('content') or delta.get('reasoning'",
        ]
        for pat in forbidden_patterns:
            assert pat not in source, (
                f"Source contains forbidden reasoning→content leak pattern: {pat!r}. "
                f"ISS-079 showed this caused English thinking text to bleed into "
                f"Arabic responses ('We need to respond as a brilliant professor...')."
            )


class TestCatastropheDeepScenarioRegression:
    """اختبار سيناريو حي مُصغّر: رسالة كارثية طويلة مع تكرار كتل."""

    def test_sanitize_removes_adjacent_duplicate_blocks(self):
        repeated_block = (
            "🎲 مسألة احتمالات\n"
            "شرح تفاعلي خطوة بخطوة\n"
            "1) نحدد الفضاء الاحتمالي.\n"
            "2) نطبق التوافيق.\n"
            "3) نتحقق من النتيجة.\n"
        )
        raw = (
            "Okay, the user asked for help.\n"
            f"{repeated_block}\n\n"
            f"{repeated_block}\n\n"
            "النتيجة النهائية: صحيحة."
        )
        cleaned = _local_graph._sanitize_local_graph_response(raw, "educational")
        assert cleaned.count("🎲 مسألة احتمالات") == 1
        assert "النتيجة النهائية: صحيحة." in cleaned

    def test_sanitize_keeps_non_adjacent_sections(self):
        """لا نحذف فقرة قد تتكرر لاحقاً بعد فاصل معرفي مختلف."""
        block_a = "عنوان A\nشرح مختصر."
        block_b = "عنوان B\nشرح مختلف."
        raw = f"{block_a}\n\n{block_b}\n\n{block_a}"
        cleaned = _local_graph._sanitize_local_graph_response(raw, "educational")
        assert cleaned.count("عنوان A") == 2
        assert "عنوان B" in cleaned

    def test_sanitize_removes_non_adjacent_long_marker_blocks(self):
        """نحذف تكرار الكتل التعليمية الطويلة حتى لو كانت غير متجاورة."""
        loop_block = (
            "🎲 مسألة احتمالات\n"
            "شرح تفاعلي خطوة بخطوة\n"
            "1) نحدد الفضاء الاحتمالي.\n"
            "2) نطبق التوافيق.\n"
            "3) نتحقق من النتيجة.\n"
            "تفصيل إضافي طويل لضمان تجاوز حد الطول المطلوب في de-dup."
        )
        bridge = "فقرة انتقالية جديدة غير مكررة."
        raw = f"{loop_block}\n\n{bridge}\n\n{loop_block}"
        cleaned = _local_graph._sanitize_local_graph_response(raw, "educational")
        assert cleaned.count("🎲 مسألة احتمالات") == 1
        assert bridge in cleaned

    def test_sanitize_removes_near_duplicate_scaffold_without_fixed_markers(self):
        """نحذف القالب الطويل حتى لو اختلف العنوان/الترقيم بشكل سطحي."""
        block_1 = (
            "مخطط حل التمرين\n"
            "1) نحدد المعطيات الأساسية في نص السؤال.\n"
            "2) نختار نموذج السحب المناسب ثم نكتب الفضاء.\n"
            "3) نحسب باحترام شرط عدم الإرجاع خطوة بخطوة.\n"
            "4) ننهي بتحقق عددي سريع يثبت تماسك النتيجة.\n"
        )
        block_2 = (
            "خارطة حل المسألة\n"
            "1) نحدد المعطيات الأساسية في نص السؤال.\n"
            "2) نختار نموذج السحب المناسب ثم نكتب الفضاء.\n"
            "3) نحسب باحترام شرط عدم الإرجاع خطوة بخطوة.\n"
            "4) ننهي بتحقق عددي سريع يثبت تماسك النتيجة.\n"
        )
        raw = f"{block_1}\n\nفقرة وسيطة.\n\n{block_2}"
        cleaned = _local_graph._sanitize_local_graph_response(raw, "educational")
        assert cleaned.count("نحدد المعطيات الأساسية") == 1
        assert "فقرة وسيطة." in cleaned


class TestPrecisionGuardrail:
    """تحقق أن حارس الدقة يربط الرد مباشرة بمعطيات سؤال الطالب."""

    def test_build_precision_guardrail_includes_question_entities(self):
        q = "تمرين احتمالات 2024: كرات بيضاء وحمراء وخضراء، اسحب 3 بدون إرجاع وارسم شجرة."
        guard = _local_graph._build_precision_guardrail(q, "educational")
        assert "حارس الدقة المرتبط بالسؤال" in guard
        assert "2024" in guard
        assert "3" in guard
        assert "بيضاء" in guard and "حمراء" in guard and "خضراء" in guard
        assert "شجرة احتمالات" in guard or "شجرة" in guard

    def test_build_precision_guardrail_disabled_for_chat(self):
        guard = _local_graph._build_precision_guardrail("السلام عليكم", "chat")
        assert guard == ""

    def test_build_precision_guardrail_reads_context_entities(self):
        context = (
            "سياق المحادثة السابقة:\n"
            "تمرين 2024: كرات بيضاء وحمراء وخضراء.\n\n"
            "السؤال الحالي: اشرح المطلوب."
        )
        guard = _local_graph._build_precision_guardrail(context, "educational")
        assert "2024" in guard
        assert "بيضاء" in guard and "حمراء" in guard and "خضراء" in guard


class TestQuestionAlignmentSanitizer:
    """D-090: منع اختلاق ألوان غير موجودة في نص التمرين."""

    def test_strip_unrequested_color_lines_probability(self):
        question = "تمرين احتمالات: لدينا كرات بيضاء وحمراء فقط."
        answer = (
            "لدينا كرات بيضاء وحمراء.\nكما توجد كرات زرقاء وسوداء.\nنحسب الآن الاحتمال المطلوب."
        )
        cleaned = _local_graph._strip_unrequested_color_lines(question, answer, "educational")
        assert "زرقاء" not in cleaned and "سوداء" not in cleaned
        assert "بيضاء" in cleaned and "حمراء" in cleaned

    def test_strip_unrequested_color_lines_non_probability_untouched(self):
        question = "اشرح الاشتقاق."
        answer = "ألوان: حمراء وزرقاء."
        cleaned = _local_graph._strip_unrequested_color_lines(question, answer, "educational")
        assert cleaned == answer
