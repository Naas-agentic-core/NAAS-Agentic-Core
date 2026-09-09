r"""ContentIntegritySkill — حارس نزاهة المحتوى المواجه للطالب (ISS-114 · D-106).

كارثتان حيتان دفعتا هذا الـ Skill:
1. **غارباج لاتيني** («experiences_random»، «brückecónceptual»، «exitos»،
   «Eingaben»، «Sweg») يتسرّب من النماذج المجانية وسط النص العربي ويصل للطالب.
2. **تسريب HTML خام** («قم بتوليد واجهة» → الـ LLM يكتب `<div class="card">`).

الثغرة الأكبر: بثّ orchestrator-service (MODE_B) كان يُمرَّر للطالب **بلا أي
حارس** (حلقة `aiter_lines` في orchestrator_client). الحُرّاس القديمة:
- `arabic_stream_guard` يفحص أول 200 حرف فقط ثم يحذف Cyrillic/CJK + لاتيني ملتصق.
- `response_sanitizer` (الخدمة) يحذف Cyrillic/CJK/Korean — لا لاتيني عشوائي.
لا أحد يلتقط اللاتيني المفصول بمسافات على كامل البثّ، ولا HTML على مسار الخدمة.

التصميم — `StreamIntegrityFilter` ذو حالة يعمل على **كامل التيار**:
- قرار وضع اللغة (أول ~200 حرف): عربي-غالب → فلترة لاتيني لكامل البثّ؛ وإلا
  (فرنسي/Darija شرعي) → تنظيف HTML فقط (يحمي الإجابات الفرنسية المشروعة).
- عبور الرياضيات: LaTeX (`$...$`, `$$...$$`, `\(...\)`, `\[...\]`) يُبثّ حرفياً
  أبداً (قوانين D-051/D-062) — صفر مساس.
- carry لحدود الكلمات: chunks تقسم الكلمات/الوسوم/المحددات → يُحجز الذيل المريب
  (سقف 96 حرفاً) حتى الـ chunk التالي؛ `flush()` يُفرغ دائماً (صفر فقدان bytes).
- heuristic اللاتيني: ALLOW إذا ≤2 حرف (P(A)/dx/ln) أو في `_TECH_ALLOWLIST`
  (مفردات رياضية + BAC فرنسية، مقارنة بعد NFD-strip فـ probabilité تنجو) أو
  مسبوق بـ `\`؛ STRIP كل ما عداه. الـ allowlist محافظة — توسيعها = doctrine bump.
- fail-open مطلق: أي استثناء ⇒ تعطيل دائم ⇒ النص الخام (لا يكسر دور الطالب).
"""

from __future__ import annotations

import contextlib
import logging
import re
import time
import unicodedata
from typing import Literal

from pydantic import Field

from app.core.schemas import RobustBaseModel
from app.services.skills.base import BaseSkill
from app.services.skills.doctrine import CONTENT_INTEGRITY_DOCTRINE_VERSION

logger = logging.getLogger("cogniforge.skills.content_integrity")

DOCTRINE_VERSION = CONTENT_INTEGRITY_DOCTRINE_VERSION

# ── ثوابت السياسة (لا تُعدَّل بدون ترقية doctrine) ───────────────────────────────
_DECISION_WINDOW = 200  # حروف القرار اللغوي (مرة واحدة في بداية البثّ)
_CARRY_CAP = 96  # أقصى ذيل محجوز عبر الـ chunks (يمنع تضخّم غير محدود)
_ARABIC_MODE_THRESHOLD = 0.5  # نسبة الحروف العربية للنثر لتفعيل فلترة اللاتيني

