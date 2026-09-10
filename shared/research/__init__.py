"""حزمة البحث المستقل — معرفة جديدة قابلة للتصدير بالعملة الصعبة.

هذه الحزمة تولّد معرفة جديدة كلياً: معامل المعرفة الدائمة القابل للتصدير (CDKC)
الذي يجمع بين:
- BKT للإتقان الدائم
- FSRS لقابلية الاسترجاع
- التحقق الرمزي لصحة المحتوى
- فجوة الوهم للمعايرة
- التبديل اللغوي العربي/الفرنسي/الدارجة

القانون: stdlib فقط، لا استيراد من app/ ولا microservices/ — قابلة للتوريّد والتدقيق.
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

__all__ = [
    "CDKC_VERSION",
    "MIN_OBS_CDKC",
    "CdkcError",
    "CdkcInput",
    "CdkcResult",
    "LanguageSwitchCost",
    "SymbolicWeight",
    "EvalTask",
    "EvalTaskKind",
    "ExportableEvalBundle",
    "compute_cdkc",
    "compute_language_switch_cost",
    "compute_symbolic_weight",
    "build_eval_bundle",
]
