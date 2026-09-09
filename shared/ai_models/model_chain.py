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

Contract (D-067 → D-167, verified live 2026-07-14)
--------------------------------------------------
* PRIMARY MUST be a model that returns real `content` (never reasoning-only) with
  Arabic + LaTeX and `finish=stop`. `openai/gpt-oss-20b:free` is the verified
  PRIMARY. Reasoning-only models (`content=None` with a system prompt) are banned.
* `openai/gpt-oss-120b:free` stays in the tail as an auto-recovery slot — it was
  removed from OpenRouter's free tier (404) but the guards skip a dead model
  instantly, so keeping it costs nothing and it re-activates automatically if the
  free version returns.
"""

from __future__ import annotations

import os

# --- The verified PRIMARY (D-067/D-167). ------------------------------------
PRIMARY_MODEL = "openai/gpt-oss-20b:free"

# --- Ordered fallback chain (D-167 — live benchmark 2026-07-14). -------------
# Kept as named constants so both the canonical `FALLBACK_CHAIN` and any future
# consumer read the same values. The two brains still declare their own pinned
# copies; the parity gate proves equality.
FALLBACK_1 = "google/gemma-4-26b-a4b-it:free"  # GOOD live — Arabic + LaTeX
FALLBACK_2 = "google/gemma-4-31b-it:free"  # GOOD live — Arabic + LaTeX
FALLBACK_3 = "nvidia/nemotron-3-nano-30b-a3b:free"  # fast; guarded by content==0
FALLBACK_4 = "openai/gpt-oss-120b:free"  # 404 free tier — auto-recovery slot
FALLBACK_5 = "nvidia/nemotron-nano-9b-v2:free"  # last resort; guarded (D-177: FIRST_TOKEN_TIMEOUT caps its 62s-empty hang; nemotron-3-super-120b stays BANNED per ISS-107 — English-in-content leak)

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
    "PRIMARY_MODEL",
    "PRIMARY_OVERRIDE_ENV",
    "resolve_primary_model",
]