# مفردات تقنية مسموحة (تُخزَّن lowercase + بلا تشكيل لاتيني، تُقارن بعد NFD-strip).
_TECH_ALLOWLIST: frozenset[str] = frozenset(
    {
        # رياضيات إنجليزية شائعة
        "sin",
        "cos",
        "tan",
        "cot",
        "sec",
        "csc",
        "lim",
        "log",
        "ln",
        "exp",
        "max",
        "min",
        "mod",
        "arg",
        "det",
        "gcd",
        "lcm",
        "sup",
        "inf",
        "abs",
        "sqrt",
        "frac",
        "sum",
        "int",
        "dx",
        "dy",
        "dt",
        "boxed",
        "cdot",
        "alpha",
        "beta",
        "gamma",
        "delta",
        "theta",
        "lambda",
        "pi",
        "mu",
        "sigma",
        "infty",
        "mathbb",
        "vec",
        "overline",
        "begin",
        "end",
        "cases",
        "matrix",
        # مصطلحات عامة مقبولة
        "bac",
        "latex",
        "html",
        "css",
        "json",
        "url",
        "id",
        "ok",
        "qcm",
        # مفردات BAC فرنسية (بعد إزالة التشكيل اللاتيني)
        "probabilite",
        "probabilites",
        "fonction",
        "fonctions",
        "limite",
        "suite",
        "suites",
        "derivee",
        "derivees",
        "integrale",
        "integrales",
        "complexe",
        "complexes",
        "tirage",
        "remise",
        "simultanement",
        "evenement",
        "variable",
        "aleatoire",
        "esperance",
        "loi",
        "exercice",
        "solution",
        "theoreme",
        "demonstration",
        "equation",
        "matrice",
        # D-289 (ISS-201): مفردات SI/الفيزياء/الكيمياء التي يكتبها النموذج باللاتينية
        # داخل نصٍّ عربي سليم — حذفُها كان يُسلِّم إجابة مبتورة («الوحدة (N)» بعد
        # حذف Newton). مقيَّدة بمصطلحات علمية/ملفية، لا كلمات إنجليزية عامة (تلك
        # بقايا reasoning وتُحذف عمداً).
        "newton",
        "newtons",
        "joule",
        "joules",
        "watt",
        "watts",
        "pascal",
        "ampere",
        "volt",
        "volts",
        "ohm",
        "ohms",
        "hertz",
        "coulomb",
        "kelvin",
        "celsius",
        "mole",
        "molecules",
        "molecule",
        "atom",
        "atoms",
        "electron",
        "electrons",
        "proton",
        "neutron",
        "photon",
        "ion",
        "ions",
        "energy",
        "power",
        "force",
        "mass",
        "velocity",
        "acceleration",
        "momentum",
        "friction",
        "tension",
        "pressure",
        "density",
        "volume",
        "temperature",
        "frequency",
        "wavelength",
        "current",
        "voltage",
        "resistance",
        "capacity",
        "inductance",
        "magnetic",
        "electric",
        "gravity",
        "inertia",
        "torque",
        "kinetic",
        "potential",
        "equilibrium",
        "oxidation",
        "reduction",
        "catalyst",
        "acid",
        "alkane",
        "alcohol",
        "ester",
        "ether",
        "polymer",
        "monomer",
        "ph",
        "python",
        "java",
        "javascript",
        "algorithm",
        "api",
        "pdf",
        "csv",
        "xlsx",
        "docx",
        "http",
        "https",
        "ftp",
        "smtp",
        "tcp",
        "udp",
        "utf8",
        "ascii",
        "sql",
    }
)

# ── أنماط (مُجمَّعة مرة واحدة) ───────────────────────────────────────────────────
# رمز لاتيني (ASCII + Latin-1/Extended المُشكَّل) مع روابط snake/apostrophe.
_LATIN_TOKEN = re.compile(r"[A-Za-zÀ-ɏ]+(?:[_'][A-Za-zÀ-ɏ]+)*")

# D-289 (ISS-201): بنيةُ نصية مشروعة — لا غارباج نموذج. الغارباج المرصود في
# ISS-114 كلماتٌ عارية («experiences_random»، «exitos»، «Eingaben»)؛ أما اللاتيني
# الذي يحمل رقماً أو punctuation مساري (`/`، `.`، `:`، `-`) أو يقع داخل شيفرة
# مُضمَّنة فهو عنوان/ملفُ/مُعرِّفٌ **مقصود** كتبه النموذج عن قصد: `https://…`،
# `gpt-oss-20b:free`، `python3.12`، `max_retry`. حذفُها كان يُسلِّم الطالب نصّاً
# مبتوراً («راجع https://foo.bar» → «راجع ://.») أي إجابةً خاطئة بعد إصلاح
# السلسلة نفسها — ولهذا تُحمى هيكلياً بدل توسيع الـ allowlist كلمةً كلمةً.
_STRUCTURAL_NEIGHBOURS = "/.:-_="
_STRUCTURAL_BEFORE = re.compile(r"(?:https?://|www\.)[A-Za-z0-9./:_\-]*$")

