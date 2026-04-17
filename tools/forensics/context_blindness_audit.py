"""محرك تشريح جنائي عميق لظاهرة عمى السياق في الأنظمة المعقدة.

ينتج هذا السكربت حزمة تحقيق قابلة للمراجعة تضم:
1) تقرير Markdown تفصيلي.
2) ملف JSON منظّم للاستهلاك الآلي في أنظمة الحوكمة والمراقبة.

الهدف هو الانتقال من التشخيص الوصفي إلى تشخيص قابل للقياس والتكرار.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class PatternProbe:
    """قاعدة فحص تربط نمطًا نصيًا بخطر سياقي محدد."""

    code: str
    file_path: str
    pattern: str
    description: str
    risk_group: str
    weight: int
    layer: str


@dataclass(frozen=True)
class ProbeHit:
    """نتيجة مطابقة مع معلومات التتبع."""

    code: str
    file_path: str
    line_number: int
    snippet: str
    description: str
    risk_group: str
    weight: int
    layer: str


PROBES: tuple[PatternProbe, ...] = (
    PatternProbe(
        code="CB-CLI-01",
        file_path="frontend/app/hooks/useAgentSocket.js",
        pattern=r"normalized\.slice\(-30\)",
        description="قص سياق العميل إلى آخر 30 رسالة.",
        risk_group="truncation",
        weight=8,
        layer="client",
    ),
    PatternProbe(
        code="CB-CLI-02",
        file_path="frontend/app/hooks/useAgentSocket.js",
        pattern=r"if \(conversationId !== null && conversationId !== undefined\)",
        description="إرسال conversation_id مشروط بتوفره في الحالة اللحظية.",
        risk_group="identity",
        weight=10,
        layer="client",
    ),
    PatternProbe(
        code="CB-CLI-03",
        file_path="frontend/public/js/legacy-app.jsx",
        pattern=r"socketRef\.current\.close\(\)",
        description="المسار legacy يعيد تدوير socket لكل إرسال.",
        risk_group="transport",
        weight=9,
        layer="transport",
    ),
    PatternProbe(
        code="CB-SRV-01",
        file_path="microservices/orchestrator_service/src/api/routes.py",
        pattern=r"MAX_HISTORY_MESSAGES\s*=\s*24",
        description="نافذة model-input للتاريخ محدودة بـ 24.",
        risk_group="truncation",
        weight=8,
        layer="server",
    ),
    PatternProbe(
        code="CB-SRV-02",
        file_path="microservices/orchestrator_service/src/api/routes.py",
        pattern=r"No context available - cold start",
        description="fallback بارد صامت عند فقد السياق.",
        risk_group="fallback",
        weight=10,
        layer="server",
    ),
    PatternProbe(
        code="CB-SRV-03",
        file_path="microservices/orchestrator_service/src/api/routes.py",
        pattern=r"_extract_recent_entity_anchor",
        description="استرجاع المرساة المرجعية عبر heuristic extraction.",
        risk_group="anchor",
        weight=7,
        layer="semantic",
    ),
    PatternProbe(
        code="CB-SRV-04",
        file_path="microservices/orchestrator_service/src/api/context_utils.py",
        pattern=r"return merged_history\[-80:\]",
        description="الدمج النهائي للتاريخ يُقص إلى آخر 80 عنصرًا.",
        risk_group="truncation",
        weight=7,
        layer="server",
    ),
    PatternProbe(
        code="CB-SRV-05",
        file_path="microservices/orchestrator_service/src/api/context_utils.py",
        pattern=r"DO NOT modify without updating the monolith counterpart",
        description="تحذير صريح من خطر الانجراف بين المسارات.",
        risk_group="drift",
        weight=9,
        layer="governance",
    ),
)


def read_text(path: Path) -> str:
    """قراءة ملف UTF-8 مع فشل صريح إذا الملف غير موجود."""

    return path.read_text(encoding="utf-8")


def probe_file(root: Path, probe: PatternProbe) -> list[ProbeHit]:
    """تشغيل probe واحد على ملف واحد وإرجاع المطابقات."""

    content = read_text(root / probe.file_path)
    lines = content.splitlines()
    regex = re.compile(probe.pattern)
    hits: list[ProbeHit] = []

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
                    weight=probe.weight,
                    layer=probe.layer,
                )
            )
    return hits


def count_by_key(hits: list[ProbeHit], key: str) -> dict[str, int]:
    """تجميع عددي حسب مفتاح (risk_group أو layer)."""

    counts: dict[str, int] = {}
    for hit in hits:
        value = getattr(hit, key)
        counts[value] = counts.get(value, 0) + 1
    return counts


def weighted_risk_score(hits: list[ProbeHit]) -> tuple[int, int]:
    """حساب درجة الخطر الموزونة (0..100) وإجمالي النقاط الخام."""

    if not hits:
        return 0, 0

    raw_points = sum(hit.weight for hit in hits)
    theoretical_max = len(hits) * 10
    score = round((raw_points / theoretical_max) * 100)
    return score, raw_points


def classify_severity(score: int) -> str:
    """تصنيف شدة المخاطر اعتمادًا على الدرجة الموزونة."""

    if score >= 85:
        return "حرج جدًا"
    if score >= 70:
        return "حرج"
    if score >= 55:
        return "عالٍ"
    if score >= 40:
        return "متوسط"
    return "منخفض"


def top_findings(hits: list[ProbeHit], limit: int = 5) -> list[ProbeHit]:
    """استخراج أعلى الدلائل خطورة حسب الوزن ثم حسب السطر."""

    ordered = sorted(hits, key=lambda item: (-item.weight, item.file_path, item.line_number))
    return ordered[:limit]


def build_json_pack(
    hits: list[ProbeHit],
    risk_counts: dict[str, int],
    layer_counts: dict[str, int],
    score: int,
    raw_points: int,
) -> dict[str, object]:
    """بناء حمولة JSON موحدة للحوكمة والتحليل اللاحق."""

    evidence_items: list[dict[str, object]] = []
    for hit in sorted(hits, key=lambda item: (item.file_path, item.line_number, item.code)):
        evidence_items.append(
            {
                "code": hit.code,
                "file": hit.file_path,
                "line": hit.line_number,
                "layer": hit.layer,
                "risk_group": hit.risk_group,
                "weight": hit.weight,
                "description": hit.description,
                "snippet": hit.snippet,
            }
        )

    pack: dict[str, object] = {
        "summary": {
            "evidence_hits": len(hits),
            "risk_score_0_100": score,
            "raw_weight_points": raw_points,
            "severity": classify_severity(score),
        },
        "distribution": {
            "by_risk_group": risk_counts,
            "by_layer": layer_counts,
        },
        "causal_chain": [
            "client_truncation",
            "identity_conditional_send",
            "legacy_transport_instability",
            "server_history_truncation",
            "silent_cold_start_fallback",
            "heuristic_anchor_recovery",
            "path_drift_risk",
        ],
        "evidence": evidence_items,
        "closure_controls": [
            "enforce_context_continuity_contract",
            "reject_ambiguous_without_anchor",
            "disable_legacy_in_prod",
            "emit_context_contract_violation_metrics",
        ],
    }
    return pack


def render_markdown(
    hits: list[ProbeHit],
    risk_counts: dict[str, int],
    layer_counts: dict[str, int],
    score: int,
    raw_points: int,
) -> str:
    """توليد تقرير Markdown تشريحي قابل للمراجعة البشرية."""

    severity = classify_severity(score)
    ordered_hits = sorted(hits, key=lambda item: (item.file_path, item.line_number, item.code))
    top = top_findings(hits, limit=6)

    out: list[str] = []
    out.append("# تقرير التشريح الجنائي العميق لعمى السياق (Generated)")
    out.append("")
    out.append("## 1) لوحة القيادة التنفيذية")
    out.append("")
    out.append(f"- **إجمالي الأدلة:** {len(hits)}")
    out.append(f"- **النقاط الخام:** {raw_points}")
    out.append(f"- **الدرجة الموزونة:** {score}/100")
    out.append(f"- **تصنيف الشدة:** {severity}")
    out.append("")

    out.append("## 2) توزيع المخاطر حسب المجموعة")
    out.append("")
    out.append("| المجموعة | عدد الأدلة |")
    out.append("|---|---:|")
    for key in sorted(risk_counts):
        out.append(f"| {key} | {risk_counts[key]} |")
    out.append("")

    out.append("## 3) توزيع المخاطر حسب الطبقة")
    out.append("")
    out.append("| الطبقة | عدد الأدلة |")
    out.append("|---|---:|")
    for key in sorted(layer_counts):
        out.append(f"| {key} | {layer_counts[key]} |")
    out.append("")

    out.append("## 4) أعلى الأدلة خطورة")
    out.append("")
    out.append("| الكود | الوزن | الملف | السطر | الدلالة |")
    out.append("|---|---:|---|---:|---|")
    for hit in top:
        out.append(
            f"| {hit.code} | {hit.weight} | `{hit.file_path}` | {hit.line_number} | {hit.description} |"
        )
    out.append("")

    out.append("## 5) سجل الأدلة الكامل")
    out.append("")
    out.append("| الكود | الطبقة | المجموعة | الوزن | الملف | السطر |")
    out.append("|---|---|---|---:|---|---:|")
    for hit in ordered_hits:
        out.append(
            f"| {hit.code} | {hit.layer} | {hit.risk_group} | {hit.weight} | `{hit.file_path}` | {hit.line_number} |"
        )
    out.append("")

    out.append("## 6) سلسلة الانهيار السببية")
    out.append("")
    out.append("1. قص مبكر للسياق في العميل.")
    out.append("2. احتمال إرسال follow-up بلا هوية ثابتة.")
    out.append("3. لااستقرار نقلي في مسار legacy.")
    out.append("4. قص إضافي للسياق في الخادم.")
    out.append("5. fallback بارد صامت.")
    out.append("6. اعتماد recovery heuristic.")
    out.append("7. خطر drift بين المسارات.")
    out.append("")

    out.append("## 7) مقتطفات دليل خام")
    out.append("")
    for hit in ordered_hits:
        out.append(
            f"- `{hit.code}` @ `{hit.file_path}:{hit.line_number}` → `{hit.snippet}`"
        )
    out.append("")

    out.append("## 8) تشخيص جذري نهائي")
    out.append("")
    out.append(
        "السبب الجذري الأعلى: غياب عقد استمرارية سياق قابل للتحقق "
        "(Identity + Integrity + Anchor + Explicit Failure)."
    )
    out.append("")

    out.append("## 9) إجراءات إغلاق فورية")
    out.append("")
    out.append("- فرض Context Continuity Contract على follow-up.")
    out.append("- رفض صريح لأي follow-up إحالي دون anchor.")
    out.append("- إيقاف legacy path في الإنتاج الحرج.")
    out.append("- تفعيل مقاييس violations والانحراف البارد.")
    out.append("")

    return "\n".join(out) + "\n"


def main() -> None:
    """تجميع الأدلة، توليد Markdown/JSON، وطباعة ملخص التنفيذ."""

    repo_root = Path(__file__).resolve().parents[2]

    hits: list[ProbeHit] = []
    for probe in PROBES:
        hits.extend(probe_file(repo_root, probe))

    risk_counts = count_by_key(hits, "risk_group")
    layer_counts = count_by_key(hits, "layer")
    score, raw_points = weighted_risk_score(hits)

    report_md = render_markdown(hits, risk_counts, layer_counts, score, raw_points)
    report_json = build_json_pack(hits, risk_counts, layer_counts, score, raw_points)

    out_md = repo_root / "docs/architecture/CONTEXT_BLINDNESS_DEEP_TRACE_REPORT_AR.md"
    out_json = repo_root / "docs/architecture/CONTEXT_BLINDNESS_FORENSIC_PACK_AR.json"

    out_md.write_text(report_md, encoding="utf-8")
    out_json.write_text(json.dumps(report_json, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"Generated markdown: {out_md}")
    print(f"Generated json pack: {out_json}")
    print(f"Evidence hits: {len(hits)}")
    print(f"Weighted score: {score}/100 ({classify_severity(score)})")


if __name__ == "__main__":
    main()
