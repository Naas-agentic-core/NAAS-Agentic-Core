"""
conversation-service — الخطوة 12.

Skill مستقلة لإدارة المحادثات التعليمية عبر HTTP + WebSocket.

Contract:
  POST /chat/message  → ChatResponse (HTTP)
  WS   /chat/ws       → streaming (WebSocket)
  GET  /health        → HealthResponse
  GET  /metrics       → Prometheus text format

قواعد الـ Skill (D-038):
  - هدف واحد: إدارة المحادثات التعليمية
  - LangGraph StateGraph: intent_node → response_node
  - Prometheus metrics: 11 مقياساً حقيقياً
  - Fallback mode: يعمل بدون LLM (deterministic responses)
  - لا يستورد من microservice آخر
  - كل WebSocket session مُسجَّل في Prometheus

الخطوة 12 — D-042:
  - conversation-service يُفعَّل كـ uvicorn process على :8003
  - يُضيف الخدمة السادسة للـ Skills Architecture
  - يُحوِّل إدارة المحادثات من monolith إلى Skill مستقلة
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import time
import uuid
from contextlib import asynccontextmanager
from datetime import UTC, datetime

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import Response
from pydantic import BaseModel, Field

from microservices.conversation_service.prom_metrics import (
    get_metrics_output,
    record_db_operation,
    record_message,
    record_request,
    record_session,
    record_ws_connection,
    set_startup_info,
)
from microservices.conversation_service.src.conversation_graph import (
    get_conversation_graph,
    invoke_graph,
)

# ── D-WS-FLAP-002: WS control-message handler (inline copy) ──────────────────
# لا نستورد من `app.services.skills` لأن microservices ممنوع لها استيراد من
# monolith (§0.5). نُكرِّر منطق ping/pong هنا — Single Source of Truth يبقى
# في `app/services/skills/doctrine.py:REALTIME_PROTOCOL_DOCTRINE`.
_WS_CONTROL_TYPES = frozenset({"ping", "heartbeat", "noop"})
_WS_CONTROL_REPLY = {"ping": "pong", "heartbeat": "heartbeat_ack", "noop": None}


async def _handle_control_message(websocket: WebSocket, payload: object) -> bool:
    """يرد على ping/heartbeat/noop ويُرجع True إذا كانت رسالة تحكم."""
    if not isinstance(payload, dict):
        return False
    msg_type = payload.get("type")
    if not isinstance(msg_type, str) or msg_type.lower() not in _WS_CONTROL_TYPES:
        return False
    reply_type = _WS_CONTROL_REPLY.get(msg_type.lower())
    if reply_type is None:
        return True  # noop swallowed
    response: dict[str, object] = {"type": reply_type, "ts": datetime.now(UTC).isoformat()}
    corr = payload.get("id") or payload.get("request_id")
    if corr is not None:
        response["id"] = corr
    with contextlib.suppress(Exception):
        # client likely closed — let receive_json detect it
        await websocket.send_json(response)
    return True


logger = logging.getLogger(__name__)

_SERVICE_VERSION = "2.0.0"
_STEP = "12"
_GRAPH_READY = False


# ── Lifespan ───────────────────────────────────────────────────────────────────


@asynccontextmanager
async def lifespan(app: FastAPI):
    """يُهيِّئ الـ graph عند الإقلاع مع timeout guard."""
    global _GRAPH_READY

    db_ready = False
    graph_ready = False

    # تهيئة قاعدة البيانات
    try:
        from sqlalchemy import text

        from microservices.conversation_service.database import engine

        async with engine.begin() as conn:
            await conn.execute(text("SELECT 1"))
        db_ready = True
        record_db_operation("health_check", "success")
        logger.info("conversation-service: DB connection OK")
    except Exception as exc:
        record_db_operation("health_check", "error")
        logger.warning("conversation-service: DB not available — %s", exc)

    # تهيئة LangGraph
    try:
        await asyncio.wait_for(
            asyncio.get_event_loop().run_in_executor(None, get_conversation_graph),
            timeout=15.0,
        )
        graph_ready = True
        _GRAPH_READY = True
        logger.info("conversation-service: LangGraph StateGraph ready")
    except Exception as exc:
        logger.warning("conversation-service: Graph warmup failed — %s (DEGRADED)", exc)

    set_startup_info(
        step=_STEP,
        version=_SERVICE_VERSION,
        graph_ready=graph_ready,
        db_ready=db_ready,
        ws_enabled=True,
    )

    logger.info(
        "conversation-service v%s started on :8003 | graph=%s db=%s",
        _SERVICE_VERSION,
        graph_ready,
        db_ready,
    )

    yield

    logger.info("conversation-service: shutdown")


# ── FastAPI App ────────────────────────────────────────────────────────────────

app = FastAPI(
    title="CogniForge Conversation Service",
    version=_SERVICE_VERSION,
    description="Skill مستقلة لإدارة المحادثات التعليمية — الخطوة 12",
    lifespan=lifespan,
)


# ── نماذج الـ API ─────────────────────────────────────────────────────────────


class ChatRequest(BaseModel):
    """طلب محادثة HTTP."""

    question: str = Field(..., min_length=1, max_length=2000)
    thread_id: str | None = Field(None, description="معرف الجلسة للاستمرارية")
    history: list[dict[str, str]] = Field(default_factory=list)
    correlation_id: str | None = Field(None)


class ChatResponse(BaseModel):
    """استجابة محادثة HTTP."""

    response: str
    intent: str
    subject: str = "general"  # math | physics | chemistry | general
    thread_id: str
    correlation_id: str
    graph_ready: bool
    step: str = _STEP
    # payload الواجهة التوليدية — None للأسئلة غير الرياضية
    ui_component: dict | None = None


class HealthResponse(BaseModel):
    """استجابة فحص الصحة."""

    status: str
    service: str
    version: str
    step: str
    graph_ready: bool
    ws_enabled: bool


# ── Endpoints ─────────────────────────────────────────────────────────────────


@app.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    """فحص صحة الخدمة — يكشف عن حالة الـ graph والـ DB."""
    t0 = time.perf_counter()
    result = HealthResponse(
        status="healthy" if _GRAPH_READY else "degraded",
        service="conversation-service",
        version=_SERVICE_VERSION,
        step=_STEP,
        graph_ready=_GRAPH_READY,
        ws_enabled=True,
    )
    record_request("GET", "/health", 200, time.perf_counter() - t0)
    return result


@app.get("/metrics")
async def metrics() -> Response:
    """مقاييس Prometheus — يُصدِّر 11 مقياساً حقيقياً."""
    t0 = time.perf_counter()
    output = get_metrics_output()
    record_request("GET", "/metrics", 200, time.perf_counter() - t0)
    return Response(content=output, media_type="text/plain; version=0.0.4; charset=utf-8")


@app.post("/chat/message", response_model=ChatResponse)
async def chat_message(req: ChatRequest) -> ChatResponse:
    """
    معالجة رسالة محادثة عبر HTTP.

    يستدعي LangGraph StateGraph: intent_node → response_node.
    """
    t0 = time.perf_counter()
    thread_id = req.thread_id or f"conv-{uuid.uuid4().hex[:12]}"
    correlation_id = req.correlation_id or f"corr-{uuid.uuid4().hex[:8]}"

    try:
        result = await invoke_graph(
            question=req.question,
            thread_id=thread_id,
            correlation_id=correlation_id,
            history=req.history,
        )
        duration = time.perf_counter() - t0
        record_request("POST", "/chat/message", 200, duration)
        return ChatResponse(
            response=result["response"],
            intent=result["intent"],
            subject=result.get("subject", "general"),
            thread_id=thread_id,
            correlation_id=correlation_id,
            graph_ready=_GRAPH_READY,
            ui_component=result.get("ui_component"),
        )
    except Exception as exc:
        duration = time.perf_counter() - t0
        record_request("POST", "/chat/message", 500, duration)
        logger.error("chat_message error [%s]: %s", correlation_id, exc)
        raise HTTPException(
            status_code=500,
            detail={
                "code": "CONVERSATION_ERROR",
                "message": "فشل معالجة الرسالة",
                "trace_id": correlation_id,
            },
        ) from exc


@app.websocket("/chat/ws")
async def chat_ws(websocket: WebSocket) -> None:
    """
    WebSocket للمحادثة التفاعلية.

    Protocol:
      Client → {"question": "...", "thread_id": "...", "history": [...]}
      Server → {"response": "...", "intent": "...", "thread_id": "...", "done": true}
    """
    route = "customer"
    session_start = time.perf_counter()
    thread_id = f"ws-{uuid.uuid4().hex[:12]}"

    await websocket.accept()
    record_ws_connection(1)
    record_session(route, "opened")

    try:
        while True:
            try:
                payload = await asyncio.wait_for(websocket.receive_json(), timeout=120.0)
            except TimeoutError:
                await websocket.send_json({"error": "timeout", "done": True})
                break

            # D-WS-FLAP-002: ping/heartbeat/noop يُعالَجون قبل أي محاولة سؤال.
            if await _handle_control_message(websocket, payload):
                continue

            question = str(payload.get("question", "")).strip()
            if not question:
                await websocket.send_json({"error": "empty_question", "done": True})
                continue

            thread_id = payload.get("thread_id", thread_id)
            history = payload.get("history", [])
            correlation_id = f"ws-{uuid.uuid4().hex[:8]}"

            record_message("inbound", route)

            try:
                result = await invoke_graph(
                    question=question,
                    thread_id=thread_id,
                    correlation_id=correlation_id,
                    history=history,
                )
                response_payload = {
                    "response": result["response"],
                    "intent": result["intent"],
                    "subject": result.get("subject", "general"),
                    "thread_id": thread_id,
                    "correlation_id": correlation_id,
                    "ui_component": result.get("ui_component"),
                    "done": True,
                }
            except Exception as exc:
                logger.error("WS graph error [%s]: %s", correlation_id, exc)
                response_payload = {
                    "error": "graph_error",
                    "message": "فشل معالجة الرسالة",
                    "done": True,
                }

            await websocket.send_json(response_payload)
            record_message("outbound", route)

    except WebSocketDisconnect:
        pass
    except Exception as exc:
        logger.error("WS unexpected error: %s", exc)
    finally:
        session_duration = time.perf_counter() - session_start
        record_ws_connection(-1)
        record_session(route, "closed", session_duration)


@app.websocket("/admin/chat/ws")
async def admin_chat_ws(websocket: WebSocket) -> None:
    """WebSocket لمسار الأدمن — نفس البروتوكول مع route='admin'."""
    route = "admin"
    session_start = time.perf_counter()
    thread_id = f"admin-{uuid.uuid4().hex[:12]}"

    await websocket.accept()
    record_ws_connection(1)
    record_session(route, "opened")

    try:
        while True:
            try:
                payload = await asyncio.wait_for(websocket.receive_json(), timeout=120.0)
            except TimeoutError:
                await websocket.send_json({"error": "timeout", "done": True})
                break

            # D-WS-FLAP-002: ping/heartbeat/noop يُعالَجون قبل أي محاولة سؤال.
            if await _handle_control_message(websocket, payload):
                continue

            question = str(payload.get("question", "")).strip()
            if not question:
                await websocket.send_json({"error": "empty_question", "done": True})
                continue

            thread_id = payload.get("thread_id", thread_id)
            history = payload.get("history", [])
            correlation_id = f"admin-{uuid.uuid4().hex[:8]}"

            record_message("inbound", route)

            try:
                result = await invoke_graph(
                    question=question,
                    thread_id=thread_id,
                    correlation_id=correlation_id,
                    history=history,
                )
                response_payload = {
                    "response": result["response"],
                    "intent": result["intent"],
                    "subject": result.get("subject", "general"),
                    "thread_id": thread_id,
                    "correlation_id": correlation_id,
                    "ui_component": result.get("ui_component"),
                    "done": True,
                }
            except Exception as exc:
                logger.error("Admin WS error [%s]: %s", correlation_id, exc)
                response_payload = {
                    "error": "graph_error",
                    "message": "فشل معالجة الرسالة",
                    "done": True,
                }

            await websocket.send_json(response_payload)
            record_message("outbound", route)

    except WebSocketDisconnect:
        pass
    except Exception as exc:
        logger.error("Admin WS unexpected error: %s", exc)
    finally:
        session_duration = time.perf_counter() - session_start
        record_ws_connection(-1)
        record_session(route, "closed", session_duration)


# ── Legacy compatibility (الخطوة 11 → 12 migration) ──────────────────────────


@app.api_route(
    "/api/chat/{path:path}",
    methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS", "HEAD"],
)
async def legacy_chat_http(path: str) -> dict[str, str]:
    """
    توافق مع المسارات القديمة أثناء الانتقال التدريجي.

    يُعيد 200 مع إشارة للمسار الجديد.
    """
    t0 = time.perf_counter()
    record_request("ANY", f"/api/chat/{path}", 200, time.perf_counter() - t0)
    return {
        "status": "ok",
        "service": "conversation-service",
        "step": _STEP,
        "new_endpoint": "/chat/message",
        "path": path,
    }
