"""بروتوكول البرهان القابل للحمل — VEP (Verifiable Evidence Protocol).

معرفة جديدة كلياً (الدفعة الثانية بعد CDKC): تحويل «تقييم اعتمادية الوكلاء» من
**سلعة ثقة** (credence good — لا يستطيع المشتري تقييم جودتها لا قبل الشراء ولا بعده
بتكلفة معقولة) إلى **سلعة فحص** (inspection good — يُتحقَّق منها بتكلفة تقترب من
الصفر)، عبر إيصالٍ حتميٍّ مقاومٍ للتلاعب يُعاد تشغيله داخل بيئة المشتري نفسه.

الجملة البحثية
--------------
العائق أمام تصدير برمجيات البنية التحتية للذكاء الاصطناعي من الجزائر ليس القدرة ولا
السعر، بل **كلفة تحقّق المشتري البعيد**. وإذا انخفضت كلفة التحقّق إلى ما دون عتبةٍ
معلنة، سقط شرط «الحضور الشخصي/التجربة الميدانية» الذي تذكره أدبيات التعهيد الخارجي
شرطاً لبناء الثقة الابتدائية — وهو شرطٌ مكلفٌ على بائعٍ من ولايةٍ قضائيةٍ بعيدة.

ما يبنيه هذا الملفّ
-------------------
1. `RunRecord` — سجلّ تشغيلٍ واحد: حتميٌّ، معرَّفٌ ببصمةٍ، يحمل بصمة النصّ لا النصّ.
2. سلسلة هاش (`build_chain`) — أيُّ حذفٍ أو تعديلٍ أو إعادة ترتيبٍ يُكسَر كشفُه.
3. جذر ميركل + برهان تضمين (`merkle_proof` / `verify_merkle_proof`) — إثبات أن تشغيلاً
   بعينه داخل المجموعة دون كشف المجموعة كلّها.
4. التزاماتٌ مملَّحة (`commit_value`) — إثبات «عدد الأصناف المكتشفة» دون كشف الأصناف
   نفسها: الحدّ الأدنى من الإفصاح (minimal disclosure) لعميلٍ يرفض تصدير بياناته.
5. `EvaluationReceipt` + `verify_receipt` — الإيصال، وتحقيقٌ يُسمّي **أيّ فحصٍ فشل**
   (لا بوليان صامت: الفشل يجب أن يكون منطوقاً).
6. `replay_digest` — بصمةٌ مستقلّة عن ترتيب التنفيذ: التنفيذ المتوازي لا يغيّر البرهان.

حدودٌ معلنة (لا تُقرأ إلا معها)
------------------------------
- هذا الملفّ **لا يثبت جودة التقييم**؛ يثبت أنّ التقييم المزعوم هو ذاته الذي جرى.
  البرهانُ على المطابقة لا البرهانُ على الصحّة — والتمييز مقصود (D-267 · L9).
- لا مفاتيحَ ولا توقيعاتٍ ولا شبكة: البصمات هنا **سجلّ حتمي** لا هوية قانونية. الربطُ
  بهويةٍ قانونية (Sigstore/in-toto/SLSA) موضعُ بحثٍ لاحق لا ادّعاءٌ في هذا الملفّ.
- لا LLM في المسار: كل بصمةٍ تُحسَب من بايتاتٍ قابلة لإعادة التشغيل.

المراجع
-------
- Darby & Karni (1973) — سلع الثقة (credence goods).
- Nelson (1970) — سلع الفحص والخبرة (search/experience goods).
- Sigstore / in-toto / SLSA — سجلّات الشفافية وإثباتات المنشأ (مرجعٌ مقارن، لا تبعية).
"""

from __future__ import annotations

import hashlib
import json
import random
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import Final

