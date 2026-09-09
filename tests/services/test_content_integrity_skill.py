r"""ISS-114 (D-106) — اختبارات StreamIntegrityFilter / ContentIntegritySkill.

يغطّي: حذف الغارباج اللاتيني، carry عبر chunks مقسومة، صمود الـ allowlist و
LaTeX حرفياً، passthrough الفرنسي، تنظيف HTML، fail-open، وعدم فقدان bytes عند
flush.
"""

from __future__ import annotations

from app.services.skills.content_integrity_skill import (
    ContentIntegrityInput,
    ContentIntegritySkill,
    StreamIntegrityFilter,
    sanitize_final_text,
)


def _run(chunks: list[str]) -> tuple[str, int, bool]:
    flt = StreamIntegrityFilter()
    out = "".join(flt.feed(c) for c in chunks) + flt.flush()
    return out, flt.tokens_stripped, flt.html_stripped


class TestLatinGarbage:
    def test_strips_known_garbage_tokens(self) -> None:
        out, stripped, _ = _run(
            [
                "المتغير العشوائي experiences_random يصف نتيجة، وجسر brückecónceptual "
                "بين الأفكار، نجاح exitos كبير Sweg وEingaben هنا."
            ]
        )
        for garbage in ("experiences_random", "brückecónceptual", "exitos", "Sweg", "Eingaben"):
            assert garbage not in out
        assert stripped >= 5
        assert "المتغير العشوائي" in out and "يصف نتيجة" in out

    def test_chunk_split_word_carry(self) -> None:
        """chunk يقسم كلمة غارباج → الجزآن يُحذفان معاً (اختبار الـ carry)."""
        out, _, _ = _run(
            ["المتغير experien", "ces_random بعدها يأتي شرح كامل للموضوع المطروح في النص العربي."]
        )
        assert "experiences_random" not in out
        assert "experien" not in out and "ces_random" not in out
        assert "المتغير" in out and "بعدها يأتي شرح" in out


class TestAllowlistAndLatex:
    def test_technical_tokens_survive(self) -> None:
        src = (
            "نحسب sin(x) و cos(x) ثم lim و dx، مع probabilité عالية والدالة fonction "
            "وقيمة exercice محدّدة هنا في هذا النص التعليمي العربي الطويل الكافي."
        )
        out, stripped, _ = _run([src])
        for tok in ("sin", "cos", "lim", "dx", "probabilité", "fonction", "exercice"):
            assert tok in out
        assert stripped == 0

    def test_latex_byte_identical_even_with_latin_inside(self) -> None:
        latex = "$$P(A)=\\frac{4}{11}\\boxed{experiences}$$"
        src = "النتيجة النهائية للحادثة المطلوبة في هذا التمرين هي " + latex + " تماماً."
        out, _, _ = _run([src])
        assert latex in out  # محتوى الرياضيات لا يُمسّ أبداً

    def test_short_tokens_allowed(self) -> None:
        src = "الاحتمال P(A) والأمل E(X) ودالة f(x) كلها معرّفة في هذا التمرين العربي الطويل."
        out, stripped, _ = _run([src])
        assert "P(A)" in out and "E(X)" in out and "f(x)" in out
        assert stripped == 0


class TestHtmlLeak:
    def test_strips_html_tags(self) -> None:
        src = (
            '<div class="card">شرح الحادثة P(A)</div> ثم نص عربي طويل كافٍ '
            "لتجاوز نافذة القرار اللغوي العربية المطلوبة هنا تماماً."
        )
        out, _, html = _run([src])
        assert "<div" not in out and "</div>" not in out
        assert 'class="card"' not in out
        assert "شرح الحادثة P(A)" in out
        assert html is True

    def test_split_tag_across_chunks(self) -> None:
        out, _, html = _run(
            ["نص عربي طويل كافٍ لتجاوز نافذة القرار اللغوي العربية هنا <di", "v>محتوى</div> تمام."]
        )
        assert "<div" not in out and "<di" not in out
        assert "محتوى" in out
        assert html is True


class TestFrenchPassthrough:
    def test_french_dominant_not_stripped(self) -> None:
        src = (
            "La probabilité de cet <b>evenement</b> est calculee avec la formule "
            "classique des tirages simultanes sans remise dans cet exercice."
        )
        out, stripped, html = _run([src])
        assert "probabilité" in out and "calculee" in out and "formule" in out
        assert stripped == 0  # الوضع غير العربي → لا فلترة لاتيني
        assert "<b>" not in out and html is True  # HTML يُنظَّف في كل الأوضاع


class TestRobustness:
    def test_flush_no_byte_loss_mid_carry(self) -> None:
        """انتهاء البثّ في منتصف كلمة عربية (لا تُحذف، تُفرَّغ في flush)."""
        flt = StreamIntegrityFilter()
        emitted = flt.feed("هذا نص عربي طويل كافٍ لتجاوز نافذة القرار اللغوي ثم كلمة")
        emitted += flt.flush()
        assert "كلمة" in emitted

    def test_fail_open_returns_raw(self, monkeypatch) -> None:
        flt = StreamIntegrityFilter()

        def _boom(_self_text):
            raise RuntimeError("forced")

        monkeypatch.setattr(flt, "_walk", _boom)
        # نص ≥ نافذة القرار ليُستدعى المعالج الداخلي (الذي نُفجّره).
        raw = "نص عربي خام يجب أن يُرجَع كما هو عند فشل الحارس داخلياً. " * 6
        out = flt.feed(raw)
        assert "نص عربي خام" in out  # fail-open: النص الخام يُرجَع، لا يُكسر الدور

    def test_skill_facade_check(self) -> None:
        skill = ContentIntegritySkill()
        res = skill.check(
            ContentIntegrityInput(
                text="المتغير experiences_random يصف نتيجة التجربة العشوائية في هذا التمرين العربي."
            )
        )
        assert "experiences_random" not in res.cleaned_text
        assert res.tokens_stripped >= 1
        assert res.passed is True


