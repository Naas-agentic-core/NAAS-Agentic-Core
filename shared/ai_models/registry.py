"""سجلّ النماذج وقدراتها — D-067 يصير بوّابة لا تعليقاً (D-202).

لماذا سجلّ وليس قائمة أسماء
---------------------------
`model_chain.py` يُعلن **الترتيب**. ما لم يكن مُعلَناً في أيّ مكان هو **لماذا** يصلح
نموذجٌ للصدارة وآخر لا يصلح — كان ذلك يعيش في تعليقات نثرية، وتعليقٌ لا يمنع أحداً من
شيء. وقد كلّف ذلك المنصّة كارثةً حقيقية (ISS-079): نموذج تفكير-فقط في الصدارة يُرجِع
`content=None`، فوصل الطالبَ حرفياً «pepepe aaaa».

هنا تصير القدرة **بياناً مُصرَّحاً** مع دليلها وتاريخه، وتصير الأهلية للصدارة **شرطاً
يُفحَص** لا عرفاً يُتذكَّر. إضافة نموذجٍ تصير إدخالاً في السجلّ مع دليلٍ حيّ، لا تحريراً
في الكود يجتاز المراجعة لأنّه «سطرٌ واحد».

القاعدة الدائمة
---------------
**نموذجٌ في السلسلة بلا إدخال ⇒ CI أحمر. ونموذجٌ محظور في السلسلة ⇒ CI أحمر.** الحظر
لا يُرفَع بتحرير سطر: يحتاج دليلاً حيّاً جديداً بتاريخه في الإدخال نفسه.

عقد الموقع: stdlib فقط. لا استيراد من `app/` ولا من خدمة.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from enum import StrEnum
from typing import Final

from .model_chain import MODEL_CHAIN, PRIMARY_MODEL

__all__ = [
    "MODEL_REGISTRY",
    "REQUIRED_FOR_PRIMARY",
    "Capability",
    "ModelRecord",
    "ModelRegistryError",
    "assert_chain_is_registered",
    "assert_primary_is_eligible",
    "record_for",
]


class ModelRegistryError(ValueError):
    """خرقٌ لعقد السجلّ — نموذجٌ غير مُسجَّل أو غير مؤهّل للدور المطلوب."""


class Capability(StrEnum):
    """قدرةٌ **مُتحقَّقة حياً**، لا موعودة في بطاقة النموذج."""

    #: يُرجِع `content` حقيقياً — لا تفكيراً فقط. هذه هي قدرة ISS-079 بعينها.
    CONTENT_STREAM = "content_stream"
    ARABIC = "arabic"
    FRENCH = "french"
    DARIJA = "darija"
    LATEX = "latex"
    #: ينتهي بـ`finish=stop` لا بقطعٍ في المنتصف.
    CLEAN_FINISH = "clean_finish"


#: شروط الصدارة. ليست ذوقاً: كلٌّ منها فشلٌ حيّ مُوثَّق دفع ثمنه طالب.
REQUIRED_FOR_PRIMARY: Final[frozenset[Capability]] = frozenset(
    {
        Capability.CONTENT_STREAM,
        Capability.ARABIC,
        Capability.LATEX,
        Capability.CLEAN_FINISH,
    }
)


@dataclass(frozen=True)
class ModelRecord:
    """ما نعرفه عن نموذج — وكيف عرفناه."""

    model_id: str
    capabilities: frozenset[Capability]
    #: تاريخ آخر تحقّق حيّ. سجلٌّ بلا تاريخ ادّعاءٌ لا دليل.
    verified_on: date
    evidence: str
    #: سببُ الحظر إن كان محظوراً — نصٌّ غير فارغ يمنع أيّ دور.
    banned_reason: str = ""
    #: هل يُسمَح له بالصدارة؟ يُشتقّ، ولا يُكتَب يدوياً.
    notes: str = ""

    def __post_init__(self) -> None:
        if not self.model_id:
            raise ModelRegistryError("model_id is required")
        if not self.evidence:
            raise ModelRegistryError(f"{self.model_id}: a record without evidence is a claim")

    @property
    def is_banned(self) -> bool:
        return bool(self.banned_reason)

    @property
    def eligible_as_primary(self) -> bool:
        """
        مؤهّلٌ للصدارة؟

        محظورٌ ⇒ لا، مهما كانت قدراته. ونقصُ قدرةٍ واحدة من `REQUIRED_FOR_PRIMARY` ⇒ لا.
        """
        return not self.is_banned and self.capabilities >= REQUIRED_FOR_PRIMARY


_ALL: Final[frozenset[Capability]] = frozenset(Capability)

MODEL_REGISTRY: Final[dict[str, ModelRecord]] = {
    record.model_id: record
    for record in (
        ModelRecord(
            model_id="openai/gpt-oss-20b:free",
            capabilities=_ALL,
            verified_on=date(2026, 9, 9),
            evidence=(
                "D-167 live benchmark: 2102 chunks, 4762 chars Arabic + LaTeX, finish=stop. "
                "2026-09-09 (D-288): public /endpoints probe returns an EMPTY list — the free "
                "tier serves no endpoint for it anymore, so it is no longer PRIMARY."
            ),
            notes=(
                "القدرة مُتحقَّقة، والقدرةَ لا تُطعِم طالباً بلا endpoint: مُنحىً عن الصدارة إلى "
                "الذيل حتى يعود حيّاً (D-288). التحقّق من الخدمة حيّاً مسؤوليّة "
                "scripts/verify_model_registry_live.py، لا هذا الإدخال."
            ),
        ),
        ModelRecord(
            model_id="google/gemma-4-26b-a4b-it:free",
            capabilities=_ALL,
            verified_on=date(2026, 9, 9),
            evidence=(
                "D-177 live E2E: answered in Arabic + LaTeX after PRIMARY returned reasoning-only. "
                "2026-09-09 /endpoints probe: free endpoint alive (Google AI Studio, 262144 ctx, "
                "uptime 99.53%) — and served a live Arabic+LaTeX turn end to end under D-288."
            ),
        ),
        ModelRecord(
            model_id="google/gemma-4-31b-it:free",
            capabilities=_ALL,
            verified_on=date(2026, 9, 9),
            evidence=(
                "D-167 live benchmark: Arabic + LaTeX, clean finish. D-280 (2026-08-22): passed the "
                "full live matrix as CI PRIMARY. 2026-09-09 /endpoints probe: free endpoint alive "
                "(262144 ctx / 32768 max completion, uptime 99.61%). PRIMARY since D-288."
            ),
            notes="الصدارة المُتحقَّقة (D-067/D-167) والمُعلَنة في السلسلة (D-288).",
        ),
        ModelRecord(
            model_id="nvidia/nemotron-3-nano-30b-a3b:free",
            capabilities=frozenset({Capability.ARABIC, Capability.FRENCH}),
            verified_on=date(2026, 5, 17),
            evidence=(
                "D-067/ISS-079 live: content=None (English reasoning only) with system prompts "
                "over 1500 chars — reached a real student as 'pepepe aaaa'."
            ),
            banned_reason="PRIMARY-banned: reasoning-only under long system prompts (ISS-079).",
            notes="يبقى في الذيل محروساً بفحص content==0 — لا يُرقّى أبداً.",
        ),
        ModelRecord(
            model_id="openai/gpt-oss-120b:free",
            capabilities=frozenset({Capability.ARABIC, Capability.LATEX}),
            verified_on=date(2026, 9, 9),
            evidence=(
                "D-167: removed from the OpenRouter free tier (404); 2026-09-09 /endpoints probe "
                "still empty. Kept as an auto-recovery slot."
            ),
            notes="نموذجٌ ميّت تُخطّيه الحُرّاس فوراً — بقاؤه مجّاني وتعافيه آلي.",
        ),
        # أُدرِج في السلسلة (D-288) لأنه حيٌّ على الكتالوج المجاني، لا لأن قدرته النصية
        # مُتحقَّقة. قدراتٌ لم تُبنشَر = إدخالٌ بقدرات فارغة، لا ادّعاءٌ يسبق الدليل.
        ModelRecord(
            model_id="nvidia/nemotron-3.5-lightning:free",
            capabilities=frozenset(),
            verified_on=date(2026, 9, 9),
            evidence=(
                "2026-09-09 public /endpoints probe: free endpoint alive (NVIDIA, 1000000 ctx, "
                "65536 max completion, uptime 99.77% last 30m). D-280 wired it as the free-tier "
                "recovery slot, but ISS-199 recorded `first_token_timeout` on it in a live CI pass "
                "(2026-08-30) — so no content capability is claimed here at all. Not PRIMARY-eligible "
                "by data, not by taste."
            ),
            notes="ملاذُ تعافٍ في الذيل. يُرقّى بعد قياسٍ حيٍّ لا بتحرير سطر.",
        ),
        ModelRecord(
            model_id="nvidia/nemotron-nano-9b-v2:free",
            capabilities=frozenset({Capability.ARABIC, Capability.FRENCH}),
            verified_on=date(2026, 7, 22),
            evidence="D-177 live: 62s to first token with zero content — capped by FIRST_TOKEN_TIMEOUT.",
            banned_reason="PRIMARY-banned: no verified clean content stream.",
            notes="ملاذٌ أخير محروس بمهلة أوّل محتوى.",
        ),
        ModelRecord(
            model_id="nvidia/nemotron-3-super-120b:free",
            capabilities=frozenset({Capability.CONTENT_STREAM}),
            verified_on=date(2026, 7, 20),
            evidence="ISS-107 live: English text leaked into `content` on Arabic prompts.",
            banned_reason="BANNED entirely: English-in-content leak (ISS-107).",
            notes="ليس في السلسلة إطلاقاً — الإدخال موجود كي يبقى الحظر مُصرَّحاً.",
        ),
    )
}


def record_for(model_id: str) -> ModelRecord:
    """إدخال نموذج. يرفع إن لم يكن مُسجَّلاً — لا افتراضَ صامتاً بالسلامة."""
    try:
        return MODEL_REGISTRY[model_id]
    except KeyError as exc:
        raise ModelRegistryError(
            f"{model_id!r} has no registry entry — declare its capabilities and live evidence first"
        ) from exc


def assert_chain_is_registered(chain: tuple[str, ...] = MODEL_CHAIN) -> None:
    """
    كلّ نموذجٍ في السلسلة مُسجَّل، ولا نموذج محظورٍ كلّياً فيها.

    الحظر الكلّي (`BANNED entirely`) يختلف عن حظر الصدارة: الأوّل يمنع أيّ دور، والثاني
    يسمح بالذيل تحت حراسة. الخلط بينهما هو ما يُعيد نموذجاً مسرِّباً إلى المسار.
    """
    for model_id in chain:
        record = record_for(model_id)
        if record.banned_reason.startswith("BANNED entirely"):
            raise ModelRegistryError(f"{model_id} is banned outright: {record.banned_reason}")


def assert_primary_is_eligible(model_id: str = PRIMARY_MODEL) -> None:
    """
    الصدارة مؤهَّلة. يرفع بسببٍ مُسمّى — «غير مؤهّل» بلا سببٍ لا يُعلِّم أحداً شيئاً.
    """
    record = record_for(model_id)
    if record.is_banned:
        raise ModelRegistryError(f"{model_id} cannot be PRIMARY: {record.banned_reason}")
    missing = sorted(capability.value for capability in REQUIRED_FOR_PRIMARY - record.capabilities)
    if missing:
        raise ModelRegistryError(f"{model_id} cannot be PRIMARY: unverified {', '.join(missing)}")
