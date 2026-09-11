"""حزمة البحث المستقل — معرفة جديدة قابلة للتصدير بالعملة الصعبة.

تولّد هذه الحزمة معرفتين جديدتين كليّاً، كلٌّ منهما قابلة للتدقيق والتوريّد:

1. **CDKC** (`durable_knowledge.py`, `exportable_eval.py`) — معامل المعرفة الدائمة
   القابل للتصدير، ويجمع:
   - BKT للإتقان الدائم
   - FSRS لقابلية الاسترجاع
   - التحقق الرمزي لصحة المحتوى
   - فجوة الوهم للمعايرة
   - التبديل اللغوي العربي/الفرنسي/الدارجة

2. **VEP** (`verifiable_evidence.py`, `portable_trust.py`) — بروتوكول البرهان
   القابل للحمل، ويحوّل «تقييم اعتمادية الوكلاء» من **سلعة ثقة** إلى **سلعة فحص**
   عبر إيصالٍ حتميٍّ قابل لإعادة التشغيل داخل بيئة المشتري نفسه، مع قياسِ كلفة
   التحقّق وقرارِ قبولٍ منطوق وأجلِ ترحيلٍ بوصفه قيدَ تصميمِ عقد.

القانون: stdlib فقط، لا استيراد من app/ ولا microservices/ — قابلة للتوريّد والتدقيق،
وتُشحن إلى عميلٍ لا يملك تبعياتنا.
"""

from __future__ import annotations

from .durable_knowledge import (
    CDKC_VERSION,
    MIN_OBS_CDKC,
    CdkcError,
    CdkcInput,
    CdkcResult,
    LanguageSwitchCost,
    SymbolicWeight,
    compute_cdkc,
    compute_language_switch_cost,
    compute_symbolic_weight,
)
from .exportable_eval import (
    EvalTask,
    EvalTaskKind,
    ExportableEvalBundle,
    build_eval_bundle,
)
from .portable_trust import (
    DEFAULT_ACCEPT_THETA,
    DEFAULT_REPATRIATION_DEADLINE_DAYS,
    MIN_N_FOR_ESTIMATE,
    AcceptDecision,
    BreachVerdict,
    EscapeDelta,
    Interval,
    PrvResult,
    RepatriationRisk,
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
from .verifiable_evidence import (
    GENESIS_CHAIN,
    MIN_RUNS_FOR_RECEIPT,
    VEP_VERSION,
    Commitment,
    EvaluationReceipt,
    FailureClass,
    MerkleStep,
    ReceiptVerification,
    RunOutcome,
    RunRecord,
    VepError,
    build_chain,
    build_receipt,
    canonical_json,
    commit_failure_classes,
    commit_value,
    deterministic_probe_stream,
    digest_payload,
    env_fingerprint,
    merkle_proof,
    merkle_root,
    public_summary,
    replay_digest,
    sha256_hex,
    verify_commitment,
    verify_merkle_proof,
    verify_receipt,
)

__all__ = [
    # CDKC — المعرفة الدائمة القابلة للتصدير
    "CDKC_VERSION",
    "MIN_OBS_CDKC",
    "CdkcError",
    "CdkcInput",
    "CdkcResult",
    "EvalTask",
    "EvalTaskKind",
    "ExportableEvalBundle",
    "LanguageSwitchCost",
    "SymbolicWeight",
    "build_eval_bundle",
    "compute_cdkc",
    "compute_language_switch_cost",
    "compute_symbolic_weight",
    # VEP — البرهان القابل للحمل: الإيصال
    "VEP_VERSION",
    "MIN_RUNS_FOR_RECEIPT",
    "GENESIS_CHAIN",
    "VepError",
    "FailureClass",
    "RunOutcome",
    "RunRecord",
    "Commitment",
    "MerkleStep",
    "EvaluationReceipt",
    "ReceiptVerification",
    "build_chain",
    "build_receipt",
    "canonical_json",
    "commit_value",
    "commit_failure_classes",
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
    # VEP — البرهان القابل للحمل: الاقتصاد والقرار
    "MIN_N_FOR_ESTIMATE",
    "WILSON_Z_95",
    "DEFAULT_ACCEPT_THETA",
    "DEFAULT_REPATRIATION_DEADLINE_DAYS",
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
    "WILSON_Z_95",
]
