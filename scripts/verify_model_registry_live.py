#!/usr/bin/env python3
"""verify_model_registry_live — هل النموذج الذي نثق به **يُخدَم** فعلاً؟

لماذا هذا المسبار موجود (ISS-200 / D-288 — 2026-09-09)
-------------------------------------------------------
المستودع كان يُصلِّي سلسلة نماذج صلبةً في `shared/ai_models/model_chain.py`
ويحرسها بحُرّاس *نصيين*: «هل الملفّان متطابقان؟» و«هل الحرفية هي ما قرّرته D-167؟».
ولا واحدٌ منهما يسأل OpenRouter: **هل لهذا النموذج endpoint أصلاً؟**

حين أوقفت OpenRouter خدمة النسخ المجانية من `openai/gpt-oss-20b:free`
(`GET /api/v1/models/openai/gpt-oss-20b:free/endpoints` ⇒ `"endpoints": []`) بقي
كل حارس أخضر — لأن الـ id ما زال في الكتالوج — بينما كانت كل دورة دردشة حقيقية
تُنهي نفسها بسطر جاهز بدل إجابة. وأسوأ: `live-e2e.yml` كان يتجاوز PRIMARY بـ
`OPENROUTER_PRIMARY_MODEL`، فظلّت الرحلة خضراء والعطل في **البيئة**، لا في الاختبار.

هذا المسبار يقلب الاتجاه: يقرأ الكتالوج الحيّ لكل نموذج في السلسلة، ويفشل إن كان
PRIMARY بلا endpoint، أو كان نموذجٌ حيّ مصفَّفاً خلف ميت، أو كانت المفتاح مرفوضاً.

Usage
-----
    python scripts/verify_model_registry_live.py                # CI / تشغيل حيّ
    python scripts/verify_model_registry_live.py --json          # مخرج آلي
    python scripts/verify_model_registry_live.py --check-key     # يتحقق من OPENROUTER_API_KEY
    OPENROUTER_BASE_URL=http://127.0.0.1:8100/api/v1 python3 scripts/verify_model_registry_live.py

الخروج: 0 السلسلةُ تُخدَم أو لم نَرَ شيئاً (بلاغةٌ صاخبةٌ لا خضراءَ كاذبة)؛ 1 عطلٌ **مقطوعٌ به**
    في التكوين؛ 2 العَمى نفسُه خطأ — عند ‎--strict‎ فقط، لمن يرفض التشغيل بلا رؤية.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from shared.ai_models.model_chain import FALLBACK_CHAIN, resolve_primary_model

DEFAULT_BASE_URL = "https://openrouter.ai/api/v1"


@dataclass
class ModelStatus:
    """حالة نموذج واحد في الكتالوج الحيّ."""

    model: str
    in_catalog: bool = True
    endpoints: int = 0
    best_provider: str | None = None
    context_length: int | None = None
    max_completion_tokens: int | None = None
    error: str | None = None
    raw: dict[str, object] = field(default_factory=dict)

    @property
    def servable(self) -> bool:
        return self.error is None and self.in_catalog and self.endpoints > 0

    def to_dict(self) -> dict[str, object]:
        return {
            "model": self.model,
            "in_catalog": self.in_catalog,
            "endpoints": self.endpoints,
            "servable": self.servable,
            "provider": self.best_provider,
            "context_length": self.context_length,
            "max_completion_tokens": self.max_completion_tokens,
            "error": self.error,
        }


def chain_from_config() -> list[str]:
    """السلسلة المرتَّبة كما يقرؤها الدماغان: تجاوزُ المُشغِّل ثم الكتالوج المشترك."""
    primary = resolve_primary_model()
    chain = [primary, *[m for m in FALLBACK_CHAIN if m != primary]]
    extra = os.getenv("OPENROUTER_EXTRA_MODELS", "").strip()
    for entry in (m.strip() for m in extra.split(",")):
        if entry and entry not in chain:
            chain.append(entry)
    return chain


def probe_model(
    base_url: str, model: str, timeout: float, api_key: str | None = None
) -> ModelStatus:
    """يقرأ `GET {base}/models/<id>/endpoints` — عامّ، لا يحتاج مفتاحاً."""
    url = f"{base_url.rstrip('/')}/models/{urllib.parse.quote(model, safe='')}/endpoints"
    headers = {"User-Agent": "naas-model-registry-probe/1.0", "Accept": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            return ModelStatus(model=model, in_catalog=False)
        return ModelStatus(model=model, error=f"HTTP {exc.code}")
    except (urllib.error.URLError, TimeoutError, OSError, ValueError) as exc:
        return ModelStatus(model=model, error=f"{type(exc).__name__}: {exc}")

    data = body.get("data") if isinstance(body, dict) else None
    if not isinstance(data, dict):
        return ModelStatus(model=model, in_catalog=False)
    endpoints = [e for e in (data.get("endpoints") or []) if isinstance(e, dict)]
    live = [e for e in endpoints if int(e.get("status", 0) or 0) == 0]
    best = max(live or endpoints, key=lambda e: int(e.get("context_length", 0) or 0), default=None)
    return ModelStatus(
        model=model,
        in_catalog=True,
        endpoints=len(endpoints),
        best_provider=(best or {}).get("provider_name") if best else None,
        context_length=int((best or {}).get("context_length", 0) or 0) if best else None,
        max_completion_tokens=int((best or {}).get("max_completion_tokens", 0) or 0)
        if best
        else None,
        raw=data,
    )


def check_api_key(base_url: str, api_key: str, timeout: float) -> tuple[bool, str]:
    """`GET {base}/auth/key` — يكشف مفتاحاً ملغى/منفَّذًا قبل أن يُفسَّر كل شيء خطأً."""
    url = f"{base_url.rstrip('/')}/auth/key"
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {api_key}"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        return False, f"HTTP {exc.code} — المفتاح مرفوض أو منتهي"
    except (urllib.error.URLError, TimeoutError, OSError, ValueError) as exc:
        return False, f"{type(exc).__name__}: {exc}"
    data = payload.get("data", payload)
    label = data.get("label") or data.get("user_id") or "ok"
    limit = data.get("limit")
    usage = data.get("usage")
    quota = f" (usage={usage}/limit={limit})" if limit is not None else ""
    return True, f"label={label}{quota}"


def _key_verdict(key_ok: bool | None, key_msg: str) -> tuple[list[str], list[str]]:
    """401/403 رفضٌ **يقيني** ⇒ خطأ؛ غيرُ ذلك (شبكة · 429 · 5xx) لم نرَه ⇒ تحذير."""
    if key_ok is not False:
        return [], []
    if re.search(r"HTTP (401|403)\b", key_msg):
        return [f"المفتاح مرفوضٌ يقيناً: {key_msg}"], []
    return [], [f"لم يُتحقَّق من المفتاح (لا حكم): {key_msg}"]


def _dead_lead_count(results: list[ModelStatus]) -> int:
    """كم نموذجاً ميتاً **يقيناً** أمام PRIMARY — لا ما لم نقرأه."""
    dead = 0
    for status in results:
        if status.error is not None or status.servable:
            break
        dead += 1
    return dead


def evaluate(
    results: list[ModelStatus],
    *,
    key_ok: bool | None,
    key_msg: str,
    allow_dead_primary: bool,
    strict: bool = False,
) -> tuple[list[str], list[str], int]:
    """
    أخطاء/تحذيرات/رمز الخروج — القرار كله هنا حتى يبقى `main` قشرةً.

    **الفرق بين «ميت» و«لم نره» هو مُنجِز هذا الملفّ:** بوّابةٌ تُحمِّر الرحلة لانقطاعٍ لا
    تراه تُعلِّم الفريق تجاهلها (دَينُ ISS-199 بعينه — بوّابةٌ حاجبةٌ على ما لا تُطيق). لذا
    لا حكمَ قطعيّاً إلا من **إجابةٍ مقروءة**: 200 بـ`"endpoints": []` ⇒ ميتٌ يقيناً؛ 404 ⇒
    لا نموذج؛ أمّا 429/5xx/انقطاعٌ فعمىً — بلاغةٌ صاخبةٌ برمزِ خروجٍ نظيف، إلّا أن يطلب
    المشغِّل `--strict` فيصير العَمى نفسُه رفضاً.
    """
    errors: list[str] = []
    warnings: list[str] = []

    seen = [r for r in results if r.error is None]
    if not seen:
        note = f"تعذّر الفحص — لا حكم: {results[0].error or 'لا استجابة من سجلّ النماذج'}"
        if strict:
            return [f"{note} (--strict: العَمى رفضٌ صريح)"], [], 2
        return (
            [],
            [
                f"{note} — لا نُحمِّر رحلةً حيّة بانقطاعٍ لا تراه البوّابة؛ شغّل المسبار من "
                "مشغِّلٍ يملك الشبكة، أو بـ--strict حين يُطلب حكمٌ صارم."
            ],
            0,
        )

    servable = [r for r in seen if r.servable]
    primary = results[0]

    if primary.error is not None:
        warnings.append(
            f"لم يُقرأ وضع PRIMARY «{primary.model}»: {primary.error} — والحكمُ على ما قُرِئ فقط."
        )
    elif not primary.servable:
        if allow_dead_primary:
            warnings.append(
                f"PRIMARY «{primary.model}» بلا endpoint — مُسموحٌ به صراحةً (--allow-dead-primary)."
            )
        else:
            errors.append(
                f"PRIMARY «{primary.model}» بلا endpoint قابلٍ للخدمة "
                f"(in_catalog={primary.in_catalog}, endpoints={primary.endpoints}) — "
                "كل دورة دردشة ستفشل صامتة. ارقَ السلسلة إلى نموذج حيّ."
            )

    if not servable:
        errors.append(
            f"لا نموذج واحد من {len(seen)} نال إجابةً تُخدَم ⇒ السلسلة كلها ميتة أو المزوّد أعمى عنا."
        )
    elif primary.error is None and not primary.servable and servable:
        warnings.append(
            f"أول نموذج قابلٍ للخدمة هو «{servable[0].model}» (الموضع "
            f"{results.index(servable[0]) + 1}) — كان الأولى أن يكون PRIMARY."
        )

    dead_lead = _dead_lead_count(results)
    if dead_lead >= 2:
        warnings.append(
            f"أول {dead_lead} نماذج في السلسلة ميتةٌ يقيناً — كل دورةٍ تدفع ثمن القفز فوقها "
            "(زمن + استثناءات) قبل أن تصل إلى إجابة."
        )

    dead = [r for r in seen if not r.servable]
    if dead and not errors:
        warnings.append(
            "نماذجُ ميّتةٌ في السلسلة: "
            + ", ".join(r.model for r in dead[:4])
            + " — فتحاتُ تعافٍ آليّ، لا أسبابُ إفشال."
        )

    key_errors, key_warnings = _key_verdict(key_ok, key_msg)
    errors += key_errors
    warnings += key_warnings
    return errors, warnings, (1 if errors else 0)


def render_text(
    results: list[ModelStatus],
    errors: list[str],
    warnings: list[str],
    base_url: str,
    key_ok,
    key_msg,
) -> None:
    print("=== Live model-registry probe (ISS-200 / D-288) ===")
    print(f"base_url: {base_url}")
    for idx, r in enumerate(results):
        role = "PRIMARY" if idx == 0 else f"FALLBACK_{idx}"
        if r.error:
            mark, detail = "❓", r.error
        elif r.servable:
            mark, detail = (
                "✅",
                f"{r.endpoints} endpoint(s) · {r.best_provider} · ctx={r.context_length}",
            )
        else:
            mark, detail = "🕳", "غير موجود في الكتالوج" if not r.in_catalog else "0 endpoint(s)"
        print(f"  {mark} {role:9s} {r.model:44s} {detail}")
    if key_ok is not None:
        print(f"  {'✅' if key_ok else '❌'} key         {key_msg}")
    for w in warnings:
        print(f"⚠️  {w}")
    for e in errors:
        print(f"❌ {e}")
    if not errors and not warnings:
        print("✅ السلسلة كلها قابلة للخدمة والترتيب سليم — لا نموذج ميت أمام إجابة حيّة.")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    # `scripts/` خارج نطاق حارس الحرفيات عمداً: سكربتٌ مستقلٌّ يقرأ البيئة بيدِه،
    # أمّا في المنتج فموطنُ الاسم `Settings` (D-270 L5).
    parser.add_argument("--base-url", default=os.getenv("OPENROUTER_BASE_URL", DEFAULT_BASE_URL))
    parser.add_argument("--timeout", type=float, default=15.0)
    parser.add_argument("--json", action="store_true", help="مخرج آلي بدل النصي.")
    parser.add_argument(
        "--check-key",
        action="store_true",
        help="يتحقق أيضاً من OPENROUTER_API_KEY عبر /auth/key.",
    )
    parser.add_argument(
        "--allow-dead-primary",
        action="store_true",
        help="لا يُفشِل الرحلة إن كان PRIMARY بلا endpoint (break-glass فقط).",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="العَمى نفسُه خطأ (خروج 2) — لمن يريد رفضَ التشغيل بلا رؤية؛ افتراضياً بلاغةٌ صاخبة.",
    )
    args = parser.parse_args(argv)

    key = os.getenv("OPENROUTER_API_KEY") or ""
    results = [
        probe_model(args.base_url, m, args.timeout, key or None) for m in chain_from_config()
    ]
    key_ok, key_msg = (None, "")
    if args.check_key:
        key_ok, key_msg = (
            (False, "OPENROUTER_API_KEY غير مضبوط")
            if not key
            else check_api_key(args.base_url, key, args.timeout)
        )
    errors, warnings, code = evaluate(
        results,
        key_ok=key_ok,
        key_msg=key_msg,
        allow_dead_primary=args.allow_dead_primary,
        strict=args.strict,
    )

    if args.json:
        print(
            json.dumps(
                {
                    "base_url": args.base_url,
                    "primary": results[0].model,
                    "models": [r.to_dict() for r in results],
                    "servable_count": sum(1 for r in results if r.servable),
                    "key_check": None if key_ok is None else {"ok": key_ok, "detail": key_msg},
                    "errors": errors,
                    "warnings": warnings,
                    "exit_code": code,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
    else:
        render_text(results, errors, warnings, args.base_url, key_ok, key_msg)
    return code


if __name__ == "__main__":
    raise SystemExit(main())
