"""
WebSocket Reverse Proxy — بوابة WebSocket الموحدة.

يُمرِّر هذا الـ router طلبات WebSocket الواردة على Gateway (:8000)
إلى conversation-service (:8003) مع الحفاظ على جميع الـ headers
وبروتوكولات المصادقة.

## لماذا هذا الملف موجود؟

Next.js rewrites (next.config.js) تعمل فقط مع HTTP — لا تُمرِّر
WebSocket upgrade headers. النتيجة: المتصفح يضرب:
  wss://[host]/api/chat/ws → Next.js → يفشل (لا يُمرِّر WS)

الحل: Gateway (8000) يستقبل WebSocket مباشرة ويُمرِّره إلى:
  ws://localhost:8003/chat/ws

## قانون معماري (D-WS-001):
  404 on websocket endpoint = architectural routing failure.
  كل WebSocket يجب أن يمر عبر هذا الـ proxy.

## الـ endpoints المُمرَّرة:
  /api/chat/ws          → ws://localhost:8003/chat/ws
  /admin/api/chat/ws    → ws://localhost:8003/admin/chat/ws
"""

import asyncio
import contextlib
import logging
import os

import websockets
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from websockets.exceptions import ConnectionClosed

logger = logging.getLogger(__name__)

router = APIRouter(tags=["WebSocket Proxy"])

# عنوان conversation-service — قابل للتهيئة عبر env var
_CONV_SERVICE_BASE = os.environ.get(
    "CONVERSATION_SERVICE_WS_URL",
    "ws://localhost:8003",
)

# مهلة الاتصال بـ conversation-service (ثوانٍ)
_CONNECT_TIMEOUT = float(os.environ.get("WS_PROXY_CONNECT_TIMEOUT", "10"))

# حجم buffer للرسائل (bytes)
_MAX_MESSAGE_SIZE = int(os.environ.get("WS_PROXY_MAX_MESSAGE_SIZE", str(10 * 1024 * 1024)))


def _build_upstream_url(path: str, query_string: str) -> str:
    """
    يبني عنوان URL للـ upstream من المسار وسلسلة الاستعلام.

    Args:
        path: المسار النسبي على conversation-service (مثل /chat/ws)
        query_string: سلسلة الاستعلام الأصلية (token, session_id, ...)

    Returns:
        عنوان URL كامل للـ upstream WebSocket
    """
    base = _CONV_SERVICE_BASE.rstrip("/")
    url = f"{base}{path}"
    if query_string:
        url = f"{url}?{query_string}"
    return url


