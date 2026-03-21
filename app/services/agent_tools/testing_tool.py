"""
أداة تشغيل الاختبارات.
======================

توفر إمكانية تشغيل pytest بشكل آمن.

المعايير:
- CS50 2025: توثيق عربي، صرامة في الأنواع
"""

import asyncio
import logging
import os
import subprocess
from pathlib import Path

logger = logging.getLogger(__name__)


async def run_tests(
    path: str = "",
    options: str = "",
    cwd: str | None = None,
    timeout: int = 120,
) -> dict[str, object]:
    """
    تشغيل اختبارات pytest.

    Args:
        path: مسار الاختبارات (ملف أو مجلد)
        options: خيارات إضافية (مثلاً -v, -x, -k)
        cwd: مسار العمل
        timeout: المهلة الزمنية (دقيقتان بالافتراض)

    Returns:
        dict: {success, stdout, stderr, return_code, passed, failed, error}
    """
    logger.info(f"Tests: Running pytest {path} {options}")

    # تحديد مسار العمل
    work_dir = Path(cwd) if cwd else Path.cwd()
    if not work_dir.exists():
        return {
            "success": False,
            "stdout": "",
            "stderr": "",
            "return_code": -1,
            "passed": 0,
            "failed": 0,
            "error": f"Directory does not exist: {work_dir}",
        }

    # بناء الأمر
    command = "python -m pytest"
    if path:
        command += f" {path}"
    if options:
        command += f" {options}"
    # إضافة خيارات افتراضية
    if "-v" not in options:
        command += " -v"
    command += " --tb=short"

    try:
        return await asyncio.wait_for(
            _run_pytest(command, work_dir),
            timeout=timeout,
        )

    except TimeoutError:
        logger.warning(f"Tests: Timed out after {timeout}s")
        return {
            "success": False,
            "stdout": "",
            "stderr": "",
            "return_code": -1,
            "passed": 0,
            "failed": 0,
            "error": f"Tests timed out after {timeout} seconds",
        }

    except Exception as e:
        logger.error(f"Tests: Unexpected error: {e}")
        return {
            "success": False,
            "stdout": "",
            "stderr": "",
            "return_code": -1,
            "passed": 0,
            "failed": 0,
            "error": str(e),
        }


async def _run_pytest(command: str, cwd: Path) -> dict[str, object]:
    """
    تشغيل pytest.
    """
    loop = asyncio.get_running_loop()

    def _execute():
        process = subprocess.run(
            command,
            shell=True,
            check=False,
            cwd=str(cwd),
            capture_output=True,
            text=True,
            timeout=180,  # حد داخلي 3 دقائق
            env={**os.environ, "PYTHONIOENCODING": "utf-8"},
        )

        stdout = process.stdout[:20000]  # حد 20KB
        stderr = process.stderr[:5000]

        # استخراج عدد الاختبارات
        passed = 0
        failed = 0
        try:
            # البحث عن نمط مثل "5 passed, 2 failed"
            import re

            match = re.search(r"(\d+) passed", stdout)
            if match:
                passed = int(match.group(1))
            match = re.search(r"(\d+) failed", stdout)
            if match:
                failed = int(match.group(1))
        except Exception:
            pass

        return {
            "success": process.returncode == 0,
            "stdout": stdout,
            "stderr": stderr,
            "return_code": process.returncode,
            "passed": passed,
            "failed": failed,
            "error": None if process.returncode == 0 else f"Tests failed: {failed} failures",
        }

    return await loop.run_in_executor(None, _execute)


async def run_specific_test(test_name: str, cwd: str | None = None) -> dict[str, object]:
    """تشغيل اختبار محدد بالاسم."""
    return await run_tests(options=f"-k '{test_name}'", cwd=cwd)


async def run_tests_verbose(path: str = "", cwd: str | None = None) -> dict[str, object]:
    """تشغيل الاختبارات مع مخرجات مفصلة."""
    return await run_tests(path=path, options="-vv --tb=long", cwd=cwd)


# تسجيل الأدوات
def register_test_tools(registry: dict) -> None:
    """
    تسجيل أدوات الاختبار في سجل الأدوات.
    """
    registry["run_tests"] = run_tests
    registry["pytest"] = run_tests
    registry["test"] = run_tests
    registry["run_specific_test"] = run_specific_test
    registry["run_tests_verbose"] = run_tests_verbose
    logger.info("Test tools registered successfully")
