from unittest.mock import patch

import pytest

from app.services.agent_tools.domain.context import ContextAwarenessTool, context_awareness_handler
from app.services.agent_tools.domain.metrics import (
    FileCountTool,
    ProjectMetricsTool,
    count_files_handler,
    get_project_metrics_handler,
)


@pytest.fixture
def mock_asyncio_create_subprocess_exec():
    with patch("asyncio.create_subprocess_exec") as mock:
        yield mock


@pytest.fixture
def mock_os_walk():
    with patch("os.walk") as mock:
        yield mock


@pytest.mark.asyncio
async def test_count_files_handler_git(mock_asyncio_create_subprocess_exec):
    """Test counting files using git ls-files."""
    from unittest.mock import AsyncMock

    mock_process = AsyncMock()
    mock_process.communicate.return_value = (b"file1.py\nfile2.py\nfile3.txt", b"")
    mock_process.returncode = 0
    mock_asyncio_create_subprocess_exec.return_value = mock_process

    # Test all files
    result = await count_files_handler()
    assert result["count"] == 3
    assert result["directory"] == "."

    # Test extension filtering
    result_py = await count_files_handler(extension=".py")
    assert result_py["count"] == 2
    assert result_py["extension"] == ".py"

    # Test directory filtering
    # When directory=".", the handler doesn't filter by startswith, effectively including all files
    result_dir = await count_files_handler(directory=".")
    assert result_dir["count"] == 3


@pytest.mark.asyncio
async def test_count_files_handler_fallback(mock_asyncio_create_subprocess_exec, mock_os_walk):
    """Test fallback to os.walk when git fails."""
    from unittest.mock import AsyncMock

    mock_process = AsyncMock()
    mock_process.communicate.return_value = (b"", b"")
    mock_process.returncode = 1
    mock_asyncio_create_subprocess_exec.return_value = mock_process

    # Mock os.walk structure: (root, dirs, files)
    mock_os_walk.return_value = [(".", [], ["file1.py", "file2.py", "file3.txt"])]

    result = await count_files_handler()
    assert result["count"] == 3

    # Test extension filtering in fallback
    result_py = await count_files_handler(extension=".py")
    assert result_py["count"] == 2


@pytest.mark.asyncio
async def test_get_project_metrics_handler(mock_asyncio_create_subprocess_exec):
    """Test retrieving project metrics."""
    from unittest.mock import AsyncMock

    mock_process = AsyncMock()
    mock_process.communicate.return_value = (b"file1.py\nfile2.py\nfile3.txt", b"")
    mock_process.returncode = 0
    mock_asyncio_create_subprocess_exec.return_value = mock_process

    # Mock the return value of build_index to match the expected test data
    from app.services.overmind.code_intelligence.models import (
        FileMetrics,
        ProjectAnalysis,
    )

    mock_analysis = ProjectAnalysis(
        timestamp="2024-01-01 00:00:00",
        files=[
            FileMetrics(
                file_path="file1.py",
                relative_path="file1.py",
                total_lines=10,
                code_lines=5,
                comment_lines=2,
                blank_lines=3,
                file_complexity=1,
            ),
            FileMetrics(
                file_path="file2.py",
                relative_path="file2.py",
                total_lines=10,
                code_lines=5,
                comment_lines=2,
                blank_lines=3,
                file_complexity=1,
            ),
            FileMetrics(
                file_path="file3.txt",
                relative_path="file3.txt",
                total_lines=10,
                code_lines=0,
                comment_lines=0,
                blank_lines=0,
                file_complexity=0,
            ),
        ],
        total_files=3,
        total_lines=30,
        total_code_lines=10,
        total_functions=5,
        total_classes=2,
        avg_file_complexity=1.0,
        max_file_complexity=1,
    )

    with patch("pathlib.Path.read_text", return_value="# Metrics"):
        with patch("pathlib.Path.exists", return_value=True):
            with patch(
                "app.services.agent_tools.domain.metrics.build_index", return_value=mock_analysis
            ):
                metrics = await get_project_metrics_handler()

                assert metrics["source"] == "PROJECT_METRICS.md"
                assert metrics["content"] == "# Metrics"
                assert metrics["live_stats"]["python_files"] == 2
                assert metrics["live_stats"]["total_files"] == 3


@pytest.mark.asyncio
async def test_context_awareness_handler():
    """Test context awareness extraction."""
    # Test with direct kwargs (legacy)
    result = await context_awareness_handler(active_file="main.py", cursor_line=10)
    assert result["active_file"] == "main.py"
    assert result["cursor_line"] == 10

    # Test with metadata dict
    metadata = {"active_file": "test.py", "cursor_line": 5, "selection": "code"}
    result_meta = await context_awareness_handler(metadata=metadata)
    assert result_meta["active_file"] == "test.py"
    assert result_meta["cursor_line"] == 5
    assert result_meta["selection"] == "code"

    # Test missing context
    result_empty = await context_awareness_handler()
    assert "error" in result_empty


@pytest.mark.asyncio
async def test_tool_classes():
    """Verify tool classes are correctly initialized."""
    metrics_tool = ProjectMetricsTool()
    assert metrics_tool.name == "get_project_metrics"

    file_count_tool = FileCountTool()
    assert file_count_tool.name == "count_files"

    context_tool = ContextAwarenessTool()
    assert context_tool.name == "get_active_context"
