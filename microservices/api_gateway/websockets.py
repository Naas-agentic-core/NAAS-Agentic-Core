import asyncio
import json
import logging
import re

import websockets
from fastapi import WebSocket, WebSocketDisconnect
from starlette.websockets import WebSocketState

try:
    from websockets.exceptions import InvalidStatus
except ImportError:
    InvalidStatus = None

try:
    from websockets.legacy.exceptions import InvalidStatusCode
except ImportError:
    InvalidStatusCode = None

logger = logging.getLogger("api_gateway")


async def websocket_proxy(client_ws: WebSocket, target_url: str):  # noqa: PLR0912
    """
    Proxies a WebSocket connection from the client to the target URL.
    Handles bi-directional communication and connection lifecycle.
    """
    # Accept with the requested subprotocol if present so the proxy connection matches
    requested_protocols = client_ws.headers.get("sec-websocket-protocol", "").split(",")
    parsed_protocols = [p.strip() for p in requested_protocols if p.strip()]
    selected_protocol = (
        "jwt"
        if "jwt" in parsed_protocols
        else (parsed_protocols[0] if parsed_protocols else None)
    )

    await client_ws.accept(subprotocol=selected_protocol)

    # Extract headers to forward (e.g., Auth)
    # We filter out hop-by-hop headers that shouldn't be forwarded
    headers = dict(client_ws.headers)
    headers.pop("host", None)
    headers.pop("sec-websocket-key", None)
    headers.pop("sec-websocket-version", None)
    headers.pop("sec-websocket-extensions", None)
    headers.pop("upgrade", None)
    headers.pop("connection", None)

    # Extract token from subprotocols if present and add it to Authorization header
    # This prevents token leakage in access logs by not appending it to the URL
    if parsed_protocols and "jwt" in parsed_protocols:
        try:
            jwt_index = parsed_protocols.index("jwt")
            if jwt_index + 1 < len(parsed_protocols):
                token = parsed_protocols[jwt_index + 1]
                headers["Authorization"] = f"Bearer {token}"
        except ValueError:
            pass

    # Remove the token from subprotocols if we extracted it, leaving only 'jwt'
    # to prevent token leakage in upstream access logs and avoid 4401 errors.
    if parsed_protocols and "jwt" in parsed_protocols:
        subprotocols = ["jwt"]
    else:
        subprotocols = parsed_protocols or None

    try:
        try:
            # Try websockets >= 14 format
            target_ws_context = websockets.connect(
                target_url, additional_headers=headers, subprotocols=subprotocols
            )
        except TypeError:
            # Fallback to websockets < 14 format
            target_ws_context = websockets.connect(
                target_url, extra_headers=headers, subprotocols=subprotocols
            )

        async with target_ws_context as target_ws:
            logger.info(f"API_GATEWAY received query (websocket: {client_ws.url})")
            logger.info(f"API_GATEWAY routed to → {target_url}")
            logger.info(f"WebSocket connected to {target_url}")

            async def client_to_target():
                try:
                    while True:
                        # Receive from client
                        message = await client_ws.receive_text()
                        # Forward to target
                        await target_ws.send(message)
                except WebSocketDisconnect:
                    logger.info("Client disconnected from WebSocket")
                except Exception as e:
                    logger.error(f"Error reading from client: {e}")

            async def target_to_client():
                try:
                    async for message in target_ws:
                        # Forward to client
                        if client_ws.client_state == WebSocketState.CONNECTED:
                            if isinstance(message, str):
                                msg_lower = message.strip().lower()
                                if msg_lower.startswith(
                                    "<!doctype"
                                ) or msg_lower.startswith("<html"):
                                    title_match = re.search(
                                        r"<title>(.*?)</title>", message, re.IGNORECASE
                                    )
                                    snippet = (
                                        f"title={title_match.group(1)[:100]!r}"
                                        if title_match
                                        else f"snippet={message[:200]!r}"
                                    )
                                    logger.error(
                                        "api_gateway.html_bleed_intercepted snippet=%s",
                                        snippet,
                                    )
                                    await client_ws.send_text(
                                        json.dumps(
                                            {
                                                "type": "error",
                                                "payload": {
                                                    "code": "WS_HTML_BLEED",
                                                    "details": "Upstream returned HTML instead of JSON",
                                                },
                                            }
                                        )
                                    )
                                    await client_ws.close(code=1011)
                                    break
                            await client_ws.send_text(message)
                except websockets.exceptions.ConnectionClosed:
                    logger.info("Target closed WebSocket connection")
                except Exception as e:
                    logger.error(f"Error reading from target: {e}")

            # Run both tasks concurrently
            # If either task finishes (e.g. disconnect), we cancel the other and exit
            _done, pending = await asyncio.wait(
                [
                    asyncio.create_task(client_to_target()),
                    asyncio.create_task(target_to_client()),
                ],
                return_when=asyncio.FIRST_COMPLETED,
            )

            for task in pending:
                task.cancel()

    except Exception as e:
        is_invalid_status = InvalidStatus and isinstance(e, InvalidStatus)
        is_invalid_status_code = InvalidStatusCode and isinstance(e, InvalidStatusCode)

        if is_invalid_status or is_invalid_status_code:
            status_code = getattr(e, "status_code", None)
            if hasattr(e, "response") and e.response:
                status_code = getattr(e.response, "status_code", status_code)
                body = getattr(e.response, "body", b"")
            else:
                body = b""

            body_str = body.decode("utf-8", errors="ignore").strip().lower()
            if body_str.startswith("<!doctype") or body_str.startswith("<html"):
                body_orig = body.decode("utf-8", errors="ignore")
                title_match = re.search(
                    r"<title>(.*?)</title>", body_orig, re.IGNORECASE
                )
                snippet = (
                    f"title={title_match.group(1)[:100]!r}"
                    if title_match
                    else f"snippet={body_orig[:200]!r}"
                )
                logger.error(
                    "api_gateway.upstream_invalid_status_html_bleed status=%s snippet=%s",
                    status_code,
                    snippet,
                )
                if client_ws.client_state == WebSocketState.CONNECTED:
                    try:
                        await client_ws.send_text(
                            json.dumps(
                                {
                                    "type": "error",
                                    "payload": {
                                        "code": "WS_HTML_BLEED",
                                        "details": "Upstream returned HTML instead of JSON",
                                    },
                                }
                            )
                        )
                        await client_ws.close(code=1011)
                    except Exception:
                        pass
                return

        logger.error(f"WebSocket proxy failed to connect to {target_url}: {e}")
        # Close client connection if it's still open
        if client_ws.client_state == WebSocketState.CONNECTED:
            await client_ws.close(code=1011, reason="Upstream connection failed")
