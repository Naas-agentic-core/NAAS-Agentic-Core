"""
Domain tools for project metrics and file system statistics.
"""

import asyncio
import os
import subprocess
from pathlib import Path

from app.services.agent_tools.tool_model import Tool, ToolConfig
from app.services.overmind.planning.deep_indexer import build_index


def get_project_root() -> Path:
    """Get the project root directory."""
    return Path(os.getcwd())


def _count_files_sync(root_path: Path, extension: str | None = None) -> int:
    """Synchronous helper for counting files without blocking the main event loop."""
    count = 0
    # Common massive directories to exclude
    excluded_dirs = {".git", ".venv", "venv", "node_modules", "__pycache__", "site-packages"}
    for _root, dirs, filenames in os.walk(root_path):
        # Prune excluded directories
        dirs[:] = [d for d in dirs if d not in excluded_dirs]
        for f in filenames:
            if extension and not f.endswith(extension):
                continue
            count += 1
    return count


async def count_files_handler(
    directory: str = ".", extension: str | None = None
) -> dict[str, object]:
    """
    Count files in a directory, optionally filtering by extension.
    Respects .gitignore if possible (using git ls-files if available).
    """
    try:
        # Use asyncio.create_subprocess_exec to avoid blocking the event loop
        process = await asyncio.create_subprocess_exec(
            "git", "ls-files", stdout=subprocess.PIPE, stderr=subprocess.PIPE
        )
        stdout, _ = await process.communicate()

        if process.returncode != 0:
            raise subprocess.CalledProcessError(process.returncode, "git ls-files")

        files = stdout.decode().splitlines()

        if extension:
            files = [f for f in files if f.endswith(extension)]

        if directory != ".":
            files = [f for f in files if f.startswith(directory)]

        count = len(files)
    except (subprocess.CalledProcessError, FileNotFoundError):
        # Fallback to os.walk, running in a thread to prevent blocking the event loop
        root_path = get_project_root() / directory
        loop = asyncio.get_running_loop()
        count = await loop.run_in_executor(None, _count_files_sync, root_path, extension)

    return {"directory": directory, "extension": extension, "count": count}


async def get_project_metrics_handler() -> dict[str, object]:
    """Read PROJECT_METRICS.md and supplement with live data using Deep Indexer."""
    metrics = {}
    metrics_file = get_project_root() / "PROJECT_METRICS.md"

    if metrics_file.exists():
        content = metrics_file.read_text()
        metrics["source"] = "PROJECT_METRICS.md"
        metrics["content"] = content
    else:
        metrics["source"] = "calculated"
        metrics["content"] = "Metrics file not found. Calculating live..."

    # Use Deep Indexer for robust counting (includes JS/TS/etc)
    try:
        loop = asyncio.get_running_loop()
        # Run synchronous build_index in a thread to avoid blocking the loop
        analysis = await loop.run_in_executor(None, build_index, ".")

        # Calculate language breakdown
        js_ts_count = sum(
            1 for f in analysis.files if f.file_path.endswith((".js", ".jsx", ".ts", ".tsx"))
        )
        py_count = sum(1 for f in analysis.files if f.file_path.endswith(".py"))

        metrics["live_stats"] = {
            "total_files": analysis.total_files,
            "python_files": py_count,
            "js_ts_files": js_ts_count,
            "total_lines": analysis.total_lines,
            "code_lines": analysis.total_code_lines,
            "avg_complexity": analysis.avg_file_complexity,
        }

    except Exception as e:
        # Fallback to simple counter if deep indexer fails
        py_count = (await count_files_handler(".", ".py"))["count"]
        total_count = (await count_files_handler("."))["count"]
        metrics["live_stats"] = {
            "python_files": py_count,
            "total_files": total_count,
            "error": f"Deep Indexer failed: {e!s}",
        }

    return metrics


class ProjectMetricsTool(Tool):
    """Tool to retrieve project metrics."""

    def __init__(self):
        config = ToolConfig(
            name="get_project_metrics",
            description="Retrieves project metrics including test coverage and file counts.",
            category="metrics",
            capabilities=["read_file", "shell_exec"],
            aliases=["metrics", "stats"],
            handler=get_project_metrics_handler,
        )
        super().__init__(config)


class FileCountTool(Tool):
    """Tool to count files."""

    def __init__(self):
        config = ToolConfig(
            name="count_files",
            description="Counts files in the project or a directory.",
            category="fs",
            aliases=["file_count"],
            handler=count_files_handler,
        )
        super().__init__(config)
