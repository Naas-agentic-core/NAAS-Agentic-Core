#!/usr/bin/env python3
"""قياسٌ حتمي على القرص: هل يكفي بروتوكول H1 المعلن (N=200) إحصائياً؟

## لماذا هذا السكربت موجود

دستور العملة الصعبة (D-290 · L8) يُلزم بأن تكون الفرضيات **قابلة للدحض ومسجَّلة**،
والفرضية H1 فيه تعلن بروتوكولاً: `N=200 أساس مقابل N=200 بحقن أعطال، و≥3 فئات فشل
متميّزة`. لكنّ أحداً لم يسأل السؤال الذي يسبق التنفيذ: **هل ٢٠٠ تشغيلاً تكفي أصلاً
ليُستبعد الصفر من فاصل الفرق؟** إن كانت لا تكفي، فالبروتوكول مُصمَّمٌ ليفشل — وتنفيذه
سيستهلك أسابيع ثم يُنتج «لا نعرف»، فيُقرأ فشلاً في الفرضية وهو فشلٌ في التصميم.

هذا السكربت يجيب بحسابٍ **حتمي** (لا محاكاة، لا عيّنة، لا شبكة): لكلّ حجمِ عيّنةٍ
ونسبةِ فشلٍ مفترضة، يُحسب فاصل نيوكومب للفرق ويُبلَّغ: عرضُه، وهل يستبعد الصفر.

## ما يخرج منه ليس رأياً

الناتج `docs/research/VERA_MEASUREMENTS.json` — ملفّ قياسٍ مؤرَّخ، كلّ رقمٍ فيه
قابلٌ لإعادة الحساب بتشغيل السكربت نفسه. وهو **حسابٌ على مُقدِّر إحصائي**، لا قياسٌ
على عالمٍ حقيقي: لا يدّعي أنّ معدّل الفشل عند عميلٍ بعينه هو كذا، بل يقول: «لو كان
كذا، لاحتجتَ إلى N كهذا لتعرف الفرق».

الوسم: 🟢 **حتمي محسوب** (deterministic-computed) — وهو وسمٌ ثالثٌ مكمّل لا بديل:
🟢 موثق · 🟡 أطروحة · 🔴 فرضية تحتاج قياساً · 🟢⟨ح⟩ حتمي محسوب.

## الاستعمال

    python3 scripts/research/measure_vera_escape_width.py

لا يُكتب في `app/` ولا يستورد منها: الحزمة `shared.research` stdlib خالصة.
"""

from __future__ import annotations

