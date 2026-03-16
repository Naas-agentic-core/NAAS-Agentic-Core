"""اختبارات عقود المسارات الحرجة لضمان التوافق الخلفي أثناء التفكيك التدريجي."""

from __future__ import annotations

from fastapi import FastAPI


def _collect_route_paths(app: FastAPI) -> set[str]:
    """يجمع جميع مسارات HTTP المعرفة داخل التطبيق لاستخدامها في اختبارات العقود."""
    return {getattr(route, "path", "") for route in app.routes}


def test_login_route_contract_exists(test_app: FastAPI) -> None:
    """يضمن استمرار نقطة تسجيل الدخول دون تغيير مسارها أثناء الهجرة."""
    routes = _collect_route_paths(test_app)
    assert "/api/security/login" in routes


def test_admin_python_count_contract_exists(test_app: FastAPI) -> None:
    """يثبّت عقد واجهة عدّ المستخدمين الإدارية كبديل توافقي لمسار عدّ الإدارة."""
    routes = _collect_route_paths(test_app)
    assert "/admin/users/count" in routes


def test_exercise_retrieval_contract_exists(test_app: FastAPI) -> None:
    """يحافظ على نقطة استرجاع محتوى التمارين عبر واجهة المحتوى الرسمية."""
    routes = _collect_route_paths(test_app)
    assert "/v1/content/search" in routes