async def _proxy_websocket(
    client_ws: WebSocket,
    upstream_url: str,
    subprotocols: list[str],
) -> None:
    """
    يُنشئ جسر ثنائي الاتجاه بين المتصفح وconversation-service.

    يُمرِّر:
    - رسائل المتصفح → upstream
    - رسائل upstream → المتصفح
    - ping/pong للحفاظ على الاتصال

    Args:
        client_ws: اتصال WebSocket من المتصفح
        upstream_url: عنوان conversation-service
        subprotocols: بروتوكولات المصادقة (jwt, token)
    """
    # D-WS-004: قبول اتصال المتصفح أولاً.
    # selected_protocol: إذا أرسل المتصفح ["jwt", token] → نُرجع "jwt" فقط.
    # إذا لم يُرسل subprotocols (query param auth) → None.
    selected_protocol = (
        "jwt" if "jwt" in subprotocols else (subprotocols[0] if subprotocols else None)
    )
    await client_ws.accept(subprotocol=selected_protocol)

    # Determine auth transport mode for diagnostics (never log token value)
    has_token_qp = "token=" in upstream_url
    auth_mode = "query_param" if has_token_qp else ("subprotocol" if subprotocols else "none")
    safe_upstream = upstream_url.split("?", maxsplit=1)[0] + ("?..." if "?" in upstream_url else "")

    logger.info(
        "ws_proxy.connecting upstream=%s auth_mode=%s protocols=%s",
        safe_upstream,
        auth_mode,
        subprotocols,
    )

    try:
        async with websockets.connect(
            upstream_url,
            subprotocols=subprotocols if subprotocols else None,
            open_timeout=_CONNECT_TIMEOUT,
            max_size=_MAX_MESSAGE_SIZE,
            ping_interval=30,
            ping_timeout=10,
            close_timeout=5,
        ) as upstream_ws:
            logger.info("ws_proxy.upstream_connected url=%s", upstream_url)

            async def client_to_upstream() -> None:
                """يُمرِّر رسائل المتصفح إلى upstream."""
                try:
                    while True:
                        data = await client_ws.receive_text()
                        await upstream_ws.send(data)
                except WebSocketDisconnect:
                    logger.debug("ws_proxy.client_disconnected")
                except Exception as exc:
                    logger.debug("ws_proxy.client_to_upstream_error: %s", exc)

            async def upstream_to_client() -> None:
                """يُمرِّر رسائل upstream إلى المتصفح."""
                try:
                    async for message in upstream_ws:
                        if isinstance(message, str):
                            await client_ws.send_text(message)
                        else:
                            await client_ws.send_bytes(message)
                except ConnectionClosed as exc:
                    logger.debug("ws_proxy.upstream_closed code=%s", exc.code)
                except Exception as exc:
                    logger.debug("ws_proxy.upstream_to_client_error: %s", exc)

            # تشغيل الاتجاهين بالتوازي — أي منهما ينتهي يُلغي الآخر
            _done, pending = await asyncio.wait(
                [
                    asyncio.create_task(client_to_upstream()),
                    asyncio.create_task(upstream_to_client()),
                ],
                return_when=asyncio.FIRST_COMPLETED,
            )

            for task in pending:
                task.cancel()
                with contextlib.suppress(asyncio.CancelledError, Exception):
                    await task

    except TimeoutError:
        logger.error(
            "ws_proxy.upstream_connect_timeout url=%s timeout=%ss",
            upstream_url,
            _CONNECT_TIMEOUT,
        )
        try:
            await client_ws.send_text(
                '{"type":"error","payload":{"details":"conversation-service unavailable","code":"WS_UPSTREAM_TIMEOUT"}}'
            )
            await client_ws.close(code=1013)
        except Exception:
            pass

    except OSError as exc:
        logger.error("ws_proxy.upstream_unreachable url=%s error=%s", upstream_url, exc)
        try:
            await client_ws.send_text(
                '{"type":"error","payload":{"details":"conversation-service unreachable","code":"WS_UPSTREAM_UNREACHABLE"}}'
            )
            await client_ws.close(code=1013)
        except Exception:
            pass

    except Exception as exc:
        logger.error("ws_proxy.unexpected_error url=%s error=%s", upstream_url, exc)
        with contextlib.suppress(Exception):
            await client_ws.close(code=1011)


@router.websocket("/api/chat/ws")
async def customer_chat_ws_proxy(websocket: WebSocket) -> None:
    """
    WebSocket proxy للمحادثة التعليمية (مستخدم قياسي).

    يُمرِّر الاتصال إلى conversation-service:/chat/ws مع الحفاظ
    على بروتوكولات المصادقة (jwt, token).

    D-WS-001: هذا هو نقطة الدخول الوحيدة لـ WebSocket من المتصفح.
    """
    query_string = websocket.scope.get("query_string", b"").decode("utf-8")
    subprotocols: list[str] = list(websocket.headers.get("sec-websocket-protocol", "").split(", "))
    subprotocols = [p.strip() for p in subprotocols if p.strip()]

    upstream_url = _build_upstream_url("/chat/ws", query_string)

    logger.info(
        "ws_proxy.customer_chat query=%s protocols=%s upstream=%s",
        query_string[:80],
        subprotocols,
        upstream_url,
    )

    await _proxy_websocket(websocket, upstream_url, subprotocols)


@router.websocket("/admin/api/chat/ws")
async def admin_chat_ws_proxy(websocket: WebSocket) -> None:
    """
    WebSocket proxy لمحادثة الأدمن.

    يُمرِّر الاتصال إلى conversation-service:/admin/chat/ws.
    """
    query_string = websocket.scope.get("query_string", b"").decode("utf-8")
    subprotocols: list[str] = list(websocket.headers.get("sec-websocket-protocol", "").split(", "))
    subprotocols = [p.strip() for p in subprotocols if p.strip()]

    upstream_url = _build_upstream_url("/admin/chat/ws", query_string)

    logger.info(
        "ws_proxy.admin_chat query=%s protocols=%s upstream=%s",
        query_string[:80],
        subprotocols,
        upstream_url,
    )

    await _proxy_websocket(websocket, upstream_url, subprotocols)