import json
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from shared.research.portable_trust import (
    DEFAULT_REPATRIATION_DEADLINE_DAYS,
    MIN_N_FOR_ESTIMATE,
    contract_term_ceiling,
    newcombe_difference,
    repatriation_breach_risk,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
OUTPUT = REPO_ROOT / "docs" / "research" / "VERA_MEASUREMENTS.json"

#: أحجام العيّنات المفحوصة — ٢٠٠ منها هي المُعلنة في H1، والباقي حولها للمقارنة.
SAMPLE_SIZES: tuple[int, ...] = (50, 100, 200, 400, 800)

#: أزواج (معدّل الفشل في المسار السعيد، معدّله تحت حقن الأعطال).
#: 🟡 هذه **نسبٌ مفترضة للتحليل** لا قياسات: الغرض منها رسمُ منحنى الحساسية،
#: لا ادّعاءُ أنّ هذه هي معدّلات الفشل الحقيقية عند أيّ عميل.
FAILURE_PAIRS: tuple[tuple[float, float], ...] = (
    (0.10, 0.20),
    (0.10, 0.15),
    (0.05, 0.12),
    (0.20, 0.30),
)

#: نِسَب السداد المفحوصة (p50 : p90) — تشتّتٌ معلن: p90 = ratio × p50.
SETTLEMENT_P50: tuple[float, ...] = (30.0, 45.0, 60.0, 90.0)
SETTLEMENT_RATIO: float = 1.8

#: الأجلان المتنازَع عليهما في السؤال المفتوح D-282.
DEADLINES: tuple[int, ...] = (120, 306)

#: z لمستوى 90% — يُستعمل لاشتقاق تشتّت التوزيع من نسبة p90/p50 المُعلنة.
Z_90: float = 1.2815515655446004


def escape_width_table() -> list[dict[str, Any]]:
    """منحنى حساسية: هل يستبعد الفاصل الصفر عند هذا الحجم وهذا الأثر؟"""
    rows: list[dict[str, Any]] = []
    for n in SAMPLE_SIZES:
        for p_base, p_injected in FAILURE_PAIRS:
            interval = newcombe_difference(
                successes_a=int(round(p_base * n)),
                n_a=n,
                successes_b=int(round(p_injected * n)),
                n_b=n,
            )
            if interval is None:
                rows.append(
                    {
                        "n_per_arm": n,
                        "p_baseline": p_base,
                        "p_injected": p_injected,
                        "mature": False,
                        "reason": f"n < {MIN_N_FOR_ESTIMATE}: الفاصل غير صالح للحكم.",
                    }
                )
                continue
            delta = p_injected - p_base
            rows.append(
                {
                    "n_per_arm": n,
                    "p_baseline": p_base,
                    "p_injected": p_injected,
                    "delta_hat": round(delta, 6),
                    "ci_low": round(interval.low, 6),
                    "ci_high": round(interval.high, 6),
                    "ci_width": round(interval.width, 6),
                    "excludes_zero": bool(interval.low > 0.0),
                    "mature": True,
                    "reported_as": "🟢⟨ح⟩ حتمي محسوب على مُقدِّر إحصائي — لا قياسُ عميل",
                }
            )
    return rows


def smallest_decisive_n(p_base: float, p_injected: float) -> int | None:
    """أصغر حجمِ عيّنةٍ يستبعد عنده الفاصلُ الصفر — أو `None` إن لم يحدث في المدى."""
    for n in (50, 100, 150, 200, 300, 400, 600, 800, 1200, 1600, 2400):
        interval = newcombe_difference(
            successes_a=int(round(p_base * n)),
            n_a=n,
            successes_b=int(round(p_injected * n)),
            n_b=n,
        )
        if interval is not None and interval.low > 0.0:
            return n
    return None


def repatriation_table() -> list[dict[str, Any]]:
    """أجل الترحيل بوصفه قيدَ تصميمِ عقد: لكلّ مهلةِ سدادٍ خطرُ الخرق تحت الأجلين."""
    rows: list[dict[str, Any]] = []
    for p50 in SETTLEMENT_P50:
        p90 = p50 * SETTLEMENT_RATIO
        row: dict[str, Any] = {
            "settle_p50_days": p50,
            "settle_p90_days": round(p90, 3),
            "settlement_dispersion_model": f"p90 = {SETTLEMENT_RATIO} × p50 (مُعلن، لا مقيس)",
        }
        for deadline in DEADLINES:
            risk = repatriation_breach_risk(
                settle_p50_days=p50, settle_p90_days=p90, deadline_days=deadline
            )
            row[f"p_breach_at_{deadline}d"] = round(risk.p_breach, 6)
            row[f"verdict_at_{deadline}d"] = str(risk.verdict)
        sigma = math.log(SETTLEMENT_RATIO) / Z_90
        ceiling = contract_term_ceiling(
            settle_sigma=sigma,
            deadline_days=DEFAULT_REPATRIATION_DEADLINE_DAYS,
            target_breach=0.05,
        )
        row["max_p50_days_for_5pct_breach_at_120d"] = round(ceiling, 3)
        rows.append(row)
    return rows


def main() -> int:
    width_rows = escape_width_table()
    decisive = {
        f"{p_base}->{p_injected}": smallest_decisive_n(p_base, p_injected)
        for p_base, p_injected in FAILURE_PAIRS
    }
    payload = {
        "artifact": "VERA_MEASUREMENTS",
        "purpose_ar": (
            "قياسٌ حتمي على القرص لسؤالين يسبقان التنفيذ: (1) هل بروتوكول H1 المُعلن "
            "(N=200) يستبعد الصفر من فاصل الفرق؟ (2) ما أجلُ السداد الذي يجوز منحُه "
            "قبل أن يخرق أجل الترحيل؟"
        ),
        "generated_at_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "generator": "scripts/research/measure_vera_escape_width.py",
        "determinism": "حتمي: لا عشوائية ولا شبكة ولا ساعة في الحساب — الساعة في التقرير فقط.",
        "method": {
            "difference_interval": (
                "Newcombe (1998) Method 10 — فاصل النتيجة الهجين للفرق بين نسبتين"
            ),
            "proportion_interval": "Wilson (1927) score interval",
            "maturity_threshold": MIN_N_FOR_ESTIMATE,
            "settlement_model": "LogNormal(mu=ln p50, sigma=(ln p90 - ln p50)/z90)",
            "warning_ar": (
                "هذا حسابٌ على مُقدِّر إحصائي ونموذجٍ معلن — ليس قياساً على عميلٍ حقيقي. "
                "كلّ نسبةِ فشلٍ هنا مُدخلُ تحليلٍ لا نتيجةُ تجربة."
            ),
        },
        "escape_width_curve": width_rows,
        "smallest_decisive_n": decisive,
        "h1_protocol_verdict": (
            "يُقرأ من `smallest_decisive_n`: إن كان أصغرُ n حاسماً ≤ 200 فبروتوكول H1 "
            "المُعلن كافٍ للأثر المفترض، وإن كان > 200 فالبروتوكول ناقصُ القدرة ويجب "
            "رفعُ N قبل التنفيذ كي لا يُنتج «لا نعرف» ويُقرأ دحضاً للفرضية."
        ),
        "repatriation": repatriation_table(),
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(f"✅ كُتب ملف القياس: {OUTPUT.relative_to(REPO_ROOT)}")
    print(f"   صفوف منحنى الحساسية: {len(width_rows)}")
    print("   أصغر n حاسم لكل أثرٍ مفترض:")
    for key, value in decisive.items():
        print(f"     {key}: {value}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
