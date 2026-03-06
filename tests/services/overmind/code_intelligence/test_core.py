from unittest.mock import patch

import pytest

from microservices.orchestrator_service.src.services.overmind.code_intelligence.core import StructuralCodeIntelligence


@pytest.fixture
def mock_repo_path(tmp_path):
    d = tmp_path / "repo"
    d.mkdir()
    (d / "main.py").write_text("print('hello')")
    return d


def test_analyze_project_structure(mock_repo_path):
    # Setup
    target_paths = ["."]
    print(f"DEBUG: repo_path={mock_repo_path}")
    print(f"DEBUG: files in repo={[f.name for f in mock_repo_path.iterdir()]}")
    service = StructuralCodeIntelligence(repo_path=mock_repo_path, target_paths=target_paths)
    service.exclude_patterns = []  # Disable exclusions as tmp_path likely contains 'test_'

    # Mock GitAnalyzer to avoid real git commands
    with patch.object(service, "git_analyzer") as mock_git:
        mock_git.analyze_file_history.return_value = {
            "total_commits": 1,
            "commits_last_6months": 1,
            "commits_last_12months": 1,
            "num_authors": 1,
            "bugfix_commits": 0,
            "branches_modified": ["main"],
        }

        # Act
        result = service.analyze_project()

        # Assert
        assert result is not None
        assert result.total_files >= 1
        assert len(result.files) >= 1
        assert result.files[0].file_path.endswith("main.py")
