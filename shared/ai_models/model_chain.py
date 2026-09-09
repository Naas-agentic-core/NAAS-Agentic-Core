"""Canonical OpenRouter model chain — the single source of truth for both brains.

Why this file exists
--------------------
The monolith brain (`app/core/ai_config.py`) and the orchestrator brain
(`microservices/orchestrator_service/src/core/ai_config.py`) each declare the
active model + fallback chain. Historically D-013 kept them in sync by a prose
"edit both copies in the same PR" rule, and `check_legacy_invariants.py` +
`test_iss079_catastrophic_fixes.py` pin the safety-critical literals **inside each
file** (defense-in-depth from the ISS-079 "pepepe" catastrophe — those pins stay).

What was missing was a machine check that the two brains actually declare the
**same ordered chain**. This module is the canonical declaration of that chain,
and `scripts/fitness/check_model_chain_parity.py` statically proves both brains
match it. Update the chain here first, then mirror the pinned literals into the
two `ai_config.py` files; the parity gate fails CI if any of the three drift.

Contract (D-067 → D-280, re-verified live 2026-09-09)
-----------------------------------------------------
* PRIMARY MUST be a model that returns real `content` (never reasoning-only) with
  Arabic + LaTeX and `finish=stop`. Reasoning-only models (`content=None` with a
  system prompt) are banned as PRIMARY — that is the ISS-079 catastrophe.
* PRIMARY must also have a **serving endpoint**. `openai/gpt-oss-20b:free` was the
  verified PRIMARY through D-167, then OpenRouter dropped every free endpoint for
  it: `GET /api/v1/models/openai/gpt-oss-20b:free/endpoints` now answers
  `"endpoints": []`. A model id that still resolves in the catalog but has no
  endpoint fails at request time, so `ci.yml` could stay green while every student
  turn died — CI overrode the model with `OPENROUTER_PRIMARY_MODEL`
  (`.github/workflows/live-e2e.yml`, D-280) while the **runtime** kept the dead
  literal. `scripts/verify_model_registry_live.py` is now the guard that reads the
  live catalog instead of trusting the id.
* Models with no endpoint today stay in the chain **only as auto-recovery slots**
  (the guards skip a dead model in milliseconds), never in front of a live one.
"""

from __future__ import annotations

import os

# --- The verified PRIMARY (D-280 — live catalog probe 2026-09-09). ----------
# gemma-4-31b-it:free — Arabic + LaTeX, finish=stop (benchmarked live in D-167),
# and the model `live-e2e.yml` has been proving green since D-280. It has a live
# endpoint today; `openai/gpt-oss-20b:free` does not.
PRIMARY_MODEL = "google/gemma-4-31b-it:free"

# --- Ordered fallback chain (D-280 — live endpoint status 2026-09-09). ------
# Kept as named constants so both the canonical `FALLBACK_CHAIN` and any future
# consumer read the same values. The two brains still declare their own pinned
# copies; the parity gate proves equality.
FALLBACK_1 = "google/gemma-4-26b-a4b-it:free"  # ✅ live endpoint — Arabic + LaTeX
FALLBACK_2 = "nvidia/nemotron-3.5-lightning:free"  # ✅ live endpoint (1M ctx) — D-280 CI slot
FALLBACK_3 = (
    "openai/gpt-oss-20b:free"  # 🕳 0 endpoints today — auto-recovery slot (historical D-067 PRIMARY)
)
FALLBACK_4 = "openai/gpt-oss-120b:free"  # 🕳 0 endpoints — auto-recovery slot
FALLBACK_5 = "nvidia/nemotron-3-nano-30b-a3b:free"  # fast; guarded by content==0 + Arabic stream guard (never PRIMARY — D-067)

FALLBACK_CHAIN: tuple[str, ...] = (
    FALLBACK_1,
    FALLBACK_2,
    FALLBACK_3,
    FALLBACK_4,
    FALLBACK_5,
)

# The full ordered chain: PRIMARY first, then the five fallbacks.
MODEL_CHAIN: tuple[str, ...] = (PRIMARY_MODEL, *FALLBACK_CHAIN)

# Env override honored by both brains' `_resolve_primary_model`.
PRIMARY_OVERRIDE_ENV = "OPENROUTER_PRIMARY_MODEL"

# Every model id in the chain that must never be answered with a canned line
# instead of a real generation — see `AllModelsFailedError` in the LLM client.
MODEL_CHAIN_ENV_ORDER: tuple[str, ...] = MODEL_CHAIN


def resolve_primary_model(default_model: str = PRIMARY_MODEL) -> str:
    """Resolve the PRIMARY model from the environment with a safe default.

    Reads ``OPENROUTER_PRIMARY_MODEL`` (stripped); falls back to ``default_model``.
    This is the canonical implementation; each brain keeps a same-named local
    helper for its gate-pinned ``PRIMARY = _resolve_primary_model(...)`` line.
    """
    override = os.getenv(PRIMARY_OVERRIDE_ENV, "").strip()
    return override or default_model


__all__ = [
    "FALLBACK_CHAIN",
    "MODEL_CHAIN",
    "MODEL_CHAIN_ENV_ORDER",
    "PRIMARY_MODEL",
    "PRIMARY_OVERRIDE_ENV",
    "resolve_primary_model",
]
