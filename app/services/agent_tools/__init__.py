"""
Hyper-Unified Agent Tool Registry
=================================
The Facade that exposes tools.
Refactored to minimize import side-effects and circular dependencies.
"""

from app.services.agent_tools.domain.context import ContextAwarenessTool
from app.services.agent_tools.domain.metrics import FileCountTool, ProjectMetricsTool
from app.services.agent_tools.registry import get_tool_registry

# We keep legacy imports BUT we must ensure they don't trigger cycles.
# If `cognitive_tools` causes a cycle, we might need to lazy import it.
# For now, we assume the cleanup of `common_imports` helps.
from .cognitive_tools import (
    generic_think,
    refine_text,
    summarize_text,
)
from .core import (
    canonicalize_tool_name,
    get_tool,
    get_tools_schema,
    has_tool,
    list_tools,
    resolve_tool_name,
)
from .definitions import (
    PROJECT_ROOT,
    ToolResult,
    __version__,
)
from .dispatch_tools import (
    dispatch_tool,
    introspect_tools,
)
from .fs_tools import (
    append_file,
    delete_file,
    ensure_directory,
    ensure_file,
    file_exists,
    list_dir,
    read_bulk_files,
    read_file,
    write_file,
    write_file_if_changed,
)
from .globals import (
    _ALIAS_INDEX,
    _CAPABILITIES,
    _LAYER_STATS,
    _TOOL_REGISTRY,
    _TOOL_STATS,
)
from .memory_tools import (
    memory_get,
    memory_put,
)
from .reasoning_tools import reason_deeply
from .search_tools import (
    code_index_project,
    code_search_lexical,
    code_search_semantic,
)
from .structural_tools import (
    analyze_path_semantics,
    reload_deep_struct_map,
)

# Bridge: Register OO Tools into Legacy Dictionary
_metrics_tool = ProjectMetricsTool()
_file_count_tool = FileCountTool()
_context_tool = ContextAwarenessTool()


async def _legacy_wrapper(tool, **kwargs):
    return await tool.execute(**kwargs)


# Register manually to avoid complex loop logic in global scope
_TOOL_REGISTRY[_metrics_tool.name] = lambda **k: _legacy_wrapper(_metrics_tool, **k)
_TOOL_REGISTRY[_file_count_tool.name] = lambda **k: _legacy_wrapper(_file_count_tool, **k)
_TOOL_REGISTRY[_context_tool.name] = lambda **k: _legacy_wrapper(_context_tool, **k)

# Also register in the OO registry
get_tool_registry().register(_metrics_tool)
get_tool_registry().register(_file_count_tool)
get_tool_registry().register(_context_tool)

# Register shell tool
from .shell_tool import execute_shell, register_shell_tool

register_shell_tool(_TOOL_REGISTRY)

# Register git tools
from .git_tool import register_git_tools

register_git_tools(_TOOL_REGISTRY)

# Register test tools
from .testing_tool import register_test_tools

register_test_tools(_TOOL_REGISTRY)

# Register FS tools
from .fs_tools import register_fs_tools

register_fs_tools(_TOOL_REGISTRY)


def get_registry() -> None:
    """
    Returns the legacy dict registry.
    Used by Overmind Factory.
    """
    return _TOOL_REGISTRY


# Aliases for explicit export
async def get_project_metrics_tool(**kwargs) -> None:
    return await _metrics_tool.execute(**kwargs)


async def count_files_tool(**kwargs) -> None:
    return await _file_count_tool.execute(**kwargs)


async def get_active_context_tool(**kwargs) -> None:
    return await _context_tool.execute(**kwargs)


# Legacy Aliases
def generic_think_tool(**kwargs) -> None:
    return generic_think(**kwargs)


def summarize_text_tool(**kwargs) -> None:
    return summarize_text(**kwargs)


def refine_text_tool(**kwargs) -> None:
    return refine_text(**kwargs)


def reason_deeply_tool(**kwargs) -> None:
    return reason_deeply(**kwargs)


def write_file_tool(**kwargs) -> None:
    return write_file(**kwargs)


def write_file_if_changed_tool(**kwargs) -> None:
    return write_file_if_changed(**kwargs)


def append_file_tool(**kwargs) -> None:
    return append_file(**kwargs)


def read_file_tool(**kwargs) -> None:
    return read_file(**kwargs)


def file_exists_tool(**kwargs) -> None:
    return file_exists(**kwargs)


def list_dir_tool(**kwargs) -> None:
    return list_dir(**kwargs)


def delete_file_tool(**kwargs) -> None:
    return delete_file(**kwargs)


def ensure_file_tool(**kwargs) -> None:
    return ensure_file(**kwargs)


def ensure_directory_tool(**kwargs) -> None:
    return ensure_directory(**kwargs)


def introspect_tools_tool(**kwargs) -> None:
    return introspect_tools(**kwargs)


def memory_put_tool(**kwargs) -> None:
    return memory_put(**kwargs)


def memory_get_tool(**kwargs) -> None:
    return memory_get(**kwargs)


def dispatch_tool_tool(**kwargs) -> None:
    return dispatch_tool(**kwargs)


def analyze_path_semantics_tool(**kwargs) -> None:
    return analyze_path_semantics(**kwargs)


def reload_deep_struct_map_tool(**kwargs) -> None:
    return reload_deep_struct_map(**kwargs)


def read_bulk_files_tool(**kwargs) -> None:
    return read_bulk_files(**kwargs)


def code_index_project_tool(**kwargs) -> None:
    return code_index_project(**kwargs)


def code_search_lexical_tool(**kwargs) -> None:
    return code_search_lexical(**kwargs)


def code_search_semantic_tool(**kwargs) -> None:
    return code_search_semantic(**kwargs)


__all__ = [
    "PROJECT_ROOT",
    "_ALIAS_INDEX",
    "_CAPABILITIES",
    "_LAYER_STATS",
    "_TOOL_REGISTRY",
    "_TOOL_STATS",
    "ToolResult",
    "__version__",
    "analyze_path_semantics_tool",
    "append_file_tool",
    "canonicalize_tool_name",
    "code_index_project_tool",
    "code_search_lexical_tool",
    "code_search_semantic_tool",
    "count_files_tool",
    "delete_file_tool",
    "dispatch_tool_tool",
    "ensure_directory_tool",
    "ensure_file_tool",
    "execute_shell",
    "file_exists_tool",
    "generic_think_tool",
    "get_active_context_tool",
    "get_project_metrics_tool",
    "get_registry",
    "get_tool",
    "get_tool_registry",
    "get_tools_schema",
    "has_tool",
    "introspect_tools_tool",
    "list_dir_tool",
    "list_tools",
    "memory_get_tool",
    "memory_put_tool",
    "read_bulk_files_tool",
    "read_file_tool",
    "reason_deeply_tool",
    "refine_text_tool",
    "reload_deep_struct_map_tool",
    "resolve_tool_name",
    "summarize_text_tool",
    "write_file_if_changed_tool",
    "write_file_tool",
]
