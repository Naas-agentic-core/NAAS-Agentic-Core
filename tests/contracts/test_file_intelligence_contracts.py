"""اختبارات عقود قدرة ذكاء الملفات لضمان الثبات ومنع الانجراف."""

from __future__ import annotations

from app.services.capabilities.file_intelligence import (
    FileIntelligenceRequest,
    build_file_count_command,
    detect_file_intelligence,
    make_result,
)


def test_detect_file_intelligence_python_request() -> None:
    """يتعرف على طلبات Python مع امتداد واضح."""
    decision = detect_file_intelligence(FileIntelligenceRequest(question="كم عدد ملفات بايثون؟"))
    assert decision.recognized is True
    assert decision.extension == "py"


def test_detect_file_intelligence_generic_request() -> None:
    """يدعم الطلبات العامة مع امتداد addtive مثل CSV."""
    decision = detect_file_intelligence(FileIntelligenceRequest(question="count csv files"))
    assert decision.recognized is True
    assert decision.extension == "csv"


def test_make_result_preserves_python_legacy_message() -> None:
    """يحافظ على الرسالة التاريخية لمسار Python دون كسر."""
    result = make_result(extension="py", count=12)
    assert result.success is True
    assert result.message == "عدد ملفات بايثون في المشروع هو: 12 ملف."


def test_make_result_handles_unsupported_or_failure_safely() -> None:
    """لا يعطي نجاحًا كاذبًا عندما يفشل العدّ."""
    result = make_result(extension="xlsx", count=None)
    assert result.success is False
    assert result.message is None


def test_build_file_count_command_includes_extension_filter() -> None:
    """يتأكد من بناء أمر deterministic للامتداد المطلوب."""
    command = build_file_count_command("json")
    assert "*.json" in command
