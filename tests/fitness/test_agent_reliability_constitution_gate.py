"""اختبارات سلبية لدستور اعتمادية الوكلاء والعملة الصعبة (D-290).

النمط مطابقٌ لبقية اختبارات `tests/fitness/`: البوّابة تُثبِت أنها **تحجب** لا أنها
تعمل (D-270 L4 · D-208). كل اختبارٍ يبني جذراً مؤقتاً بملفّاتٍ ناقصةٍ أو مخالفةٍ
ويستدعي الدوال الداخلية — والجوهر: العبارات غير القابلة للتفنيد بلا وسم منعٍ/نفيٍّ
يجب أن تُسقط البوّابة، وأن الحالات المغلقة للفرضيات تُحترم.
"""

from __future__ import annotations

import json
from pathlib import Path

from scripts.fitness import check_agent_reliability_constitution as gate


def _mini_repo(tmp_path: Path) -> dict[str, Path]:
    """جذر مؤقت يحمل نسخاً صغيرة من الملفات المُعرَّفة، مع قائمة انتهاكات فارغة."""
    (tmp_path / ".memory").mkdir()
    (tmp_path / "docs" / "commercial").mkdir(parents=True)
    (tmp_path / "docs" / "governance").mkdir(parents=True)
    (tmp_path / ".github" / "workflows").mkdir(parents=True)
    law = tmp_path / ".memory" / "agent_reliability_hard_currency_constitution.md"
    status = tmp_path / ".memory" / "agent_reliability_hard_currency_truth.md"
    strategy = tmp_path / "docs" / "commercial" / "NAAS_AGENT_RELIABILITY_STRATEGIC_RESEARCH.md"
    registry = tmp_path / "docs" / "governance" / "CONSTITUTION_REGISTRY.json"
    claude = tmp_path / "CLAUDE.md"
    ci = tmp_path / ".github" / "workflows" / "ci.yml"
    catalog = tmp_path / "docs" / "commercial" / "OFFER_CATALOG.json"
    for p in (law, status, strategy, claude, ci, catalog):
        p.write_text("", encoding="utf-8")
    registry.write_text(
        json.dumps(
            {
                "constitutions": [
                    {
                        "section": "0.29",
                        "id": "D-290",
                        "law_docs": [".memory/agent_reliability_hard_currency_constitution.md"],
                        "status_docs": [".memory/agent_reliability_hard_currency_truth.md"],
                        "enforcers": ["check_agent_reliability_constitution.py"],
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    return {
        "law": law,
        "status": status,
        "strategy": strategy,
        "registry": registry,
        "claude": claude,
        "ci": ci,
        "catalog": catalog,
    }


def test_forbidden_claim_without_marker_rejected(tmp_path: Path, monkeypatch) -> None:
    """«نضمن» في أيّ وثيقةٍ بلا وسم منعٍ/نفيٍّ يجب أن يُسقط البوّابة (L3)."""
    paths = _mini_repo(tmp_path)
    monkeypatch.setattr(gate, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(gate, "LAW_DOC", paths["law"])
    monkeypatch.setattr(gate, "TRUTH_DOC", paths["status"])
    monkeypatch.setattr(gate, "STRATEGY_DOC", paths["strategy"])
    paths["strategy"].write_text("المنتج يضمن نجاح الوكيل في كل الحالات.\n", encoding="utf-8")
    gate._FAILURES.clear()
    gate.check_claim_discipline()
    assert any("عبارةٌ غير قابلةٍ للتفنيد" in f for f in gate._FAILURES)


def test_forbidden_claim_with_negation_allowed(tmp_path: Path, monkeypatch) -> None:
    """السطر الذي يعلن المنع/النفي بذاته (❌/لا/ليس) لا يُسقط البوّابة — جدول المحرَّمات."""
    paths = _mini_repo(tmp_path)
    monkeypatch.setattr(gate, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(gate, "STRATEGY_DOC", paths["strategy"])
    paths["strategy"].write_text(
        "❌ «نضمن أن الوكيل آمن» — ممنوع الإعلان بلا دليل.\n", encoding="utf-8"
    )
    # تعطيل بقية الفحوص كي نحاكم القاعدة وحدها
    for fn in (
        "check_files_exist",
        "check_registry_entry",
        "check_claude_section",
        "check_ci_wiring",
        "check_law_table",
        "check_truth_doc",
        "check_positioning",
        "check_catalog",
        "check_evidence_boundary",
    ):
        monkeypatch.setattr(gate, fn, lambda: None)
    gate._FAILURES.clear()
    gate.main()
    assert not any("عبارةٌ غير قابلةٍ للتفنيد" in f for f in gate._FAILURES)


def test_market_figure_without_citation_rejected(tmp_path: Path, monkeypatch) -> None:
    """رقم سوقٍ (مليار) بلا إحالة [R#] في السطر نفسه يُسقط البوّابة (L3)."""
    paths = _mini_repo(tmp_path)
    monkeypatch.setattr(gate, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(gate, "STRATEGY_DOC", paths["strategy"])
    paths["strategy"].write_text("حجم السوق 50 مليار دولار بحلول 2030.\n", encoding="utf-8")
    gate._FAILURES.clear()
    gate.check_claim_discipline()
    assert any("بلا إحالة مصدر" in f for f in gate._FAILURES)


def test_hypothesis_closed_without_evidence_rejected(tmp_path: Path, monkeypatch) -> None:
    """`CLOSED_CONFIRMED` بلا دليلٍ في العمود الثالث يُسقط البوّابة (L8)."""
    paths = _mini_repo(tmp_path)
    monkeypatch.setattr(gate, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(gate, "TRUTH_DOC", paths["status"])
    paths["status"].write_text(
        "**as-of:** 2026-09-09\n"
        "| GATE_C | `ABSENT` | لا دليل |\n"
        "| H1 | حقن الأعطال | `CLOSED_CONFIRMED` | |\n",
        encoding="utf-8",
    )
    gate._FAILURES.clear()
    gate.check_truth_doc()
    assert any("CLOSED_CONFIRMED بلا دليل" in f for f in gate._FAILURES)


def test_catalog_eighth_line_rejected(tmp_path: Path, monkeypatch) -> None:
    """خطّ عرضٍ ثامن خارج السبعة المصرّحة يُسقط البوّابة (L6 · D-273)."""
    paths = _mini_repo(tmp_path)
    monkeypatch.setattr(gate, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(gate, "CATALOG", paths["catalog"])
    offers = [{"id": offer_id, "status": "PROPOSED"} for offer_id in gate.CANONICAL_OFFER_IDS]
    offers.append({"id": "agent-reliability-evaluation", "status": "PROPOSED"})
    paths["catalog"].write_text(json.dumps({"offers": offers}), encoding="utf-8")
    gate._FAILURES.clear()
    gate.check_catalog()
    assert any("خارج السبعة" in f or "ثامن" in f for f in gate._FAILURES)
