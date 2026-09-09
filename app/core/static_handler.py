"""
معالج الملفات الثابتة (Static File Handler) - DEPRECATED.

⚠️ هذا الملف DEPRECATED وسيتم حذفه في الإصدار القادم.
⚠️ استخدم app.middleware.static_files_middleware بدلاً منه.

السبب: API-First Architecture
- تم فصل static file serving عن API core
- الآن static files اختياري ومنفصل تماماً
- يمكن تشغيل API بدون frontend

Migration:
```python
# القديم (Deprecated)
from app.core.static_handler import setup_static_files
setup_static_files(app)

# الجديد (Recommended)
from app.middleware.static_files_middleware import (
    StaticFilesConfig,
    setup_static_files_middleware
)
config = StaticFilesConfig(enabled=True)
setup_static_files_middleware(app, config)
```

يتولى مسؤولية تقديم ملفات الواجهة الأمامية (Frontend) والتعامل مع توجيه SPA (Single Page Application).
يطبق مبادئ CS50 (التوثيق) و SICP (فصل الاهتمامات).

المعايير (Standards):
- Strict Types: استخدام الأنواع الصارمة.
- Arabic Docs: توثيق عربي كامل.
- Security: منع تجاوز المسار (Path Traversal).
"""

import logging
import os
from typing import Final

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

logger = logging.getLogger(__name__)

# المجلدات المسموح بتقديمها مباشرة
MOUNTABLE_FOLDERS: Final[list[str]] = ["css", "js", "src", "assets"]
DEFAULT_STATIC_DIR: Final[str] = os.path.join(os.getcwd(), "app/static")


# NOTE: This function is DEPRECATED. Use app.middleware.static_files_middleware instead.
def setup_static_files(app: FastAPI, static_dir: str | None = None) -> None:
    """
    إعداد خدمة الملفات الثابتة واستراتيجية الرد (Fallback) لتطبيقات الصفحة الواحدة.
    Setup static files serving and SPA fallback strategy.

    Args:
        app: تطبيق FastAPI
        static_dir: مسار مجلد الملفات الثابتة (اختياري)
    """
    # 1. تحديد وتحقق من مسار الملفات | Determine and validate path
    base_static_dir = static_dir or DEFAULT_STATIC_DIR

    if not _validate_static_directory(base_static_dir):
        return

    logger.info(f"📂 Mounting static files from: {base_static_dir}")

    # 2. ربط المجلدات المحددة | Mount specific folders
    _mount_static_folders(app, base_static_dir)

    # 3. خدمة الصفحة الرئيسية | Serve root index
    _setup_root_route(app, base_static_dir)

    # 4. معالج SPA Fallback | Setup SPA fallback handler
    _setup_spa_fallback(app, base_static_dir)


async def serve_static(
    request: Request, file_path: str, static_dir: str | None = None
) -> Response | None:
    """
    Serve static file with proper headers and caching.

    يخدم ملف ثابت مع الترويسات والتخزين المؤقت المناسب.

    Args:
        request: Request object طلب HTTP
        file_path: Relative path to the file مسار الملف النسبي
        static_dir: Optional override for static directory.

    Returns:
        Response | None: FileResponse if found, else None

    Raises:
        HTTPException: For path traversal (404) or invalid method (405).
    """
    base_static_dir = static_dir or DEFAULT_STATIC_DIR

    full_path = os.path.join(base_static_dir, file_path)
    full_path = os.path.normpath(full_path)

    # Security: Path Traversal Check
    if not full_path.startswith(base_static_dir):
        raise HTTPException(status_code=404, detail="Not Found")

    if not os.path.exists(full_path):
        return None

    if not os.path.isfile(full_path):
        return None

    # Check method
    if request.method not in ["GET", "HEAD"]:
        raise HTTPException(status_code=405, detail="Method Not Allowed")

    return FileResponse(full_path)


def _validate_static_directory(directory: str) -> bool:
    """
    التحقق من وجود مجلد الملفات الثابتة.
    Validate static directory exists.

    Returns:
        bool: True إذا كان المجلد موجوداً
    """
    if not os.path.exists(directory):
        logger.warning(
            f"⚠️ Static files directory not found: {directory}. Frontend will not be served."
        )
        return False
    return True


def _mount_static_folders(app: FastAPI, base_static_dir: str) -> None:
    """
    ربط المجلدات الفرعية المحددة.
    Mount specific static subfolders (css, js, etc.).
    """
    for folder in MOUNTABLE_FOLDERS:
        folder_path = os.path.join(base_static_dir, folder)
        if os.path.isdir(folder_path):
            app.mount(f"/{folder}", StaticFiles(directory=folder_path), name=folder)


def _setup_root_route(app: FastAPI, base_static_dir: str) -> None:
    """
    إعداد مسار الجذر لخدمة index.html.
    Setup root route to serve index.html.
    """

    async def serve_root() -> FileResponse:
        """يخدم ملف index.html عند طلب الجذر."""
        return FileResponse(os.path.join(base_static_dir, "index.html"))

    app.add_api_route("/", serve_root, methods=["GET", "HEAD"])


def _setup_spa_fallback(app: FastAPI, base_static_dir: str) -> None:
    """
    إعداد معالج SPA Fallback.
    Setup SPA fallback handler for client-side routing.
    """

    async def spa_fallback(request: Request, full_path: str) -> FileResponse:
        """
        معالج المسارات غير الموجودة.
        Handle non-existent paths with SPA fallback logic.
        """
        # 1. التحقق من ملف فعلي | Check for physical file
        physical_response = await serve_static(request, full_path, static_dir=base_static_dir)
        if physical_response:
            return physical_response  # type: ignore

        # 2. حماية مسارات API | Protect API routes
        if _is_api_route(full_path):
            raise HTTPException(status_code=404, detail="Not Found")

        # 3. التحقق من الطريقة | Validate HTTP method
        if request.method not in ["GET", "HEAD"]:
            raise HTTPException(status_code=404, detail="Not Found")

        # 4. التوجيه إلى SPA | Fallback to SPA
        return FileResponse(os.path.join(base_static_dir, "index.html"))

    app.add_api_route(
        "/{full_path:path}",
        spa_fallback,
        methods=["GET", "HEAD", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"],
    )


def _is_api_route(path: str) -> bool:
    """
    التحقق من كون المسار مسار API.
    Check if path is an API route.
    """
    return path.startswith("api") or "/api/" in path or path.endswith("/api")