__all__ = [
    "GENESIS_CHAIN",
    "MIN_RUNS_FOR_RECEIPT",
    "VEP_VERSION",
    "Commitment",
    "EvaluationReceipt",
    "FailureClass",
    "MerkleStep",
    "ReceiptVerification",
    "RunOutcome",
    "RunRecord",
    "VepError",
    "build_chain",
    "build_receipt",
    "canonical_json",
    "commit_failure_classes",
    "commit_value",
    "deterministic_probe_stream",
    "digest_payload",
    "env_fingerprint",
    "merkle_proof",
    "merkle_root",
    "public_summary",
    "replay_digest",
    "sha256_hex",
    "verify_commitment",
    "verify_merkle_proof",
    "verify_receipt",
]

VEP_VERSION: Final = "1.0.0"

#: الحدّ الأدنى للتشغيلات: دون ثلاث تشغيلات لا معنى لـ«نمط» — والقاعدة هنا مطابقةٌ
#: لعقد التكرار في طبقة التحقّق (D-267): قياسٌ بلا تكرارٍ ليس قياساً.
MIN_RUNS_FOR_RECEIPT: Final = 3

#: بداية السلسلة — ثابتٌ معلن، لا قيمةٌ ضمنية تُقرأ خطأً.
GENESIS_CHAIN: Final = "0" * 64

_HEX_LEN: Final = 64


class VepError(ValueError):
    """يُرفَع عند خرقِ عقدٍ في بناء الإيصال — لا فشلَ صامت، ولا قيمةً افتراضية مضلّلة."""


class RunOutcome(StrEnum):
    """مآل التشغيل. `TIMEOUT` **ليس** نجاحاً (قانونٌ مستعارٌ من عقيدة القيمة D-210)."""

    SUCCESS = "success"
    FAILURE = "failure"
    TIMEOUT = "timeout"
    ERROR = "error"


class FailureClass(StrEnum):
    """تصنيفٌ مبدئي لأصناف الفشل — أطروحة تصميم (🟡) لا تصنيفاً متفقاً عليه في الأدبيات."""

    NONE = "none"
    TOOL_MISUSE = "tool_misuse"
    STATE_DRIFT = "state_drift"
    PREMATURE_STOP = "premature_stop"
    UNVERIFIED_RESULT = "unverified_result"
    CONSTRAINT_VIOLATION = "constraint_violation"
    COST_OVERRUN = "cost_overrun"


