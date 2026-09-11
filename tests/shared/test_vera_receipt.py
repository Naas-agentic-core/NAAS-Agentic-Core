"""اختبارات VEP — إيصال التقييم القابل للتحقّق.

تثبت هذه الاختبارات أنّ البرهان:
1. حتميٌّ — نفسُ المدخلات تعطي نفس البصمة على أيّ ترتيب إدراج
2. مقاومٌ للتلاعب — حذفُ تشغيلٍ أو تبديلُ ترتيبٍ أو تعديلُ حقلٍ يكسر التحقّق
3. قابل لإعادة التشغيل — البصمة لا تتغيّر بالتنفيذ المتوازي
4. مقلِّلُ الإفصاح — يثبت عدد الأصناف دون كشفها
5. منطوقٌ عند الفشل — التحقّق يسمّي الفحص الذي سقط، لا «خطأ» غامضاً
6. ناضجٌ أو معدوم — دون ثلاث تشغيلات لا إيصال (لا برهانَ على نمطٍ من اثنين)
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from shared.research.verifiable_evidence import (
    GENESIS_CHAIN,
    MIN_RUNS_FOR_RECEIPT,
    VEP_VERSION,
    Commitment,
    EvaluationReceipt,
    FailureClass,
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
    verify_commitment,
    verify_merkle_proof,
    verify_receipt,
)

ENV = env_fingerprint({"python": "3.12", "harness": "vera-probe", "platform": "linux"})
TASK_ROOT = "a" * 64
POLICY = "b" * 64


def make_run(
    task_id: str = "task-001",
    *,
    seed: int = 7,
    outcome: RunOutcome = RunOutcome.SUCCESS,
    failure_class: FailureClass = FailureClass.NONE,
    latency_ms: int = 1200,
    cost_usd: float = 0.02,
    notes: str = "",
) -> RunRecord:
    return RunRecord(
        task_id=task_id,
        seed=seed,
        harness="vera-probe@1.0.0",
        env_fingerprint=ENV,
        outcome=outcome,
        failure_class=failure_class,
        attempts=1,
        latency_ms=latency_ms,
        cost_usd=cost_usd,
        transcript_digest=digest_payload({"task": task_id, "seed": seed}),
        notes=notes,
    )


def sample_runs(count: int = 6) -> list[RunRecord]:
    """عيّنة تشغيلات: ثلاثة أنماط فشل متميّزة حيثما اتّسع المجال.

    أهمّ ما يُباع ليس عدد التشغيلات بل **التنوّع المكتشف**؛ ومع ذلك يجب أن تعمل
    الدالة مع الحدّ الأدنى (٣ تشغيلات) لأنّ الإيصال يُبنى عنده أيضاً.
    """
    runs = [make_run(f"task-{index:03d}") for index in range(count)]
    patterns = (
        (1, RunOutcome.FAILURE, FailureClass.TOOL_MISUSE),
        (3, RunOutcome.TIMEOUT, FailureClass.STATE_DRIFT),
        (5, RunOutcome.ERROR, FailureClass.CONSTRAINT_VIOLATION),
    )
    for position, outcome, failure_class in patterns:
        if position < count:
            runs[position] = make_run(
                f"task-{position:03d}", outcome=outcome, failure_class=failure_class
            )
    return runs


def build(runs: list[RunRecord], **kwargs) -> EvaluationReceipt:
    options = {
        "harness": "vera-probe@1.0.0",
        "env_fingerprint": ENV,
        "policy_digest": POLICY,
        "task_set_root": TASK_ROOT,
        "created_utc": "2026-09-11T00:00:00Z",
        "salt": "salt-not-a-secret-in-this-test",
    }
    options.update(kwargs)
    return build_receipt(runs, **options)  # type: ignore[arg-type]


# --------------------------------------------------------------------------- #
# 1) الحتمية
# --------------------------------------------------------------------------- #
def test_canonical_json_is_independent_of_insertion_order() -> None:
    left = canonical_json({"b": 1, "a": {"d": 2, "c": 3}})
    right = canonical_json({"a": {"c": 3, "d": 2}, "b": 1})
    assert left == right
    assert " " not in left, "التمثيل الكنسي بلا فراغات: أيّ فراغٍ بصمةٌ مختلفة"


def test_run_digest_is_stable_and_sensitive() -> None:
    run = make_run("task-042")
    assert run.digest() == make_run("task-042").digest()
    assert run.digest() != make_run("task-043").digest()


def test_notes_do_not_change_the_digest() -> None:
    """الملاحظات تفسيرٌ بشري: لا يجوز أن تُبدّل برهاناً."""
    assert make_run("task-001", notes="").digest() == make_run("task-001", notes="ملاحظة").digest()


def test_probe_stream_is_a_pure_function_of_the_seed() -> None:
    first = deterministic_probe_stream(seed=2026, count=5)
    again = deterministic_probe_stream(seed=2026, count=5)
    other = deterministic_probe_stream(seed=2027, count=5)
    assert first == again
    assert first != other
    assert len(first) == 5


def test_probe_stream_rejects_nonsense() -> None:
    with pytest.raises(VepError):
        deterministic_probe_stream(seed=-1, count=5)
    with pytest.raises(VepError):
        deterministic_probe_stream(seed=1, count=0)


# --------------------------------------------------------------------------- #
# 2) سلامة السجلّ
# --------------------------------------------------------------------------- #
def test_failure_requires_a_class_and_success_forbids_it() -> None:
    with pytest.raises(VepError):
        make_run("t", outcome=RunOutcome.FAILURE, failure_class=FailureClass.NONE)
    with pytest.raises(VepError):
        make_run("t", outcome=RunOutcome.SUCCESS, failure_class=FailureClass.TOOL_MISUSE)


def test_timeout_is_never_a_success() -> None:
    timeout_run = make_run("t", outcome=RunOutcome.TIMEOUT, failure_class=FailureClass.STATE_DRIFT)
    assert timeout_run.is_failure
    assert not make_run("t").is_failure


def test_invalid_transcript_digest_is_rejected() -> None:
    with pytest.raises(VepError):
        RunRecord(
            task_id="t",
            seed=0,
            harness="h",
            env_fingerprint=ENV,
            outcome=RunOutcome.SUCCESS,
            failure_class=FailureClass.NONE,
            attempts=1,
            latency_ms=1,
            cost_usd=0.0,
            transcript_digest="short",
        )


# --------------------------------------------------------------------------- #
# 3) مقاومة التلاعب
# --------------------------------------------------------------------------- #
def test_chain_detects_deletion() -> None:
    digests = [run.digest() for run in sample_runs()]
    honest = build_chain(digests)
    tampered = build_chain(digests[:-1])
    assert honest[-1] != tampered[-1]
    assert build_chain([]) == ()


def test_chain_detects_reordering() -> None:
    digests = [run.digest() for run in sample_runs()]
    assert build_chain(digests)[-1] != build_chain(list(reversed(digests)))[-1]


def test_chain_starts_from_the_declared_genesis() -> None:
    digests = [run.digest() for run in sample_runs(3)]
    assert build_chain(digests)[0] != GENESIS_CHAIN
    assert len(build_chain(digests)) == 3


def test_replay_digest_is_order_independent() -> None:
    digests = [run.digest() for run in sample_runs()]
    assert replay_digest(digests) == replay_digest(list(reversed(digests)))


def test_merkle_root_and_inclusion_proof() -> None:
    digests = [run.digest() for run in sample_runs()]
    root = merkle_root(digests)
    proof = merkle_proof(digests, index=2)
    assert verify_merkle_proof(digests[2], 2, proof, root)
    assert not verify_merkle_proof(digests[3], 2, proof, root), "ورقةٌ مزيّفة يجب أن تُرفض"


def test_merkle_root_changes_with_any_leaf() -> None:
    digests = [run.digest() for run in sample_runs()]
    tampered = list(digests)
    tampered[0] = digest_payload({"evil": True})
    assert merkle_root(digests) != merkle_root(tampered)


def test_merkle_proof_rejects_out_of_range_index() -> None:
    digests = [run.digest() for run in sample_runs(3)]
    with pytest.raises(VepError):
        merkle_proof(digests, index=9)


# --------------------------------------------------------------------------- #
# 4) الحدّ الأدنى من الإفصاح
# --------------------------------------------------------------------------- #
def test_commitment_reveals_only_when_the_salt_matches() -> None:
    commitment = commit_value("STATE_DRIFT", salt="s3cr3t")
    assert verify_commitment("STATE_DRIFT", "s3cr3t", commitment)
    assert not verify_commitment("STATE_DRIFT", "other", commitment)
    assert not verify_commitment("TOOL_MISUSE", "s3cr3t", commitment)


def test_commitment_rejects_empty_salt_and_value() -> None:
    with pytest.raises(VepError):
        commit_value("value", salt="")
    with pytest.raises(VepError):
        commit_value("", salt="salt")


def test_commitment_arity_equals_distinct_failure_classes() -> None:
    runs = sample_runs()
    distinct = {str(run.failure_class) for run in runs if run.is_failure}
    commitments = commit_failure_classes(runs, salt="s")
    assert len(commitments) == len(distinct) == 3
    assert [item.index for item in commitments] == [0, 1, 2]


def test_public_summary_leaks_no_class_and_no_transcript() -> None:
    receipt = build(sample_runs())
    summary = public_summary(receipt)
    blob = repr(summary)
    assert "transcript" not in blob
    for label in ("tool_misuse", "state_drift", "constraint_violation"):
        assert label not in blob, f"الملخّص العام كشف صنفاً: {label}"
    assert summary["commitment_count"] == 3
    assert summary["run_count"] == 6
    assert summary["vep_version"] == VEP_VERSION


# --------------------------------------------------------------------------- #
# 5) بناء الإيصال والتحقّق منه
# --------------------------------------------------------------------------- #
def test_receipt_requires_mature_evidence() -> None:
    with pytest.raises(VepError):
        build(sample_runs()[:2])
    assert MIN_RUNS_FOR_RECEIPT == 3


def test_receipt_rejects_mixed_environments() -> None:
    runs = sample_runs(3)
    other_env = env_fingerprint({"python": "3.13", "harness": "vera-probe", "platform": "linux"})
    runs[2] = RunRecord(
        task_id="task-002",
        seed=2,
        harness="vera-probe@1.0.0",
        env_fingerprint=other_env,
        outcome=RunOutcome.SUCCESS,
        failure_class=FailureClass.NONE,
        attempts=1,
        latency_ms=10,
        cost_usd=0.0,
        transcript_digest=digest_payload({"task": "task-002"}),
    )
    with pytest.raises(VepError):
        build(runs)


def test_receipt_rejects_mixed_harnesses() -> None:
    runs = sample_runs(3)
    with pytest.raises(VepError):
        build(runs, harness="other@2.0.0")


def test_receipt_requires_a_timestamp() -> None:
    with pytest.raises(VepError):
        build(sample_runs(), created_utc="  ")


def test_verify_receipt_passes_on_honest_evidence() -> None:
    runs = sample_runs()
    verification = verify_receipt(build(runs), runs)
    assert verification.ok
    assert verification.reasons == ()
    assert len(verification.checks) == 9


def test_verify_receipt_names_the_failed_check_when_a_run_is_dropped() -> None:
    """الفشل يجب أن يكون منطوقاً: «خطأ» وحده يمنح سبباً للرفض لا سبباً للتصحيح."""
    runs = sample_runs()
    receipt = build(runs)
    verification = verify_receipt(receipt, runs[:-1])
    assert not verification.ok
    assert any(name == "chain_head" and not passed for name, passed in verification.checks)
    assert any("chain_head" in reason for reason in verification.reasons)


def test_verify_receipt_detects_a_mutated_run() -> None:
    runs = sample_runs()
    receipt = build(runs)
    runs[0] = make_run("task-000", latency_ms=999_999)
    verification = verify_receipt(receipt, runs)
    assert not verification.ok
    assert not dict(verification.checks)["merkle_root"]


def test_verify_receipt_rejects_immature_evidence() -> None:
    runs = sample_runs()[:2]
    receipt = build(sample_runs())
    verification = verify_receipt(receipt, runs)
    assert not verification.ok
    assert not dict(verification.checks)["min_runs"]


def test_receipt_digest_is_deterministic() -> None:
    runs = sample_runs()
    assert build(runs).receipt_digest() == build(runs).receipt_digest()


def test_receipt_is_exportable_as_json() -> None:
    """الإيصال يُشحن: لذا يجب أن يكون كائناً قابلاً للتسلسل بصورةٍ كنسيّة."""
    receipt = build(sample_runs())
    payload = receipt.canonical()
    assert digest_payload(payload) == receipt.receipt_digest()
    assert isinstance(receipt.commitments[0], Commitment)


# --------------------------------------------------------------------------- #
# 6) حدود الحزمة: stdlib فقط، ولا استيراد من التطبيق
# --------------------------------------------------------------------------- #
def test_module_imports_nothing_but_the_standard_library() -> None:
    """البرهان يُشحن إلى عميلٍ لا يملك تبعياتنا: الحزمة يجب أن تكون نقيّة."""
    module_path = (
        Path(__file__).resolve().parents[2] / "shared" / "research" / "verifiable_evidence.py"
    )
    tree = ast.parse(module_path.read_text(encoding="utf-8"))
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module.split(".")[0])
    forbidden = imported - {
        "hashlib",
        "json",
        "random",
        "collections",
        "dataclasses",
        "enum",
        "typing",
        "__future__",
    }
    assert not forbidden, f"استيرادٌ خارج المسموح: {sorted(forbidden)}"
