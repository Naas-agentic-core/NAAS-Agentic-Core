"""قدرة ذكاء الملفات الإدارية بعقود صريحة وسلوك متوافق خلف واجهات التوافق."""

from __future__ import annotations

import re
from pathlib import Path

from pydantic import Field

from app.core.schemas import RobustBaseModel


class FileIntelligenceRequest(RobustBaseModel):
    """طلب قدرة عدّ الملفات بشكل صريح."""

    question: str = Field(..., min_length=1)


class FileIntelligenceDecision(RobustBaseModel):
    """قرار التعرف على النية وتحديد الامتداد المطلوب إن وجد."""

    recognized: bool
    extension: str | None = None


class FileIntelligenceResult(RobustBaseModel):
    """نتيجة القدرة بصيغة آمنة ومتوافقة مع استهلاك الواجهات الحالية."""

    success: bool
    message: str | None = None
    extension: str | None = None
    count: int | None = None


_SUPPORTED_EXTENSIONS: tuple[str, ...] = (
    "py",
    "js",
    "ts",
    "tsx",
    "jsx",
    "json",
    "md",
    "txt",
    "pdf",
    "csv",
    "yaml",
    "yml",
    "sql",
)


def _is_python_question(normalized: str) -> bool:
    indicators = (
        "كم عدد ملفات بايثون",
        "عدد ملفات بايثون",
        "python files",
        "how many python files",
    )
    return any(indicator in normalized for indicator in indicators)


def _is_shell_style_question(normalized: str) -> bool:
    count_intents = ("كم عدد", "عدد الملفات", "احسب عدد", "count", "how many", "wc -l")
    shell_hints = ("shell", "find", "*.py", "python", "بايثون")
    return any(intent in normalized for intent in count_intents) and any(
        hint in normalized for hint in shell_hints
    )


def _is_generic_count_question(normalized: str) -> bool:
    count_intents = ("كم عدد", "عدد الملفات", "احسب عدد", "count", "how many")
    file_hints = ("ملف", "ملفات", "files", "file")
    return any(intent in normalized for intent in count_intents) and any(
        hint in normalized for hint in file_hints
    )


def _extract_extension(normalized: str) -> str | None:
    if _is_python_question(normalized):
        return "py"

    aliases = {
        "python": "py",
        "بايثون": "py",
        "جافاسكريبت": "js",
        "typescript": "ts",
        "markdown": "md",
        "text": "txt",
    }
    for alias, extension in aliases.items():
        if alias in normalized:
            return extension

    explicit_candidates = re.findall(r"(?:\*\.)?([a-z0-9]{1,8})\b", normalized)
    for candidate in explicit_candidates:
        extension = candidate.lstrip(".")
        if extension in _SUPPORTED_EXTENSIONS:
            return extension
    return None


def detect_file_intelligence(request: FileIntelligenceRequest) -> FileIntelligenceDecision:
    """يحدد ما إذا كان السؤال يخص عدّ الملفات ويستنتج الامتداد المطلوب."""
    normalized = request.question.strip().lower()
    recognized = (
        _is_python_question(normalized)
        or _is_shell_style_question(normalized)
        or _is_generic_count_question(normalized)
    )
    if not recognized:
        return FileIntelligenceDecision(recognized=False)
    return FileIntelligenceDecision(recognized=True, extension=_extract_extension(normalized))


def build_file_count_command(extension: str | None = None) -> str:
    """يبني أمرًا موحدًا وآمنًا لعدّ الملفات مع استبعاد المسارات الثقيلة."""
    extension_filter = f" -name '*.{extension}'" if extension else ""
    return (
        "find . "
        "\\( -path './.git' -o -path './.venv' -o -path './venv' -o "
        "-path './node_modules' -o -path '*/__pycache__' -o "
        "-path '*/.pytest_cache' -o -path '*/.mypy_cache' \\) -prune -o "
        f"-type f{extension_filter} -print | wc -l"
    )


def default_project_root() -> str:
    """يعيد جذر المشروع الافتراضي المستخدم في حساب الملفات."""
    return str(Path(__file__).resolve().parents[3])


def render_compatible_message(extension: str | None, count: int) -> str:
    """ينتج رسالة متوافقة مع السلوك التاريخي مع إضافات غير كاسرة."""
    if extension is None:
        return f"عدد الملفات في المشروع هو: {count} ملف."
    if extension == "py":
        return f"عدد ملفات بايثون في المشروع هو: {count} ملف."
    return f"عدد الملفات بامتداد .{extension} في المشروع هو: {count} ملف."


def make_result(*, extension: str | None, count: int | None) -> FileIntelligenceResult:
    """يبني نتيجة القدرة بشكل محدد وقابل للاختبار."""
    if count is None:
        return FileIntelligenceResult(success=False, extension=extension)
    return FileIntelligenceResult(
        success=True,
        extension=extension,
        count=count,
        message=render_compatible_message(extension, count),
    )
