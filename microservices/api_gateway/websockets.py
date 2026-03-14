import asyncio
import logging

import websockets
from fastapi import WebSocket, WebSocketDisconnect
from starlette.websockets import WebSocketState

logger = logging.getLogger("api_gateway")


async def websocket_proxy(client_ws: WebSocket, target_url: str):
    """
    Proxies a WebSocket connection from the client to the target URL.
    Handles bi-directional communication and connection lifecycle.
    """
    # Accept with the requested subprotocol if present so the proxy connection matches
    requested_protocols = client_ws.headers.get("sec-websocket-protocol", "").split(",")
    parsed_protocols = [p.strip() for p in requested_protocols if p.strip()]
    selected_protocol = "jwt" if "jwt" in parsed_protocols else (parsed_protocols[0] if parsed_protocols else None)

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

    # Passing all requested subprotocols to websockets.connect correctly to preserve tokens
    # (e.g., ['jwt', '<token>']) rather than just the first selected protocol.
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
                            await client_ws.send_text(message)
                except websockets.exceptions.ConnectionClosed:
                    logger.info("Target closed WebSocket connection")
                except Exception as e:
                    logger.error(f"Error reading from target: {e}")

            # Run both tasks concurrently
            # If either task finishes (e.g. disconnect), we cancel the other and exit
            _done, pending = await asyncio.wait(
                [asyncio.create_task(client_to_target()), asyncio.create_task(target_to_client())],
                return_when=asyncio.FIRST_COMPLETED,
            )

            for task in pending:
                task.cancel()

    except Exception as e:
        logger.error(f"WebSocket proxy failed to connect to {target_url}: {e}")
        # Close client connection if it's still open
        if client_ws.client_state == WebSocketState.CONNECTED:
            await client_ws.close(code=1011, reason="Upstream connection failed")
