"""يتحقق من جاهزية بوابة التتبع عبر الربط البنيوي وتنفيذ اختبار المواصفة الفعلي."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
GATEWAY_MAIN = REPO_ROOT / "microservices/api_gateway/main.py"
GATEWAY_MIDDLEWARE = REPO_ROOT / "microservices/api_gateway/middleware.py"
TRACE_TEST = REPO_ROOT / "tests/api_gateway/test_trace_propagation.py"


def _contains_token(path: Path, token: str) -> bool:
    """يتأكد من احتواء الملف على رمز نصي مطلوب لتأكيد عقد التتبع."""
    return token in path.read_text(encoding="utf-8")


def _run_pytest_trace_contract() -> bool:
    """يشغّل اختبار تمرير التتبع الحقيقي ويعيد نجاحه كقيمة منطقية."""
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", str(TRACE_TEST)],
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        env={**os.environ, "SKIP_DB_FIXTURES": "1"},
        text=True,
    )
    if result.returncode != 0:
        print("❌ Trace propagation pytest contract failed.")
        print(result.stdout.strip())
        print(result.stderr.strip())
        return False
    return True


def main() -> int:
    """ينفذ حارس التتبع ويرجع 0 عند توافق الشروط و1 عند وجود نقص."""
    if not TRACE_TEST.exists():
        print("❌ Missing trace propagation test file.")
        return 1

    if not _contains_token(GATEWAY_MAIN, "TraceContextMiddleware"):
        print("❌ Gateway main is missing TraceContextMiddleware wiring.")
        return 1

    required_tokens = ["traceparent", "class TraceContextMiddleware"]
    for token in required_tokens:
        if not _contains_token(GATEWAY_MIDDLEWARE, token):
            print(f"❌ Gateway middleware is missing required tracing token: {token}")
            return 1

    if not _run_pytest_trace_contract():
        return 1

    print("✅ Tracing gate passed: wiring + runtime contract test are valid.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