# محددات الرياضيات (opener/closer).
_MATH_DELIM = re.compile(r"\$\$|\$|\\\(|\\\)|\\\[|\\\]")
# وسوم HTML (فتح/إغلاق/مغلق ذاتياً).
_HTML_TAG = re.compile(r"</?[A-Za-z][A-Za-z0-9]*(?:\s[^>]*?)?/?>")
# أسوار شيفرة Markdown (```html ... ```).
_CODE_FENCE = re.compile(r"```[A-Za-z]*\n?|```")
# مسافات مكرّرة (تنظيف بعد الحذف).
_MULTISPACE = re.compile(r"[ \t]{2,}")
# أزواج الفتح/الإغلاق للرياضيات.
_MATH_PAIRS: dict[str, str] = {"$$": "$$", "$": "$", "\\(": "\\)", "\\[": "\\]"}
_MATH_OPENERS = frozenset(_MATH_PAIRS)

# ── D-115: المُطهّر المُصفّح — فواصل ⟦⟧ مشوّهة + تعليمات system prompt مُسرَّبة ──
_BRACKET_BLOCK_RE = re.compile(r"⟦[^⟧\n]{0,120}⟧")
_MARKER_PHRASE_RE = re.compile(r"/?\s*مثال_محلول")
# D-117: العلامات الداخلية المُسرَّبة («الطالب يرى التعليم لا هندسة التعليم») —
# أي سطر يصف تفكير النظام نفسه (توجيه D-104، قالب D-115 السقراطي، وضع MODE_B،
# هلوسة «Konzept») يُحذف بالكامل. دفاع عميق: حتى لو سرّب النموذج العنوان، يُمحى.
_INSTRUCTION_LEAK_RE = re.compile(
    r"(?im)^.*?(?:WARM[\s\-]?UP|the instruction must|coalesced|rendered in a|"
    r"single flowing syntax|semantic nuances|prepares the learner|Konzept|"
    r"التوجيه التربوي|توجيه تربوي|تفعيل الفهم المبكر|مثال_محلول|"
    r"مستوى الدعم|نوع المسألة|سؤال تشخيصي|أصغر خطوة|اطلب من الطالب|"
    r"وضع الشرح العميق|فهمت المطلوب).*$"
)
# D-116: علامات تجميعية لاتينية دخيلة (U+0300–U+036F) — تظهر فوق حروف عربية كغارباج
# («لا̅ يمكن̅»). حركات العربية (U+064B–U+065F، U+0670) خارج هذا النطاق فتبقى سليمة.
_COMBINING_MARKS_RE = re.compile(r"[̀-ͯ]")


def _strip_garbage_markers(text: str) -> str:
    """D-115/D-116: يحذف الفواصل المشوّهة + تعليمات الـ system prompt المُسرَّبة +
    العلامات التجميعية اللاتينية الدخيلة.

    حتمي، fail-open. يُطبَّق على كل نثر (داخل/خارج الوضع العربي) — `⟦⟧` و
    `WARM-UP` والعلامات الدخيلة يجب ألا تصل الطالب أبداً مهما تشوّهت أو انقسمت.
    """
    if not text:
        return text or ""
    try:
        out = _BRACKET_BLOCK_RE.sub("", text)
        out = out.replace("⟦", "").replace("⟧", "")
        out = _COMBINING_MARKS_RE.sub("", out)  # D-116: علامات U+0305 الدخيلة
        out = _MARKER_PHRASE_RE.sub("", out)
        return _INSTRUCTION_LEAK_RE.sub("", out)
    except Exception:  # pragma: no cover — fail-open
        return text


