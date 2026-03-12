"""خدمة Conversation بسيطة لضمان parity مبدئي لمسارات HTTP/WS خلال التحويل التدريجي."""

from __future__ import annotations

import os

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse

app = FastAPI(title="Conversation Service", version="0.1.0")


def _response_envelope(question: str, route_id: str) -> dict[str, str]:
    """يبني Envelope متوافقًا مبدئيًا مع تدفق المحادثة الحالي دون تغيير بروتوكول العميل."""
    return {
        "status": "ok",
        "response": f"conversation-service:{question}",
        "route_id": route_id,
    }


@app.get("/health")
async def health() -> JSONResponse:
    """يوفر نقطة صحة قياسية مع إعلان مستوى القدرة لتفعيل admission control."""
    capability_level = os.getenv("CONVERSATION_CAPABILITY_LEVEL", "stub")
    return JSONResponse(
        {
            "status": "ok",
            "service": "conversation-service",
            "capability_level": capability_level,
            "parity_ready": capability_level in {"parity_ready", "production_eligible"},
        }
    )


@app.api_route(
    "/api/chat/{path:path}",
    methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS", "HEAD"],
)
async def chat_http(path: str) -> JSONResponse:
    """يوفر استجابة HTTP متوافقة مبدئيًا لمسار chat أثناء canary."""
    return JSONResponse({"status": "ok", "path": path, "service": "conversation-service"})


async def _chat_ws_loop(websocket: WebSocket, route_id: str) -> None:
    """ينفذ حلقة WS ثنائية الاتجاه مع Envelope متوافق مبدئيًا."""
    await websocket.accept(subprotocol=websocket.headers.get("sec-websocket-protocol"))
    try:
        while True:
            payload = await websocket.receive_json()
            question = str(payload.get("question", ""))
            await websocket.send_json(_response_envelope(question, route_id))
    except WebSocketDisconnect:
        return


@app.websocket("/api/chat/ws")
async def customer_chat_ws(websocket: WebSocket) -> None:
    """نقطة WS لمسار الزبون."""
    await _chat_ws_loop(websocket, "chat_ws_customer")


@app.websocket("/admin/api/chat/ws")
async def admin_chat_ws(websocket: WebSocket) -> None:
    """نقطة WS لمسار الأدمن."""
    await _chat_ws_loop(websocket, "chat_ws_admin")
