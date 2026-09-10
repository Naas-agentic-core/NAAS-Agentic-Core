#!/usr/bin/env python3
"""بوّابة دستور اعتمادية الوكلاء والعملة الصعبة (D-290).

تحرس القواعد الدستورية التالية:
- وجود وثيقة القانون ووثيقة الحالة ووثيقة الأطروحة (الاستراتيجية) على القرص.
- تسجيل الدستور في CONSTITUTION_REGISTRY.json (§0.29) وربط قسمه في CLAUDE.md.
- ربط البوّابة نفسها بوظيفة `guardrails` في ci.yml — فارضٌ يضمّن عدم فكّ أسلاكه بصمت.
- جدول القوانين L1–L10: كل صفّ يسمّي فارضاً موجوداً على القرص.
- انضباط وثيقة الحالة: `GATE_C` صريحة، وحالات H1–H7 من مجموعة مغلقة، و`CLOSED_CONFIRMED`
  بلا دليلٍ في العمود الثالث = انتهاك.
- حدّ المصداقية (L3): عباراتٌ غير قابلةٍ للتفنيد ممنوعة في الوثائق الثلاث — والاستثناء
  الوحيد: سطرٌ يعلن المنعَ بذاته (❌/⛔/يُمنع/يحظر) أو ينفيه بذاته (لا/ليس/ممنوع).
- أرقام السوق (مليار/حجم سوق) في الوثيقة الاستراتيجية تتطلّب إحالة مصدر `[R#]` في نفس
  السطر، و⛔ ممنوعةٌ نهائياً من وثيقتَي القانون والحالة.
- المواضع الأربعة (L2 · L4 · L5) ثابتةٌ نصيّاً: Compute-Agnostic · Framework-Agnostic ·
  Adapter Layer · Compute Abstraction · Sovereignty-as-option.
- خطوط OFFER_CATALOG السبعة (D-273): لا خطّ ثامن، و`PAID_PROOF`/`REPEATABLE` بلا دليل
  مذكور في `evidence_paths` = انتهاك.
- عدم استعارة أدلّة D-267 (L9): ذكر `naas_verifier` أو قياس «90 نقطة» يلزمه حدٌّ صريح
  في السطر نفسه أو في سطرَي ما بعده.

**لا تُستورد من `app/`** — نصّية خالصة تعمل في بيئة متدهورة. Exit 0 = نظيف · 1 = انتهاك.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

LAW_DOC = REPO_ROOT / ".memory" / "agent_reliability_hard_currency_constitution.md"
TRUTH_DOC = REPO_ROOT / ".memory" / "agent_reliability_hard_currency_truth.md"
STRATEGY_DOC = REPO_ROOT / "docs" / "commercial" / "NAAS_AGENT_RELIABILITY_STRATEGIC_RESEARCH.md"
REGISTRY = REPO_ROOT / "docs" / "governance" / "CONSTITUTION_REGISTRY.json"
CLAUDE_MD = REPO_ROOT / "CLAUDE.md"
CI_WORKFLOW = REPO_ROOT / ".github" / "workflows" / "ci.yml"
CATALOG = REPO_ROOT / "docs" / "commercial" / "OFFER_CATALOG.json"

CONSTITUTION_ID = "D-290"
CONSTITUTION_SECTION = "0.29"
GATE_NAME = "check_agent_reliability_constitution.py"

#: المواضع الأربعة — نصوصٌ لا يجوز غيابها من الأطروحة ولا من القانون.
POSITIONING_MARKERS = (
    "Compute-Agnostic",
    "Framework-Agnostic",
    "Adapter Layer",
    "Compute Abstraction",
    "Sovereign",
    "06-2021",
)

#: العبارات غير القابلة للتفنيد — سطرٌ يحمل إحداها يجب أن يُعلن المنعَ أو النفيَ بذاته.
FORBIDDEN_PHRASES = (
    "نضمن",
    "مضمون",
    "مضمونة",
    "يغيّر البشرية",
    "يغير البشرية",
    "أكبر حوسبة",
    "بديل AWS",
    "بديل عن AWS",
    "أفضل من كل المنافسين",
    "سنحقق",
    "سنجني",
    "يضمن",
)

#: أدوات النفي/المنع المقبولة داخل سطرٍ يحمل عبارةً ممنوعة.
NEGATION_TOKENS = (
    "⛔",
    "❌",
    "يُمنع",
    "يمنع",
    "يُحظَر",
    "يحظر",
    "ممنوع",
    "لا ",
    "ليس",
    "محرّم",
    "محرَّم",
)

#: خطوط الإيراد السبعة المصرّحة دستورياً (D-273) — قائمةٌ معيارية لا رقمٌ متحرّك.
CANONICAL_OFFER_IDS = [
    "ai-red-teaming-multilingual",
    "niche-rlhf-data",
    "on-premise-energy-ai",
    "physics-informed-ai",
    "formal-verification-ai",
    "eu-ai-act-compliance",
    "high-rpm-ai-affiliation",
]

HYPOTHESES = ("H1", "H2", "H3", "H4", "H5", "H6", "H7")
HYPOTHESIS_STATUSES = {"OPEN", "IN_PROGRESS", "CLOSED_CONFIRMED", "CLOSED_REFUTED", "HOLD"}
CATALOG_STATUSES = {"PROPOSED", "DISCOVERY", "OFFER_READY", "PILOT", "PAID_PROOF", "REPEATABLE"}

_FAILURES: list[str] = []


def _fail(msg: str) -> None:
    _FAILURES.append(msg)
    print(f"❌ D-290: {msg}", file=sys.stderr)


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _text(path: Path) -> str:
    return _read(path) if path.is_file() else ""


# --------------------------------------------------------------------------- #
# 1) وجود الملفات
# --------------------------------------------------------------------------- #
def check_files_exist() -> None:
    for doc, _label in (
        (LAW_DOC, "وثيقة القانون"),
        (TRUTH_DOC, "وثيقة الحالة"),
        (STRATEGY_DOC, "وثيقة الأطروحة (الاستراتيجية)"),
        (REGISTRY, "السجلّ الدستوري"),
        (CLAUDE_MD, "الدستور التشغيلي CLAUDE.md"),
        (CI_WORKFLOW, "workflow CI"),
        (CATALOG, "كتالوج العروض"),
    ):
        if not doc.exists():
            _fail(f"ملفٌ غائب: {doc.relative_to(REPO_ROOT)}")


# --------------------------------------------------------------------------- #
# 2) السجلّ الدستوري وقسم CLAUDE.md
# --------------------------------------------------------------------------- #
def check_registry_entry() -> None:
    if not REGISTRY.exists():
        return
    try:
        registry = json.loads(_read(REGISTRY))
    except json.JSONDecodeError as error:
        _fail(f"السجلّ الدستوري غير صالح JSON: {error}")
        return
    rows = list(registry.get("core_doctrines", [])) + list(registry.get("constitutions", []))
    entry = next((row for row in rows if row.get("id") == CONSTITUTION_ID), None)
    if entry is None:
        _fail(f"صف {CONSTITUTION_ID} غير مسجّل في CONSTITUTION_REGISTRY.json")
        return
    if str(entry.get("section")) != CONSTITUTION_SECTION:
        _fail(
            f"صف {CONSTITUTION_ID} يحمل قسماً غير {CONSTITUTION_SECTION}: {entry.get('section')!r}"
        )
    for key in ("law_docs", "status_docs"):
        for rel in entry.get(key, []):
            if not (REPO_ROOT / rel).exists():
                _fail(f"مسارٌ في السجلّ لا وجود له: {rel}")
    enforcers = entry.get("enforcers", [])
    if GATE_NAME not in enforcers:
        _fail(f"السجلّ لا يسمّي فارض هذه العقيدة `{GATE_NAME}`")


def check_claude_section() -> None:
    if not CLAUDE_MD.exists():
        return
    text = _read(CLAUDE_MD)
    # CONSTITUTION_SECTION = "0.29" → نبحث عن "## 0.29."
    marker = f"## {CONSTITUTION_SECTION}."
    if marker not in text:
        _fail(f"قسم {marker} غائب من CLAUDE.md")
    elif CONSTITUTION_ID not in text[text.find(marker) : text.find(marker) + 400]:
        _fail(f"قسم {marker} في CLAUDE.md لا يذكر {CONSTITUTION_ID}")


def check_ci_wiring() -> None:
    """بوّابةٌ تُفكّ أسلاكها بفارضٍ واحد: تُفشل هي نفسها إن غابت عن `guardrails`."""
    if not CI_WORKFLOW.exists():
        return
    text = _read(CI_WORKFLOW)
    if "  guardrails:" not in text:
        _fail("لا توجد وظيفة guardrails في ci.yml")
        return
    guardrails_text = text[text.find("  guardrails:") :]
    if GATE_NAME not in guardrails_text:
        _fail(f"الفارض `{GATE_NAME}` غير مسلوكٍ في وظيفة guardrails — فارضٌ بلا مرمى (D-266)")
    if "set -euo pipefail" not in guardrails_text:
        _fail("guardrails لا يعمل في وضع fail-closed (set -euo pipefail مفقود)")


# --------------------------------------------------------------------------- #
# 3) جدول القوانين L1–L10
# --------------------------------------------------------------------------- #
def check_law_table() -> None:
    if not LAW_DOC.exists():
        return
    text = _read(LAW_DOC)
    gate_names = (
        {p.name for p in (REPO_ROOT / "scripts" / "fitness").glob("check_*.py")}
        | {p.name for p in (REPO_ROOT / "tools" / "ci").glob("check_*.py")}
        | {
            "check_deep_tech_constitution.py",
            "check_revenue_doctrine.py",
            "check_naas_verification.py",
            "check_governance_registry.py",
            "check_documentation_contract.py",
        }
    )
    for law in range(1, 11):
        row = re.search(rf"^\|\s*L{law}\s*\|(.+)$", text, flags=re.MULTILINE)
        if not row:
            _fail(f"القانون L{law} غائب من جدول القوانين")
            continue
        # الفواصل المُهرَّبة `\|` داخل خلايا النصّ لا تُعدّ أعمدةً
        cells = [c.strip() for c in re.split(r"(?<!\\)\|", row.group(1))]
        while cells and not cells[-1]:
            cells.pop()
        if len(cells) < 2:
            _fail(f"صفّ القانون L{law} ناقص الأعمدة")
            continue
        enforcer_cell = cells[-2]
        if not enforcer_cell:
            _fail(f"صفّ القانون L{law} بلا فارضٍ مسمّى")
            continue
        named = re.findall(r"`([\w./-]+\.py)`", enforcer_cell)
        if not named:
            _fail(f"صفّ القانون L{law} يسمّي فارضاً بلا أسماء ملفاتٍ في backticks")
            continue
        for name in named:
            if Path(name).name not in gate_names:
                _fail(f"القانون L{law} يسمّي فارضاً غير موجود على القرص: {name}")
    # الفصل الثلاثي (L1): لا عمود حالةٍ في جدول القوانين
    if re.search(r"^\|\s*#\s*\|\s*الحالة\s*\|", text, flags=re.MULTILINE):
        _fail("وثيقة القانون تحمل عمود حالة — الفصل بنيويّ (L1)")


# --------------------------------------------------------------------------- #
# 4) وثيقة الحالة — GATE_C وحالات الفرضيات
# --------------------------------------------------------------------------- #
def check_truth_doc() -> None:
    if not TRUTH_DOC.exists():
        return
    text = _read(TRUTH_DOC)
    if CONSTITUTION_ID not in text:
        _fail("وثيقة الحالة لا تذكر D-290")
    if not re.search(r"^\|\s*`?GATE_C", text, flags=re.MULTILINE):
        _fail("وثيقة الحالة بلا سطر GATE_C صريح")
    elif not re.search(
        r"^\|\s*`?GATE_C[^\n]*\|\s*`ABSENT`\s*\|", text, flags=re.MULTILINE
    ) and not re.search(
        r"^\|\s*`?GATE_C[^\n]*\|\s*`ACTIVE`\s*[^\n]*دليل", text, flags=re.MULTILINE
    ):
        _fail("GATE_C بلا حالةٍ معتمدة (`ABSENT` أو `ACTIVE` بدليلٍ في السطر نفسه)")
    # الحالات مغلقة
    for hyp in HYPOTHESES:
        row = re.search(rf"^\|\s*{hyp}\s*\|(.+)$", text, flags=re.MULTILINE)
        if not row:
            _fail(f"صفّ الفرضية {hyp} غائب من سجلّ الفرضيات")
            continue
        cells = [c.strip() for c in row.group(1).split("|")]
        status = cells[1].strip("` ") if len(cells) > 1 else ""
        if status not in HYPOTHESIS_STATUSES:
            _fail(f"الفرضية {hyp} بحالةٍ خارج المجموعة المغلقة: {status!r}")
        if status == "CLOSED_CONFIRMED":
            evidence = " ".join(cells[2:]) if len(cells) > 2 else ""
            if not (re.search(r"دليل", evidence) or re.search(r"`[^`]+`", evidence)):
                _fail(f"الفرضية {hyp} أُعلنت CLOSED_CONFIRMED بلا دليلٍ في العمود الثالث")
    if not re.search(r"^\s*\*\*as-of:\*\*", text, flags=re.MULTILINE):
        _fail("وثيقة الحالة بلا تاريخ as-of")
    # L1: وثيقة الحالة لا تحمل صفوف قانون
    if re.search(r"^\|\s*L\d+\s*\|", text, flags=re.MULTILINE):
        _fail("وثيقة الحالة تحمل صفوف قانون L# — الفصل بنيويّ (L1)")


# --------------------------------------------------------------------------- #
# 5) حدّ المصداقية — العبارات الممنوعة وأرقام السوق
# --------------------------------------------------------------------------- #
def _line_allowed(line: str) -> bool:
    return any(token in line for token in NEGATION_TOKENS)


def check_claim_discipline() -> None:
    for doc, label in (
        (TRUTH_DOC, "وثيقة الحالة"),
        (LAW_DOC, "وثيقة القانون"),
        (STRATEGY_DOC, "الوثيقة الاستراتيجية"),
    ):
        if not doc.exists():
            continue
        text = _read(doc)
        for lineno, line in enumerate(text.splitlines(), 1):
            for phrase in FORBIDDEN_PHRASES:
                if phrase in line and not _line_allowed(line):
                    _fail(
                        f"{label} سطر {lineno}: عبارةٌ غير قابلةٍ للتفنيد بلا منعٍ/نفيٍّ صريح — «{phrase}»"
                    )
                    break
        # أرقام السوق: الاستراتيجية تتطلّب إحالةً، والقانون والحالة لا يجوزانها
        for lineno, line in enumerate(text.splitlines(), 1):
            if "مليار" not in line and "حجم سوق" not in line:
                continue
            if _line_allowed(line):
                continue  # سطرُ منعٍ/نفيٍّ ضمن جدول المحرَّمات — مسموح
            if re.match(r"^\|\s*R\d+\s*\|", line):
                continue  # صفّ جدول المصادر نفسه هو الإحالة
            if label != "الوثيقة الاستراتيجية":
                _fail(f"{label} سطر {lineno}: رقم/حجم سوقٍ ممنوعٌ نهائياً من وثيقة القانون/الحالة")
                break
            if not re.search(r"\[R\d+\]", line):
                _fail(f"{label} سطر {lineno}: رقم سوقٍ بلا إحالة مصدرٍ `[R#]` في نفس السطر")
                break


# --------------------------------------------------------------------------- #
# 6) المواضع النصّية (L2 · L4 · L5 · L7)
# --------------------------------------------------------------------------- #
def check_positioning() -> None:
    strategy = _text(STRATEGY_DOC)
    law = _text(LAW_DOC)
    for marker in POSITIONING_MARKERS:
        if marker not in strategy:
            _fail(f"الوثيقة الاستراتيجية بلا موضع إلزامي: «{marker}»")
        if marker not in law and marker != "06-2021":
            _fail(f"وثيقة القانون بلا موضع إلزامي: «{marker}»")
    if "CPST" not in strategy or "Cost per Successful Task" not in strategy:
        _fail("الوثيقة الاستراتيجية بلا مقياس CPST (L7)")
    if not re.search(r"[🟢🟡🔴]", strategy):
        _fail("الوثيقة الاستراتيجية بلا أوسمة تصنيف (🟢/🟡/🔴)")
    if len(re.findall(r"^\|\s*R\d+\s*\|", strategy, flags=re.MULTILINE)) < 10:
        _fail("الوثيقة الاستراتيجية بلا جدول مصادرٍ بحدود ≥10 إحالات R#")
    for hyp in HYPOTHESES:
        if not re.search(rf"^\|\s*{hyp}\s*\|", strategy, flags=re.MULTILINE):
            _fail(f"جدول الفرضيات في الوثيقة الاستراتيجية بلا {hyp}")


# --------------------------------------------------------------------------- #
# 7) كتالوج العروض — السبعة المصرّحة فقط (L6)
# --------------------------------------------------------------------------- #
def check_catalog() -> None:
    if not CATALOG.exists():
        return
    try:
        catalog = json.loads(_read(CATALOG))
    except json.JSONDecodeError as error:
        _fail(f"OFFER_CATALOG.json غير صالح JSON: {error}")
        return
    offers = catalog.get("offers", [])
    ids = [offer.get("id") for offer in offers]
    if ids != CANONICAL_OFFER_IDS:
        extra = [i for i in ids if i not in CANONICAL_OFFER_IDS]
        missing = [i for i in CANONICAL_OFFER_IDS if i not in ids]
        if extra:
            _fail(f"خطّ عرضٍ خارج السبعة المصرّحة (يتطلّب قرار حوكمة D-273): {sorted(extra)}")
        if missing:
            _fail(f"خطوط السبعة المصرّحة ناقصة من الكتالوج: {sorted(missing)}")
    for offer in offers:
        status = offer.get("status")
        if status not in CATALOG_STATUSES:
            _fail(f"خطّ {offer.get('id')}: حالة خارج المجموعة: {status!r}")
        if status in {"PAID_PROOF", "REPEATABLE"} and not offer.get("evidence_paths"):
            _fail(f"خطّ {offer.get('id')}: حالة دفعٍ بلا evidence_paths")


# --------------------------------------------------------------------------- #
# 8) عدم استعارة أدلّة D-267 (L9)
# --------------------------------------------------------------------------- #
def check_evidence_boundary() -> None:
    for doc, label in ((STRATEGY_DOC, "الوثيقة الاستراتيجية"), (TRUTH_DOC, "وثيقة الحالة")):
        if not doc.exists():
            continue
        lines = _read(doc).splitlines()
        for idx, line in enumerate(lines):
            if "naas_verifier" not in line and "90 نقطة" not in line:
                continue
            window = " ".join(lines[max(0, idx - 2) : idx + 3])
            if not re.search(r"بحدود|بحد|حدّ|بحدوده|بحدودها|مستقل", window):
                _fail(f"{label} سطر {idx + 1}: ذكرُ أداة D-267 بلا حدّها الصريح (L9)")


# --------------------------------------------------------------------------- #
def main() -> int:
    check_files_exist()
    check_registry_entry()
    check_claude_section()
    check_ci_wiring()
    check_law_table()
    check_truth_doc()
    check_claim_discipline()
    check_positioning()
    check_catalog()
    check_evidence_boundary()

    if _FAILURES:
        print(
            f"check_agent_reliability_constitution: FAIL ({len(_FAILURES)} انتهاكاً)",
            file=sys.stderr,
        )
        return 1
    print("check_agent_reliability_constitution: PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