def _is_structural_token(tok: str, text: str, pos: int) -> bool:
    """هل هذا اللاتيني جزءٌ من بنية نصية مشروعة (URL/مسار/مُعرِّف/شيفرة)؟

    D-289 — لا يمسّ قرار الـ allowlist ولا وضع الرياضيات: يضيف فقط استثناءً
    بنيوياً لا يمكن أن يكون غارباجَ نموذج.
    """
    # داخل شيفرة مُضمَّنة `...` أو ```...```
    if text.count("`", 0, pos) % 2 == 1:
        return True
    if _STRUCTURAL_BEFORE.match(text[max(0, pos - 12) : pos]):
        return True  # امتداد عنوان بعد // أو www.
    end = pos + len(tok)
    before = text[pos - 1] if pos > 0 else ""
    after = text[end] if end < len(text) else ""
    if before in _STRUCTURAL_NEIGHBOURS or after in _STRUCTURAL_NEIGHBOURS:
        return True  # ملتحم بمسار/وسم (example.com، gpt-oss، F=ma)
    # مُعرِّف مرقَّم (python3، utf8)
    return before.isdigit() or after.isdigit()


def _strip_accents(token: str) -> str:
    """يزيل التشكيل اللاتيني (é→e) للمقارنة مع الـ allowlist."""
    nfkd = unicodedata.normalize("NFKD", token)
    return "".join(c for c in nfkd if not unicodedata.combining(c)).lower()


def _arabic_prose_ratio(text: str) -> float:
    """نسبة الحروف العربية إلى مجموع الحروف (عربي + لاتيني). 1.0 إن لا حروف."""
    arabic = 0
    latin = 0
    for c in text:
        if "؀" <= c <= "ۿ":
            arabic += 1
        elif (c.isascii() and c.isalpha()) or ("À" <= c <= "ɏ"):
            latin += 1
    total = arabic + latin
    return arabic / total if total else 1.0


# ── العقود (Pydantic) ────────────────────────────────────────────────────────────


class ContentIntegrityInput(RobustBaseModel):
    """مدخلات الفحص الدفعي (one-shot)."""

    text: str = Field(..., max_length=200_000)
    mode: Literal["stream_chunk", "final"] = "final"


class ContentIntegrityOutput(RobustBaseModel):
    """مخرج الفحص الدفعي."""

    cleaned_text: str
    tokens_stripped: int = 0
    html_stripped: bool = False
    arabic_mode: bool = True
    passed: bool = True
    doctrine_version: str = DOCTRINE_VERSION


# ── القياس (Prometheus عبر التيليمتري الموحَّد) ────────────────────────────────────


def _record_metric(mode: str, status: str, tokens: int, duration_s: float) -> None:
    with contextlib.suppress(Exception):
        from app.telemetry.unified_observability import get_unified_observability

        obs = get_unified_observability()
        obs.record_metric(
            "skill.content_integrity.invocations.total",
            1.0,
            labels={"mode": mode, "status": status},
        )
        if tokens:
            obs.record_metric("skill.content_integrity.tokens_stripped.total", float(tokens))
        obs.record_metric("skill.content_integrity.duration_seconds", duration_s)


# ── المرشِّح ذو الحالة (قلب الإصلاح) ──────────────────────────────────────────────


