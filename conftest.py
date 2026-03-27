"""جسر إعدادات الاختبار وتطبيق سياسات جودة نتائج الاختبارات على مستوى المستودع."""

from collections.abc import Sequence

from _pytest.config import Config
from _pytest.terminal import TerminalReporter

from tests.conftest import *  # noqa: F403


def _count_report_items(reporter: TerminalReporter, key: str) -> int:
    """تُعيد عدد العناصر المسجلة ضمن فئة معيّنة في تقرير pytest النهائي."""

    items: Sequence[object] = reporter.stats.get(key, ())
    return len(items)


def pytest_sessionfinish(session: object, exitstatus: int) -> None:
    """يفرض فشل جلسة الاختبار إذا وُجدت اختبارات متخطّاة أو تحذيرات."""

    del exitstatus
    config: Config | None = getattr(session, "config", None)
    if config is None:
        return

    reporter_obj: object | None = config.pluginmanager.getplugin("terminalreporter")
    if not isinstance(reporter_obj, TerminalReporter):
        return

    skipped_count = _count_report_items(reporter_obj, "skipped")
    warning_count = _count_report_items(reporter_obj, "warnings")
    if skipped_count == 0 and warning_count == 0:
        return

    reporter_obj.write_sep(
        "=",
        (
            "تم تفعيل سياسة الجودة الصارمة: "
            f"skipped={skipped_count}, warnings={warning_count}"
        ),
        red=True,
    )
    if hasattr(session, "exitstatus"):
        session.exitstatus = 1
