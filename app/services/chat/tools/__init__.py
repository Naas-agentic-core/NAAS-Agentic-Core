"""
سجل الأدوات المتاحة للوكلاء.

يجمع أدوات الوصول إلى المعرفة والمشروع بشكل منضبط وفق فلسفة API First.
"""

from collections.abc import Callable
from pathlib import Path

from app.core.logging import get_logger

# Avoid importing specific tools at module level to prevent circular imports

logger = get_logger("tool-registry")


class ToolRegistry:
    """
    سجل الأدوات المتاحة للوكلاء.
    يضمن عدم استخدام أدوات غير مسجلة.
    """

    def __init__(self) -> None:
        self._tools: dict[str, Callable] = {}
        self._register_defaults()

    def _register_defaults(self) -> None:
        # Avoid circular imports by importing locally
        from app.services.chat.tools.content import (
            get_content_raw,
            get_curriculum_structure,
            get_solution_raw,
            search_content,
        )
        from app.services.chat.tools.curriculum import (
            adjust_difficulty_level,
            get_learning_path_progress,
            recommend_next_mission,
        )
        from app.services.chat.tools.reporting import (
            analyze_learning_curve,
            fetch_comprehensive_student_history,
            get_student_diagnostic_report,
        )
        from app.services.chat.tools.retrieval import search_educational_content

        # Admin / Core Tools
        self.register("search_codebase", self._search_codebase)
        self.register("find_symbol", self._find_symbol)
        self.register("find_route", self._find_route)
        self.register("read_file_snippet", self._read_file_snippet)

        # Educational / Student Tools
        self.register("get_student_diagnostic_report", get_student_diagnostic_report)
        self.register("fetch_comprehensive_student_history", fetch_comprehensive_student_history)
        self.register("analyze_learning_curve", analyze_learning_curve)
        self.register("recommend_next_mission", recommend_next_mission)
        self.register("get_learning_path_progress", get_learning_path_progress)
        self.register("adjust_difficulty_level", adjust_difficulty_level)
        self.register("search_educational_content", search_educational_content)

        # New Content Tools
        self.register("get_curriculum_structure", get_curriculum_structure)
        self.register("search_content", search_content)
        self.register("get_content_raw", get_content_raw)
        self.register("get_solution_raw", get_solution_raw)

    def register(self, name: str, func: Callable) -> None:
        self._tools[name] = func

    async def execute(self, tool_name: str, args: dict[str, object]) -> object:
        if tool_name not in self._tools:
            raise ValueError(f"Tool '{tool_name}' not found.")

        logger.info(
            "Executing tool: %s with %s",
            tool_name,
            self._redact_args(args),
        )
        return await self._tools[tool_name](**args)

    # --- Tool Implementations ---

    async def _search_codebase(self, query: str) -> list[dict[str, object]]:
        from app.services.codebase.introspection import introspection_service

        # Map to CodeSearchService
        results = introspection_service.search_text(query)
        return [r.model_dump() for r in results]

    async def _find_symbol(self, symbol: str) -> list[dict[str, object]]:
        from app.services.codebase.introspection import introspection_service

        results = introspection_service.find_symbol(symbol)
        return [r.model_dump() for r in results]

    async def _find_route(self, path_fragment: str) -> list[dict[str, object]]:
        from app.services.codebase.introspection import introspection_service

        results = introspection_service.find_route(path_fragment)
        return [r.model_dump() for r in results]

    async def _read_file_snippet(
        self,
        file_path: str,
        start_line: int,
        end_line: int | None = None,
        max_lines: int = 12,
    ) -> dict[str, object]:
        repo_root = Path.cwd().resolve()
        target_path = (repo_root / file_path).resolve()
        if repo_root not in target_path.parents and target_path != repo_root:
            raise ValueError("Invalid file path.")
        if not target_path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")

        if start_line < 1:
            raise ValueError("start_line must be >= 1.")

        raw_lines = target_path.read_text(encoding="utf-8", errors="ignore").splitlines()
        total_lines = len(raw_lines)
        start = max(start_line, 1)
        effective_end = end_line if end_line is not None else start
        effective_end = max(effective_end, start)
        effective_end = min(effective_end, start + max_lines - 1, total_lines)
        snippet = raw_lines[start - 1 : effective_end]

        return {
            "file_path": str(target_path.relative_to(repo_root)),
            "start_line": start,
            "end_line": effective_end,
            "lines": snippet,
            "total_lines": total_lines,
        }

    @staticmethod
    def _redact_args(args: dict[str, object]) -> dict[str, object]:
        """
        إخفاء القيم الحساسة قبل التسجيل في السجلات.
        """
        redacted: dict[str, object] = {}
        for key, value in args.items():
            lowered = key.lower()
            if any(token in lowered for token in ("password", "token", "secret", "key")):
                redacted[key] = "***"
            else:
                redacted[key] = value
        return redacted