class StreamIntegrityFilter:
    """مرشِّح بثّ ذو حالة: يلتقط الغارباج اللاتيني وتسريب HTML على كامل التيار.

    استخدام:
        f = StreamIntegrityFilter()
        for chunk in stream:
            emit(f.feed(chunk))
        emit(f.flush())  # إلزامي — يُفرغ الذيل المحجوز
    """

    def __init__(self) -> None:
        self._decided = False
        self._arabic_mode = True
        self._decision_buf = ""
        self._carry = ""
        self._in_math = False
        self._math_opener = ""
        self._disabled = False
        self.tokens_stripped = 0
        self.html_stripped = False

    # ── واجهة عامة ────────────────────────────────────────────────────────────
    def feed(self, chunk: str) -> str:
        if self._disabled or not chunk:
            return chunk or ""
        try:
            if not self._decided:
                self._decision_buf += chunk
                if len(self._decision_buf) < _DECISION_WINDOW:
                    return ""  # نحجز حتى يكتمل نافذة القرار
                chunk = self._take_decision_buffer()
            buf = self._carry + chunk
            safe, self._carry = self._safe_split(buf)
            return self._walk(safe)
        except Exception:  # pragma: no cover - fail-open مطلق
            logger.debug("content_integrity feed failed — disabling (fail-open)", exc_info=True)
            self._disabled = True
            pending = self._decision_buf + self._carry + chunk
            self._decision_buf = self._carry = ""
            return pending

    def flush(self) -> str:
        if self._disabled:
            return ""
        try:
            remaining = self._take_decision_buffer() if not self._decided else ""
            buf = self._carry + remaining
            self._carry = ""
            return self._walk(buf)
        except Exception:  # pragma: no cover
            logger.debug("content_integrity flush failed (fail-open)", exc_info=True)
            self._disabled = True
            pending = self._decision_buf + self._carry
            self._decision_buf = self._carry = ""
            return pending

    # ── داخلي ────────────────────────────────────────────────────────────────
    def _take_decision_buffer(self) -> str:
        """يحسم وضع اللغة ويُرجِع المخزَّن لمعالجته كأول دفعة."""
        sample = _MATH_DELIM.sub(" ", self._decision_buf)
        self._arabic_mode = _arabic_prose_ratio(sample) >= _ARABIC_MODE_THRESHOLD
        self._decided = True
        buffered = self._decision_buf
        self._decision_buf = ""
        return buffered

    def _safe_split(self, buf: str) -> tuple[str, str]:
        """يفصل البادئة الآمنة عن ذيل قد يكمل في الـ chunk التالي (حد _CARRY_CAP)."""
        n = len(buf)
        min_keep = max(0, n - _CARRY_CAP)
        i = n
        while i > min_keep:
            ch = buf[i - 1]
            # حروف (وسط كلمة) / بداية وسم / محدد رياضي / سور شيفرة محتمل
            if ch.isalpha() or ch in "_'`$\\<":
                i -= 1
            else:
                break
        return buf[:i], buf[i:]

    def _walk(self, text: str) -> str:
        """يمرّ على النص: الرياضيات حرفياً، النثر يُفلتَر — مع تتبّع حالة الرياضيات."""
        if not text:
            return ""
        out: list[str] = []
        pos = 0
        for m in _MATH_DELIM.finditer(text):
            seg = text[pos : m.start()]
            delim = m.group(0)
            if self._in_math:
                out.append(seg)  # داخل الرياضيات → حرفياً
                if _MATH_PAIRS.get(self._math_opener) == delim:
                    self._in_math = False
                    self._math_opener = ""
                out.append(delim)
            else:
                out.append(self._filter_prose(seg))
                if delim in _MATH_OPENERS:
                    self._in_math = True
                    self._math_opener = delim
                out.append(delim)
            pos = m.end()
        tail = text[pos:]
        out.append(tail if self._in_math else self._filter_prose(tail))
        return "".join(out)

    def _filter_prose(self, prose: str) -> str:
        if not prose:
            return ""
        # D-115: حذف الفواصل المشوّهة + تعليمات system prompt المُسرَّبة دائماً.
        cleaned = _strip_garbage_markers(prose)
        cleaned = self._strip_markup(cleaned)
        if self._arabic_mode:
            cleaned = self._strip_latin_garbage(cleaned)
        return cleaned

    def _strip_markup(self, text: str) -> str:
        if "<" not in text and "`" not in text:
            return text
        new = _CODE_FENCE.sub("", text)
        new = _HTML_TAG.sub("", new)
        if new != text:
            self.html_stripped = True
        return new

    def _strip_latin_garbage(self, prose: str) -> str:
        def repl(match: re.Match[str]) -> str:
            tok = match.group(0)
            start = match.start()
            if self._allow_token(tok, prose, start):
                return tok
            self.tokens_stripped += 1
            return ""

        out = _LATIN_TOKEN.sub(repl, prose)
        return _MULTISPACE.sub(" ", out)

    @staticmethod
    def _allow_token(tok: str, text: str, pos: int) -> bool:
        # D-116: المتغيّرات القصيرة المسموحة ASCII فقط (x, n, dx, ln) — الحرف
        # اللاتيني المُلكَّن المنفرد (ë) غارباج هلوسة يُحذف، لا يُعدّ متغيّراً.
        if len(tok) <= 2:
            return tok.isascii()
        if pos > 0 and text[pos - 1] == "\\":
            return True  # أمر LaTeX شارد خارج الرياضيات
        if _is_structural_token(tok, text, pos):
            return True  # D-289: عنوان/مسار/مُعرِّف/شيفرة مُضمَّنة — ليست غارباجاً
        return _strip_accents(tok) in _TECH_ALLOWLIST


