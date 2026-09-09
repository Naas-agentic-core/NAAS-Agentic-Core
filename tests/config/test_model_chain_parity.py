"""D-013 (machine-enforced): both brains' model chains equal the canonical shared chain.

Mirrors `scripts/fitness/check_model_chain_parity.py` as a pytest so the split-brain
model-chain invariant is enforced in the normal test run too. Pure stdlib + the
dep-free `shared.ai_models.model_chain` module — no app/microservice imports.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

from shared.ai_models.model_chain import MODEL_CHAIN

_REPO_ROOT = Path(__file__).resolve().parents[2]
_GATE_PATH = _REPO_ROOT / "scripts" / "fitness" / "check_model_chain_parity.py"


def _load_gate():
    spec = importlib.util.spec_from_file_location("check_model_chain_parity", _GATE_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_canonical_chain_is_the_verified_primary_first():
    # D-167: PRIMARY must be the verified gpt-oss-20b; 120b stays as tail recovery slot.
    assert MODEL_CHAIN[0] == "openai/gpt-oss-20b:free"
    assert "openai/gpt-oss-120b:free" in MODEL_CHAIN[1:]
    # No reasoning-only / dead models proven catastrophic live (D-067/ISS-107).
    joined = " ".join(MODEL_CHAIN)
    assert "reasoning:free" not in joined
    assert "inclusionai" not in joined


def test_both_brains_match_canonical_chain():
    gate = _load_gate()
    for _label, rel_path in gate.BRAINS:
        chain = gate.resolve_chain_from_source(rel_path)
        assert chain == list(MODEL_CHAIN), f"{rel_path} drifted from canonical model chain"


def test_gate_main_passes():
    gate = _load_gate()
    # Pass an explicit empty argv so pytest's own sys.argv doesn't reach argparse.
    assert gate.main([]) == 0