# --------------------------------------------------------------------------- #
# الحتمية: أيّ كائنٍ يُبصَم بالطريقة نفسها على أيّ آلة
# --------------------------------------------------------------------------- #
def canonical_json(payload: object) -> str:
    """تمثيلٌ نصّي وحيد لأيّ حمولة: مفاتيحُ مرتّبة، بلا فراغات، UTF-8 صريح.

    لماذا؟ لأن `json.dumps` الافتراضي يترك ترتيب المفاتيح لترتيب الإدراج، فيُنتج
    بصمتين مختلفتين لنفس البيانات — وهو بالضبط ما يجعل «إعادة التشغيل» بلا معنى.
    """
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def sha256_hex(text: str) -> str:
    """بصمةٌ نصّية قياسية: SHA-256 على بايتات UTF-8."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def digest_payload(payload: object) -> str:
    """بصمة أيّ كائنٍ قابلٍ للتسلسل عبر التمثيل الكنسي."""
    return sha256_hex(canonical_json(payload))


def env_fingerprint(manifest: Mapping[str, object]) -> str:
    """بصمة بيئة التنفيذ: الحتمية بلا بيئةٍ معلومة ليست حتميةً يُعتدّ بها.

    البيئة تُعلَن (إصدار المحرّك، إصدار Python، المنصّة، المتغيّرات المؤثّرة) وتُبصَم؛
    فإن اختلفت البيئة اختلفت البصمة — فيُعرف أنّ المقارنة غير عادلة بدل أن تُخفى.
    """
    if not manifest:
        raise VepError("بيان البيئة فارغ: بصمةٌ بلا بيئةٍ تُعلَن ادّعاءٌ بلا حدّ.")
    return digest_payload(dict(manifest))


def deterministic_probe_stream(seed: int, count: int, prefix: str = "probe") -> tuple[str, ...]:
    """تيارُ مجساتٍ حتمي: البذرة وحدها تحدّد المجسّات، فلا حاجة لنقلها كلّها.

    الأهمية التصديرية: حزمةُ التقييم تُشحن كبذرة + مُولّد، لا كملفّات بياناتٍ ضخمة
    يصعب تمريرها عبر حدودٍ قانونية — والمشتري يعيد توليد المجسّات ذاتها في مكانه.
    """
    if seed < 0:
        raise VepError("البذرة يجب أن تكون صفراً أو موجبة.")
    if count <= 0:
        raise VepError("عدد المجسات يجب أن يكون موجباً.")
    rng = random.Random(seed)
    return tuple(
        f"{prefix}-{seed}-{index:04d}-{rng.randrange(16**8):08x}" for index in range(count)
    )


# --------------------------------------------------------------------------- #
# سجلّ التشغيل
# --------------------------------------------------------------------------- #
@dataclass(frozen=True, slots=True)
class RunRecord:
    """تشغيلٌ واحد: ما يُبصَم، لا ما يُقال.

    النصّ الكامل للتفاعل **لا يدخل** الإيصال؛ تدخل بصمته وحدها (`transcript_digest`).
    بهذا يصير الإيصال قابلاً للنشر دون كشف بيانات العميل — وهو شرطٌ يسبق أيّ تفاوض.
    """

    task_id: str
    seed: int
    harness: str
    env_fingerprint: str
    outcome: RunOutcome
    failure_class: FailureClass
    attempts: int
    latency_ms: int
    cost_usd: float
    transcript_digest: str
    notes: str = ""

    def __post_init__(self) -> None:
        if not self.task_id.strip():
            raise VepError("معرّف المهمة فارغ: تشغيلٌ بلا مهمة لا يُبصَم.")
        if self.seed < 0:
            raise VepError("البذرة سالبة.")
        if not self.harness.strip():
            raise VepError("معرّف المحرّك فارغ: لا إعادة تشغيل بلا محرّكٍ مسمّى.")
        if len(self.env_fingerprint) != _HEX_LEN:
            raise VepError("بصمة البيئة غير صالحة: يجب أن تكون SHA-256 نصّاً سداسياً.")
        if len(self.transcript_digest) != _HEX_LEN:
            raise VepError("بصمة النصّ غير صالحة: يجب أن تكون SHA-256 نصّاً سداسياً.")
        if self.attempts < 1:
            raise VepError("عدد المحاولات يجب أن يكون ≥ 1.")
        if self.latency_ms < 0 or self.cost_usd < 0:
            raise VepError("الزمن والكلفة غير سالبين.")
        # التلازم: لا صنفَ بلا فشل، ولا فشلَ بلا صنف. خانةٌ فارغة تُقرأ نجاحاً (D-228).
        failed = self.outcome is not RunOutcome.SUCCESS
        classified = self.failure_class is not FailureClass.NONE
        if failed != classified:
            raise VepError(
                "تلازمٌ مكسور: الفشل يتطلّب صنفاً والنجاح يتطلّب `none` — "
                f"outcome={self.outcome!s} class={self.failure_class!s}"
            )

    def canonical(self) -> dict[str, object]:
        """التمثيل الكنسي: الحقول مرتّبة نصّياً عبر `canonical_json`."""
        return {
            "attempts": self.attempts,
            "cost_usd": round(float(self.cost_usd), 6),
            "env_fingerprint": self.env_fingerprint,
            "failure_class": str(self.failure_class),
            "harness": self.harness,
            "latency_ms": self.latency_ms,
            "outcome": str(self.outcome),
            "seed": self.seed,
            "task_id": self.task_id,
            "transcript_digest": self.transcript_digest,
        }

    def digest(self) -> str:
        """بصمة التشغيل: تُبنى من التمثيل الكنسي وحده بلا `notes` (الملاحظات لا تُبصَم)."""
        return digest_payload(self.canonical())

    @property
    def is_failure(self) -> bool:
        """الفشل يشمل المهلة والخطأ: `TIMEOUT` ليس نجاحاً."""
        return self.outcome is not RunOutcome.SUCCESS


# --------------------------------------------------------------------------- #
# سلسلة الهاش · ميركل · الالتزامات
# --------------------------------------------------------------------------- #
def _validate_digest(value: str, label: str) -> str:
    if len(value) != _HEX_LEN or any(char not in "0123456789abcdef" for char in value):
        raise VepError(f"{label} غير صالح: يجب أن يكون SHA-256 نصّاً سداسياً صغيراً.")
    return value


def build_chain(run_digests: Sequence[str]) -> tuple[str, ...]:
    """سلسلةٌ متّصلة: `c_i = H(c_{i-1} + d_i)` — حذفُ تشغيلٍ أو تبديلُ ترتيبٍ يكسرها.

    لماذا سلسلةٌ لا قائمة؟ لأنّ قائمة البصمات تسمح بحذفٍ صامت: من يحذف تشغيلاً سيّئاً
    يُبقي الجذر سليماً. السلسلة تجعل كلّ بصمةٍ مرتهنةً بمن قبلها.
    """
    chain: list[str] = []
    previous = GENESIS_CHAIN
    for digest in run_digests:
        _validate_digest(digest, "بصمة تشغيل")
        previous = sha256_hex(previous + digest)
        chain.append(previous)
    return tuple(chain)


def merkle_root(leaves: Sequence[str]) -> str:
    """جذر ميركل: إثبات تضمينٍ لاحقاً دون كشف المجموعة كلّها.

    العدد الفردي يُعالَج بتكرار آخر ورقة (المعتاد في الشفافية) ويُقال صراحةً لا ضمنياً.
    """
    if not leaves:
        raise VepError("جذر ميركل بلا أوراق: مجموعةٌ فارغة ليست برهاناً.")
    level = [_validate_digest(leaf, "ورقة ميركل") for leaf in leaves]
    while len(level) > 1:
        if len(level) % 2 == 1:
            level.append(level[-1])  # تكرارٌ صريح لآخر ورقة عند الفردي
        level = [sha256_hex(level[i] + level[i + 1]) for i in range(0, len(level), 2)]
    return level[0]


@dataclass(frozen=True, slots=True)
class MerkleStep:
    """خطوة برهان: بصمة الأخت وجهتها."""

    sibling: str
    side: str  # "left" إن كانت الأخت يساراً، و"right" إن كانت يميناً


def merkle_proof(leaves: Sequence[str], index: int) -> tuple[MerkleStep, ...]:
    """برهان تضمين لورقةٍ بعينها — أقصرُ طريقٍ من الورقة إلى الجذر."""
    if not leaves:
        raise VepError("برهانٌ بلا أوراق.")
    if not 0 <= index < len(leaves):
        raise VepError(f"فهرس الورقة خارج النطاق: {index}")
    level = [_validate_digest(leaf, "ورقة ميركل") for leaf in leaves]
    proof: list[MerkleStep] = []
    position = index
    while len(level) > 1:
        if len(level) % 2 == 1:
            level.append(level[-1])
        if position % 2 == 0:
            proof.append(MerkleStep(sibling=level[position + 1], side="right"))
        else:
            proof.append(MerkleStep(sibling=level[position - 1], side="left"))
        level = [sha256_hex(level[i] + level[i + 1]) for i in range(0, len(level), 2)]
        position //= 2
    return tuple(proof)


def verify_merkle_proof(leaf: str, index: int, proof: Sequence[MerkleStep], root: str) -> bool:
    """تحقّقٌ من برهان تضمين: يُعاد حساب الجذر من الورقة والبرهان ويُقارَن."""
    _validate_digest(leaf, "ورقة ميركل")
    _validate_digest(root, "جذر ميركل")
    computed = _validate_digest(leaf, "ورقة ميركل")
    position = index
    for step in proof:
        _validate_digest(step.sibling, "بصمة الأخت")
        computed = (
            sha256_hex(step.sibling + computed)
            if step.side == "left"
            else sha256_hex(computed + step.sibling)
        )
        position //= 2
    return computed == root


def commit_value(value: str, salt: str) -> str:
    """التزامٌ مملَّح: `H(salt | value)` — يُثبت أنّ القيمة كانت معلومةً قبل الكشف.

    الاستعمال: «وجدنا ثلاثة أصناف فشلٍ متميّزة» تُثبَت بالالتزامات، ثم تُكشَف الأصناف
    لاحقاً بملحها. المشتري يتحقّق أنّنا لم نخترع الصنف بعد أن سمع اعتراضه.
    """
    if not value.strip():
        raise VepError("الالتزام على قيمةٍ فارغة بلا معنى.")
    if not salt.strip():
        raise VepError("الالتزام بلا ملحٍ قابلٌ للتخمين بالقوة الغاشمة — والملح إلزامي.")
    return sha256_hex(f"{salt}|{value}")


def verify_commitment(value: str, salt: str, commitment: str) -> bool:
    """كشفٌ صادق: القيمة + الملح يطابقان الالتزام السابق."""
    return commit_value(value, salt) == commitment


@dataclass(frozen=True, slots=True)
class Commitment:
    """التزامٌ بقيمةٍ غير مفصَح عنها، مرتّبٌ بفهرسٍ ثابت."""

    index: int
    digest: str


def commit_failure_classes(runs: Sequence[RunRecord], salt: str) -> tuple[Commitment, ...]:
    """التزاماتٌ بالأصناف المتميّزة المكتشفة، مرتّبةٌ أبجدياً: عددٌ بلا إفصاح.

    لماذا؟ لأنّ العميل يريد أن يعرف **كم** صنفاً اكتشفنا قبل أن يسمح لنا ببياناته،
    ونحن لا نستطيع كشف الأصناف قبل أن نملك حقّ نشرها. الالتزام يحلّ التبادل المستحيل.
    """
    if not salt.strip():
        raise VepError("الالتزامات بلا ملحٍ: الملح إلزامي.")
    distinct = sorted({str(run.failure_class) for run in runs if run.is_failure})
    return tuple(
        Commitment(index=position, digest=commit_value(value=label, salt=salt))
        for position, label in enumerate(distinct)
    )


def replay_digest(run_digests: Sequence[str]) -> str:
    """بصمة إعادة التشغيل: مستقلّة عن ترتيب التنفيذ (مجموعةٌ لا متتالية).

    التنفيذ المتوازي يغيّر الترتيب ولا يغيّر المجموعة؛ فلو بُني البرهان على الترتيب
    لصار كلّ تشغيلٍ متوازٍ «دليلاً مختلفاً» — وهذا بالضبط ما يجعل إعادة التشغيل بلا معنى
    عند العميل الذي يملك عُمّالاً كُثراً.
    """
    if not run_digests:
        raise VepError("بصمة إعادة تشغيل بلا تشغيلات.")
    ordered = sorted(_validate_digest(digest, "بصمة تشغيل") for digest in run_digests)
    return sha256_hex("|".join(ordered))


# --------------------------------------------------------------------------- #
# الإيصال
# --------------------------------------------------------------------------- #
@dataclass(frozen=True, slots=True)
class EvaluationReceipt:
    """إيصال التقييم القابل للتحقّق: ما يُشحن إلى المشتري البعيد.

    لا يحمل نصّاً ولا بيانات عميل: يحمل بصماتٍ والتزاماتٍ وعدداً. وكلّ ما فيه قابلٌ
    لإعادة الحساب محلياً عند المشتري — وهذا هو جوهر تحويل سلعة الثقة إلى سلعة فحص.
    """

    vep_version: str
    receipt_id: str
    harness: str
    env_fingerprint: str
    policy_digest: str
    task_set_root: str
    run_count: int
    outcome_counts: tuple[tuple[str, int], ...]
    chain_head: str
    merkle_root: str
    replay_digest: str
    commitments: tuple[Commitment, ...]
    created_utc: str

    def canonical(self) -> dict[str, object]:
        """التمثيل الكنسي — البصمة تُحسَب عليه، لا على تمثيل الذاكرة."""
        return {
            "chain_head": self.chain_head,
            "commitments": [[item.index, item.digest] for item in self.commitments],
            "created_utc": self.created_utc,
            "env_fingerprint": self.env_fingerprint,
            "harness": self.harness,
            "merkle_root": self.merkle_root,
            "outcome_counts": [[name, count] for name, count in self.outcome_counts],
            "policy_digest": self.policy_digest,
            "receipt_id": self.receipt_id,
            "replay_digest": self.replay_digest,
            "run_count": self.run_count,
            "task_set_root": self.task_set_root,
            "vep_version": self.vep_version,
        }

    def receipt_digest(self) -> str:
        """بصمة الإيصال: ما يُوقَّع لاحقاً بهويةٍ قانونية (خارج نطاق هذا الملفّ)."""
        return digest_payload(self.canonical())


def build_receipt(
    runs: Sequence[RunRecord],
    *,
    harness: str,
    env_fingerprint: str,
    policy_digest: str,
    task_set_root: str,
    created_utc: str,
    salt: str,
    receipt_id: str | None = None,
    min_runs: int = MIN_RUNS_FOR_RECEIPT,
) -> EvaluationReceipt:
    """يبني إيصالاً من تشغيلات: غيرُ الناضج يُرفَض خطأً، لا يُشحن بصمت.

    `min_runs` واجهةُ عقد التكرار: دون ثلاث تشغيلات لا نمطَ ولا برهان.
    """
    if len(runs) < min_runs:
        raise VepError(
            f"التشغيلات {len(runs)} أقلّ من حدّ النضج {min_runs}: "
            "إيصالٌ من تشغيلٍ أو اثنين برهانٌ على شيءٍ واحد لا على نمط."
        )
    if not created_utc.strip():
        raise VepError("الإيصال بلا تاريخ إنشاء: برهانٌ بلا زمنٍ لا يُؤرَّخ به ادّعاء.")
    fingerprints = {run.env_fingerprint for run in runs}
    if fingerprints != {env_fingerprint}:
        raise VepError("بيئاتٌ مختلطة في إيصالٍ واحد: المقارنة بين بيئتين ليست قياساً واحداً.")
    harnesses = {run.harness for run in runs}
    if harnesses != {harness}:
        raise VepError("محرّكاتٌ مختلطة في إيصالٍ واحد: الإيصال يُعلن محرّكاً واحداً.")

    digests = [run.digest() for run in runs]
    chain = build_chain(digests)
    counts: dict[str, int] = {}
    for run in runs:
        counts[str(run.outcome)] = counts.get(str(run.outcome), 0) + 1
    ordered_counts = tuple(sorted(counts.items()))
    identifier = (
        receipt_id
        or digest_payload(
            {"env": env_fingerprint, "harness": harness, "replay": replay_digest(digests)}
        )[:32]
    )

    return EvaluationReceipt(
        vep_version=VEP_VERSION,
        receipt_id=identifier,
        harness=harness,
        env_fingerprint=env_fingerprint,
        policy_digest=policy_digest,
        task_set_root=task_set_root,
        run_count=len(runs),
        outcome_counts=ordered_counts,
        chain_head=chain[-1],
        merkle_root=merkle_root(digests),
        replay_digest=replay_digest(digests),
        commitments=commit_failure_classes(runs, salt=salt),
        created_utc=created_utc,
    )


@dataclass(frozen=True, slots=True)
class ReceiptVerification:
    """نتيجة التحقّق: بوليان + **اسم الفحص الذي فشل** — الفشل يجب أن يكون منطوقاً."""

    ok: bool
    checks: tuple[tuple[str, bool], ...]
    reasons: tuple[str, ...]


def verify_receipt(receipt: EvaluationReceipt, runs: Sequence[RunRecord]) -> ReceiptVerification:
    """يحقّق أنّ الإيصال يطابق التشغيلات المدّعاة — مطابقةٌ لا صحّة.

    تسعة فحوص، كلٌّ منها يُسمّى في النتيجة: التحقّق الذي يقول «خطأ» دون أن يقول أين،
    يمنح المشتري سبباً للرفض دون سببٍ للتصحيح.
    """
    checks: list[tuple[str, bool]] = []
    reasons: list[str] = []

    def record(name: str, passed: bool, reason: str = "") -> None:
        checks.append((name, passed))
        if not passed:
            reasons.append(f"{name}: {reason}")

    digests = [run.digest() for run in runs]
    record(
        "run_count",
        len(runs) == receipt.run_count,
        f"الإيصال يعلن {receipt.run_count} والمعطى {len(runs)}.",
    )
    record(
        "min_runs",
        len(runs) >= MIN_RUNS_FOR_RECEIPT,
        f"التشغيلات {len(runs)} دون حدّ النضج {MIN_RUNS_FOR_RECEIPT}.",
    )
    record(
        "env_uniform",
        len({run.env_fingerprint for run in runs}) <= 1
        and (not runs or runs[0].env_fingerprint == receipt.env_fingerprint),
        "بصمات البيئة مختلطة أو لا تطابق الإيصال.",
    )
    record(
        "harness_uniform",
        len({run.harness for run in runs}) <= 1
        and (not runs or runs[0].harness == receipt.harness),
        "معرّفات المحرّك مختلطة أو لا تطابق الإيصال.",
    )
    chain = build_chain(digests)
    record(
        "chain_head",
        bool(chain) and chain[-1] == receipt.chain_head,
        "رأس السلسلة المعاد حسابه لا يطابق الإيصال — حذفٌ أو تبديلُ ترتيب.",
    )
    record(
        "merkle_root",
        bool(digests) and merkle_root(digests) == receipt.merkle_root,
        "جذر ميركل المعاد حسابه لا يطابق الإيصال.",
    )
    record(
        "replay_digest",
        bool(digests) and replay_digest(digests) == receipt.replay_digest,
        "بصمة إعادة التشغيل لا تطابق: المجموعة مختلفة.",
    )
    computed_counts: dict[str, int] = {}
    for run in runs:
        computed_counts[str(run.outcome)] = computed_counts.get(str(run.outcome), 0) + 1
    record(
        "outcome_counts",
        tuple(sorted(computed_counts.items())) == receipt.outcome_counts,
        f"عدّاد المآلات {tuple(sorted(computed_counts.items()))} ≠ {receipt.outcome_counts}.",
    )
    record(
        "commitment_arity",
        len(receipt.commitments) == len({str(r.failure_class) for r in runs if r.is_failure}),
        "عدد الالتزامات لا يطابق عدد أصناف الفشل المتميّزة.",
    )

    return ReceiptVerification(
        ok=all(passed for _, passed in checks),
        checks=tuple(checks),
        reasons=tuple(reasons),
    )


def public_summary(receipt: EvaluationReceipt) -> dict[str, object]:
    """ملخّصٌ قابل للنشر: ما يمكن قوله لعميلٍ قبل توقيع اتفاق سرّية.

    يحمل العدد والجذور والالتزامات — ولا يحمل صنفاً ولا نصّاً ولا بصمة نصّ.
    """
    return {
        "commitment_count": len(receipt.commitments),
        "created_utc": receipt.created_utc,
        "env_fingerprint": receipt.env_fingerprint,
        "harness": receipt.harness,
        "merkle_root": receipt.merkle_root,
        "outcome_counts": dict(receipt.outcome_counts),
        "receipt_digest": receipt.receipt_digest(),
        "replay_digest": receipt.replay_digest,
        "run_count": receipt.run_count,
        "vep_version": receipt.vep_version,
    }