# ── المساعد الدفعي + الواجهة (façade) ─────────────────────────────────────────────


def sanitize_final_text(text: str, support_level: int | None = None) -> str:
    """تنظيف دفعي one-shot للنص النهائي (الإطار المحفوظ في DB).

    D-113: بعد تنظيف الغارباج/HTML، يمرّ النص عبر حارس حجب الإجابة النهائية
    (`AnswerRedactionSkill`) — شبكة الأمان الأخيرة ضد كشف الحل للطالب. fail-open.

    D-114: ``support_level == 1`` يُفعّل الإعفاء الواعي بالفواصل الحارسة — كتلة
    المثال المحلول (على مسألة مماثلة) تمرّ، وما عداها يُحجب (fail-closed).
    """
    if not text:
        return text or ""
    flt = StreamIntegrityFilter()
    cleaned = flt.feed(text) + flt.flush()
    try:
        from app.services.skills.answer_redaction_skill import redact_final_answers

        redacted, _ = redact_final_answers(cleaned, support_level)
        return redacted
    except Exception:  # pragma: no cover - fail-open
        logger.debug("answer redaction in sanitize_final_text failed (fail-open)", exc_info=True)
        return cleaned


class ContentIntegritySkill(BaseSkill):
    """واجهة Skill رسمية للـ registry + القياس (D-100).

    عقد دائم (لا يُكسر بدون ADR):
    1. كل بثّ مواجه للطالب يمرّ عبر المرشّح على **كامل التيار** لا أول نافذة فقط.
    2. وضع اللغة العربي يحمي الإجابات الفرنسية المشروعة من الحذف.
    3. spans الرياضيات (LaTeX) لا تُمسّ أبداً.
    4. الـ allowlist محافظة — توسيعها = doctrine bump.
    5. fail-open مطلق — فشل الحارس لا يكسر دور الطالب.
    6. HTML لا يصل نص الطالب أبداً — الواجهات حصراً عبر ui_component المُهيكلة.
    """

    VERSION = DOCTRINE_VERSION
    SKILL_NAME = "content_integrity"
    name = "content_integrity"

    def run(self, payload: ContentIntegrityInput | str) -> ContentIntegrityOutput:
        """Polymorphic entry point (BaseSkill) — delegates to :meth:`check`."""
        return self.check(payload)

    def check(self, payload: ContentIntegrityInput | str) -> ContentIntegrityOutput:
        t0 = time.perf_counter()
        if isinstance(payload, str):
            payload = ContentIntegrityInput(text=payload)
        flt = StreamIntegrityFilter()
        try:
            cleaned = flt.feed(payload.text) + flt.flush()
            out = ContentIntegrityOutput(
                cleaned_text=cleaned,
                tokens_stripped=flt.tokens_stripped,
                html_stripped=flt.html_stripped,
                arabic_mode=flt._arabic_mode,
                passed=True,
            )
            _record_metric(payload.mode, "success", flt.tokens_stripped, time.perf_counter() - t0)
            return out
        except Exception:  # pragma: no cover - fail-open
            logger.debug("content_integrity check failed (fail-open)", exc_info=True)
            _record_metric(payload.mode, "fallback", 0, time.perf_counter() - t0)
            return ContentIntegrityOutput(cleaned_text=payload.text, passed=False)

    @staticmethod
    def stream_filter() -> StreamIntegrityFilter:
        return StreamIntegrityFilter()


__all__ = [
    "ContentIntegrityInput",
    "ContentIntegrityOutput",
    "ContentIntegritySkill",
    "StreamIntegrityFilter",
    "sanitize_final_text",
]
