"""وسيط معالجة الأخطاء الموحّد."""

from __future__ import annotations

import logging

from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.types import ASGIApp

from app.middleware.core.base_middleware import BaseMiddleware
from app.middleware.core.context import RequestContext
from app.middleware.core.result import MiddlewareResult
from app.middleware.error_handling.exception_mapper import ExceptionMapper

logger = logging.getLogger(__name__)


class ErrorHandlerMiddleware(BaseMiddleware):
    """
    وسيط موحّد لمعالجة الأخطاء وتحويلها إلى استجابات HTTP منسّقة.

    يلتقط جميع الاستثناءات غير المعالجة ويعيدها كـ JSON منظّم.
    """

    def __init__(self, app: ASGIApp, debug: bool = False) -> None:
        super().__init__(app)
        self.debug = debug
        self._mapper = ExceptionMapper()

    async def process(self, context: RequestContext) -> MiddlewareResult:
        return MiddlewareResult(should_continue=True)

    async def dispatch(self, request: Request, call_next: object) -> Response:
        try:
            response: Response = await call_next(request)
            return response
        except Exception as exc:
            mapping = ExceptionMapper.EXCEPTION_MAP.get(type(exc))
            if mapping:
                status_code = int(mapping["status_code"])
                message = str(mapping["message"])
            else:
                status_code = 500
                message = "Internal server error"
                logger.exception("Unhandled exception in request pipeline")

            return JSONResponse(
                status_code=status_code,
                content={"detail": message, "type": type(exc).__name__},
            )


__all__ = ["ErrorHandlerMiddleware"]
