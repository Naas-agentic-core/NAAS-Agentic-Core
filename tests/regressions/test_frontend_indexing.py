from pathlib import Path
from unittest.mock import patch

import pytest

from microservices.orchestrator_service.src.services.overmind.planning.deep_indexer import build_index


def test_frontend_files_are_indexed() -> None:
    """
    Regression test for Admin File Counting Bug.
    Verifies that the build_index function includes the 'frontend' directory
    and successfully counts JS/TS files within it.
    """
    root_path = Path.cwd()
    frontend_path = root_path / "frontend"

    if not frontend_path.exists():
        pytest.skip("frontend directory not found")

    with patch(
        "microservices.orchestrator_service.src.services.overmind.code_intelligence.core.StructuralCodeIntelligence._enrich_with_git_metrics",
        return_value=None,
    ):
        analysis = build_index(".")

    frontend_files = [f for f in analysis.files if f.relative_path.startswith("frontend/")]

    assert len(frontend_files) > 0, (
        f"No frontend files found in analysis. Total files: {len(analysis.files)}. "
        f"Ensure 'frontend' is in target candidates."
    )

    next_config = next((f for f in frontend_files if "next.config.js" in f.relative_path), None)
    assert next_config is not None, "next.config.js not found in index"
