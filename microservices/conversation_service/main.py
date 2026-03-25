"""خدمة Conversation بسيطة لضمان parity مبدئي لمسارات HTTP/WS خلال التحويل التدريجي."""

from __future__ import annotations

import os
import jsonschema

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse

from app.services.chat.event_protocol import (
    ChatEventType,
    build_chat_event_envelope,
    normalize_streaming_event,
)

from microservices.conversation_service.routers.import_router import router as import_router

app = FastAPI(title="Conversation Service", version="0.1.0")
app.include_router(import_router)


def _assert_envelope_schema(event: dict[str, object]) -> None:
    """يتحقق من صحة بنية الحدث ضد المخطط التعاقدي."""
    schema = {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "type": "object",
        "required": ["type", "payload"],
        "additionalProperties": False,
        "properties": {
            "type": {
                "type": "string",
                "enum": [
                    "assistant_delta",
                    "assistant_final",
                    "assistant_error",
                    "status",
                    "conversation_init",
                    "complete",
                ],
            },
            "contract_version": {"type": "string"},
            "payload": {
                "type": "object",
                "additionalProperties": True,
                "properties": {
                    "content": {"type": "string"},
                    "details": {"type": "string"},
                    "status_code": {"type": "integer"},
                    "conversation_id": {"type": "integer"},
                },
            },
        },
    }
    try:
        jsonschema.validate(instance=event, schema=schema)
    except jsonschema.ValidationError as e:
        raise ValueError(f"Schema validation failed: {e.message}\nEvent: {event}") from e


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
    env = os.getenv("ENV", "development")

    init_event = build_chat_event_envelope(event_type=ChatEventType.CONVERSATION_INIT)
    if env != "production":
        _assert_envelope_schema(init_event)
    await websocket.send_json(init_event)

    try:
        while True:
            payload = await websocket.receive_json()
            question = str(payload.get("question", ""))

            raw_event = _response_envelope(question, route_id)
            normalized = normalize_streaming_event(raw_event)
            if env != "production":
                _assert_envelope_schema(normalized)
            await websocket.send_json(normalized)

            complete_event = build_chat_event_envelope(event_type=ChatEventType.COMPLETE)
            if env != "production":
                _assert_envelope_schema(complete_event)
            await websocket.send_json(complete_event)
    except WebSocketDisconnect:
        return
    except Exception as e:
        error_event = build_chat_event_envelope(
            event_type=ChatEventType.ASSISTANT_ERROR,
            details="Internal Server Error"
        )
        if env != "production":
            _assert_envelope_schema(error_event)
        await websocket.send_json(error_event)
        return


@app.websocket("/api/chat/ws")
async def customer_chat_ws(websocket: WebSocket) -> None:
    """نقطة WS لمسار الزبون."""
    await _chat_ws_loop(websocket, "chat_ws_customer")


@app.websocket("/admin/api/chat/ws")
async def admin_chat_ws(websocket: WebSocket) -> None:
    """نقطة WS لمسار الأدمن."""
    await _chat_ws_loop(websocket, "chat_ws_admin")
