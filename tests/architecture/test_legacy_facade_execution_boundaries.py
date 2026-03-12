"""اختبارات تمنع إدخال منطق تنفيذي داخل legacy façades."""

from __future__ import annotations

from pathlib import Path

LEGACY_FACADE_FILES = [
    Path("app/api/routers/admin.py"),
    Path("app/api/routers/customer_chat.py"),
    Path("app/api/routers/content.py"),
]

FORBIDDEN_TOKENS = (
    "execute_shell(",
    "search_educational_content(",
    "_build_file_count_command(",
    "_count_files_in_project(",
)


def test_legacy_facades_do_not_embed_execution_logic_tokens() -> None:
    """يفرض بقاء واجهات legacy ضمن التطبيع والتفويض فقط."""
    for file_path in LEGACY_FACADE_FILES:
        content = file_path.read_text(encoding="utf-8")
        for token in FORBIDDEN_TOKENS:
            assert token not in content, f"Forbidden execution token {token} in {file_path}"
