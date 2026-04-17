"""مولّد تقرير جنائي عميق لعمى السياق اعتمادًا على تتبّع ثابت للشيفرة.

هذا السكربت لا يقدّم انطباعات عامة؛ بل يستخرج دلائل دقيقة من ملفات محددة
ويربطها بسلسلة سببية موثقة لدعم قرارات هندسية في المشاريع العملاقة.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class PatternProbe:
    """يمثل قاعدة فحص تربط ملفًا بنمط بحث ووصف دلالي للخطر."""

    code: str
    file_path: str
    pattern: str
    description: str
    risk_group: str


@dataclass(frozen=True)
class ProbeHit:
    """يمثل نتيجة مطابقة واحدة مع رقم السطر والمقتطف النصي."""

    code: str
    file_path: str
    line_number: int
    snippet: str
    description: str
    risk_group: str


PROBES: tuple[PatternProbe, ...] = (
    PatternProbe(
        code="CB-CLI-01",
        file_path="frontend/app/hooks/useAgentSocket.js",
        pattern=r"normalized\.slice\(-30\)",
        description="قص سياق العميل إلى آخر 30 رسالة.",
        risk_group="truncation",
    ),
    PatternProbe(
        code="CB-CLI-02",
        file_path="frontend/app/hooks/useAgentSocket.js",
        pattern=r"if \(conversationId !== null && conversationId !== undefined\)",
        description="إرسال conversation_id مشروط بتوفر الحالة لحظة الإرسال.",
        risk_group="identity",
    ),
    PatternProbe(
        code="CB-CLI-03",
        file_path="frontend/public/js/legacy-app.jsx",
        pattern=r"socketRef\.current\.close\(\)",
        description="المسار legacy يغلق socket قبل إنشاء قناة جديدة.",
        risk_group="transport",
    ),
    PatternProbe(
        code="CB-SRV-01",
        file_path="microservices/orchestrator_service/src/api/routes.py",
        pattern=r"MAX_HISTORY_MESSAGES\s*=\s*24",
        description="نافذة تاريخ model input محدودة إلى 24 رسالة.",
        risk_group="truncation",
    ),
    PatternProbe(
        code="CB-SRV-02",
        file_path="microservices/orchestrator_service/src/api/routes.py",
        pattern=r"No context available - cold start",
        description="fallback بارد صامت عند غياب السياق.",
        risk_group="fallback",
    ),
    PatternProbe(
        code="CB-SRV-03",
        file_path="microservices/orchestrator_service/src/api/routes.py",
        pattern=r"_extract_recent_entity_anchor",
        description="الاعتماد على استخراج مرساة إحالية heuristic.",
        risk_group="anchor",
    ),
    PatternProbe(
        code="CB-SRV-04",
        file_path="microservices/orchestrator_service/src/api/context_utils.py",
        pattern=r"return merged_history\[-80:\]",
        description="قص الدمج النهائي للتاريخ إلى 80 عنصرًا.",
        risk_group="truncation",
    ),
    PatternProbe(
        code="CB-SRV-05",
        file_path="microservices/orchestrator_service/src/api/context_utils.py",
        pattern=r"DO NOT modify without updating the monolith counterpart",
        description="وجود تحذير صريح من خطر الانجراف بين المسارات.",
        risk_group="drift",
    ),
)


def read_text(path: Path) -> str:
    """يقرأ ملفًا نصيًا بترميز UTF-8 مع فشل صريح عند الغياب."""

    return path.read_text(encoding="utf-8")


def probe_file(root: Path, probe: PatternProbe) -> list[ProbeHit]:
    """يفحص ملفًا وفق نمط منتظم ويعيد جميع المطابقات مع أسطرها."""

    file_abs = root / probe.file_path
    content = read_text(file_abs)
    lines = content.splitlines()

    hits: list[ProbeHit] = []
    regex = re.compile(probe.pattern)
    for idx, line in enumerate(lines, start=1):
        if regex.search(line):
            hits.append(
                ProbeHit(
                    code=probe.code,
                    file_path=probe.file_path,
                    line_number=idx,
                    snippet=line.strip(),
                    description=probe.description,
                    risk_group=probe.risk_group,
                )
            )
    return hits


def aggregate_by_group(hits: list[ProbeHit]) -> dict[str, int]:
    """يحصي عدد الأدلة المكتشفة لكل مجموعة مخاطر."""

    counts: dict[str, int] = {}
    for hit in hits:
        counts[hit.risk_group] = counts.get(hit.risk_group, 0) + 1
    return counts


def render_markdown(hits: list[ProbeHit], group_counts: dict[str, int]) -> str:
    """يبني تقرير ماركداون شامل مع سلسلة سببية ومؤشرات إغلاق."""

    total_hits = len(hits)
    ordered_hits = sorted(hits, key=lambda item: (item.file_path, item.line_number, item.code))

    lines: list[str] = []
    lines.append("# تقرير التتبع الجنائي العميق لعمى السياق (Generated)")
    lines.append("")
    lines.append("## 1) النتيجة الكلية")
    lines.append("")
    lines.append(
        f"تم العثور على **{total_hits} دليلًا صريحًا** موزعة على {len(group_counts)} مجموعات مخاطر تشغيلية."
    )
    lines.append("")

    lines.append("## 2) توزيع المخاطر")
    lines.append("")
    lines.append("| مجموعة المخاطر | عدد الأدلة |")
    lines.append("|---|---:|")
    for group in sorted(group_counts):
        lines.append(f"| {group} | {group_counts[group]} |")
    lines.append("")

    lines.append("## 3) سجل الأدلة القابل للتتبع")
    lines.append("")
    lines.append("| الكود | الملف | السطر | الدلالة |")
    lines.append("|---|---|---:|---|")
    for hit in ordered_hits:
        lines.append(
            f"| {hit.code} | `{hit.file_path}` | {hit.line_number} | {hit.description} |"
        )
    lines.append("")

    lines.append("## 4) سلسلة الانهيار السببية (Causal Chain)")
    lines.append("")
    lines.append("1. **client truncation** يقلص التاريخ قبل النقل.")
    lines.append("2. **identity conditionality** قد ترسل follow-up دون هوية ثابتة.")
    lines.append("3. **transport instability** في legacy يرفع احتمالات انقطاع التسلسل.")
    lines.append("4. **server truncation** يقلص التاريخ مرة أخرى قبل graph input.")
    lines.append("5. **cold-start fallback** يحول فشل السياق إلى استمرار صامت.")
    lines.append("6. **heuristic anchor extraction** لا يعوض دائمًا فقد المرساة.")
    lines.append("7. **path drift risk** يهدد توحيد السلوك بين المسارات.")
    lines.append("")

    lines.append("## 5) مقتطفات أدلة خام")
    lines.append("")
    for hit in ordered_hits:
        lines.append(
            f"- `{hit.code}` @ `{hit.file_path}:{hit.line_number}` → `{hit.snippet}`"
        )
    lines.append("")

    lines.append("## 6) تشخيص جذري نهائي")
    lines.append("")
    lines.append(
        "السبب الجذري الأعلى: غياب عقد استمرارية سياق قابل للتحقق end-to-end "
        "(Identity + Integrity + Anchor Presence + Explicit Failure Semantics)."
    )
    lines.append("")

    lines.append("## 7) إغلاق هندسي قابل للقياس")
    lines.append("")
    lines.append("- فرض حقول استمرارية إلزامية في follow-up.")
    lines.append("- رفض صريح للحالات الإحالية دون anchor.")
    lines.append("- توحيد المسار وإيقاف legacy في الإنتاج.")
    lines.append("- تفعيل مقاييس ContextContractViolation وColdStartOnFollowup.")
    lines.append("")

    return "\n".join(lines) + "\n"


def main() -> None:
    """نقطة الدخول: يجمع الأدلة وينتج تقريرًا مولدًا في docs/architecture."""

    repo_root = Path(__file__).resolve().parents[2]
    collected_hits: list[ProbeHit] = []
    for probe in PROBES:
        collected_hits.extend(probe_file(repo_root, probe))

    counts = aggregate_by_group(collected_hits)
    report = render_markdown(collected_hits, counts)

    out_path = repo_root / "docs/architecture/CONTEXT_BLINDNESS_DEEP_TRACE_REPORT_AR.md"
    out_path.write_text(report, encoding="utf-8")

    print(f"Generated report: {out_path}")
    print(f"Evidence hits: {len(collected_hits)}")


if __name__ == "__main__":
    main()