def test_sanitize_final_text_helper() -> None:
    out = sanitize_final_text(
        "الإجابة النهائية exitos للحادثة المطلوبة في هذا التمرين التعليمي العربي الطويل."
    )
    assert "exitos" not in out
    assert "الإجابة النهائية" in out


class TestBranchCoverage:
    """تغطية الفروع المتبقية (guards الفارغة/المعطَّلة + LaTeX-command + الواجهة)."""

    def test_empty_chunk_and_disabled_feed(self) -> None:
        flt = StreamIntegrityFilter()
        assert flt.feed("") == ""  # chunk فارغ
        flt._disabled = True
        assert flt.feed("نص") == "نص"  # معطَّل ⇒ خام
        assert flt.flush() == ""  # flush معطَّل

    def test_backslash_latex_command_allowed_in_prose(self) -> None:
        # أمر LaTeX شارد خارج الرياضيات مسبوق بـ \ يُسمح به (L358).
        src = (
            "النص العربي الطويل الكافي لتجاوز نافذة القرار اللغوي العربية ثم \\alpha "
            "يظهر كأمر شارد هنا تماماً في الجملة."
        )
        out, stripped, _ = _run([src])
        assert "alpha" in out
        assert stripped == 0

    def test_sanitize_final_text_empty(self) -> None:
        assert sanitize_final_text("") == ""

    def test_check_accepts_raw_string(self) -> None:
        res = ContentIntegritySkill().check(
            "نص عربي نظيف وطويل كافٍ لتجاوز نافذة القرار اللغوي العربية المطلوبة هنا."
        )
        assert res.passed is True
        assert res.tokens_stripped == 0

    def test_stream_filter_factory(self) -> None:
        assert isinstance(ContentIntegritySkill.stream_filter(), StreamIntegrityFilter)

    def test_carry_trailing_alpha_then_resolve(self) -> None:
        # ذيل لاتيني ممتد عبر الـ chunks ثم يُحَل (carry loop L293).
        flt = StreamIntegrityFilter()
        out = flt.feed("نص عربي طويل كافٍ لتجاوز نافذة القرار اللغوي العربية ثم sin")
        out += flt.feed("us نهاية") + flt.flush()
        # «sinus» ليست في allowlist (sin نعم، sinus لا) ⇒ تُحذف ككلمة كاملة.
        assert "نهاية" in out and "sinus" not in out


class TestD289StructuralProtection:
    r"""ISS-201 (D-289): الحماية البنيوية — اللاتيني الذي هو **بنية** ليس غارباجاً.

    العطل المرصود حيّاً: بعد إصلاح سلسلة النماذج وصلت إجابات مبتورة للطالب —
    `https://example.com/physics` صارت `://./`، و`Newton` حُذف كلياً. الحارس صُمِّم
    ليقتل «experiences_random»، لا ليمزّق الروابط والمُعرِّفات والمصطلحات العلمية.
    """

    _PAD = "شرح مفصّل لقانون نيوتن الثاني في الفيزياء: القوة محصلة تساوي الكتلة في التسارع، " * 3

    def test_url_survives(self) -> None:
        src = self._PAD + "راجع https://example.com/physics للمزيد."
        out, stripped, _ = _run([src])
        assert "https://example.com/physics" in out
        assert stripped == 0

    def test_dotted_and_numbered_identifiers_survive(self) -> None:
        src = self._PAD + "شغّل python3.12 ثم اكتب الملف main.py وreadme.txt هنا."
        out, _, _ = _run([src])
        assert "python3.12" in out and "main.py" in out and "readme.txt" in out

    def test_inline_code_span_survives(self) -> None:
        src = self._PAD + "نفّذ الأمر `run_live_e2e` ثم راجع النتيجة."
        out, _, _ = _run([src])
        assert "run_live_e2e" in out

    def test_si_unit_vocabulary_survives(self) -> None:
        """المفردات العلمية المكتوبة لاتينياً في نصٍّ عربي سليم (توسيع allowlist)."""
        src = self._PAD + "الوحدة Newton والجهد بالفولت volt والطاقة joule والمقاومة ohm."
        out, _, _ = _run([src])
        for word in ("Newton", "volt", "joule", "ohm"):
            assert word in out, f"مصطلح علمي حُذف: {word}"

    def test_real_garbage_is_still_stripped(self) -> None:
        """الغارباج العاري (بلا بنية، خارج allowlist) يبقى محذوفاً — لا ارتخاء في الحراسة."""
        src = self._PAD + "كلمات Eingaben exitos Sweg دخيلة تماماً."
        out, stripped, _ = _run([src])
        assert stripped >= 2 and "Eingaben" not in out and "exitos" not in out

    def test_model_id_leak_in_prose_is_not_math(self) -> None:
        """مُعرِّف نموذج ملتحم بنقاط/شرطات يبقى (يُعالَج في طبقة الـ meta لاحقاً)،
        لكن لا يُترك كـ«جملة إنجليزية»: الكلمة العامة حوله تُحذف."""
        src = self._PAD + "من google/gemma-4-31b-it:free انتهى الشرح"
        out, _, _ = _run([src])
        assert "gemma-4-31b-it" in out
