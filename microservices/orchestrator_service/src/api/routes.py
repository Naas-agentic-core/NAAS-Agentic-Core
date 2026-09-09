import asyncio
import json
import logging
import uuid
from collections.abc import AsyncGenerator

import jwt
from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    Header,
    HTTPException,
    Query,
    Request,
    WebSocket,
    WebSocketDisconnect,
)
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from microservices.orchestrator_service.src.api.context_utils import (
    _extract_client_context_messages,  # noqa: F401 — re-export (D-168)
    _merge_history_with_client_context,  # noqa: F401 — re-export (D-168)
)
from microservices.orchestrator_service.src.contracts.admin_tools import ADMIN_TOOL_CONTRACT
from microservices.orchestrator_service.src.core.config import get_settings
from microservices.orchestrator_service.src.core.database import (
    _psycopg_session_factory_proxy,
    async_session_factory,
    get_checkpointer,
    get_db,
)
from microservices.orchestrator_service.src.core.event_bus import get_event_bus
from microservices.orchestrator_service.src.core.prom_metrics import (
    record_pipeline_error,
    record_pipeline_invocation,
    set_pipeline_active,
)
from microservices.orchestrator_service.src.core.security import (
    decode_user_id,
    extract_websocket_auth,
)
from microservices.orchestrator_service.src.models.mission import Mission
from microservices.orchestrator_service.src.services.llm.client import get_ai_client
from microservices.orchestrator_service.src.services.overmind.agents.orchestrator import (
    OrchestratorAgent,
)
from microservices.orchestrator_service.src.services.overmind.domain.api_schemas import (
    MissionCreate,
    MissionEventResponse,
    MissionResponse,
)
from microservices.orchestrator_service.src.services.overmind.entrypoint import start_mission
from microservices.orchestrator_service.src.services.overmind.state import MissionStateManager
from microservices.orchestrator_service.src.services.overmind.utils.tools import tool_registry
from microservices.orchestrator_service.src.services.skills_pipeline import run_skills_pipeline
from microservices.orchestrator_service.src.services.tools.registry import get_registry

# D-168: decomposed API helpers — re-exported so runtime imports and monkeypatch
# targets on `routes.<name>` keep working (manifest: api_sources.API_SOURCE_FILES).
# Plain imports (no wrappers) preserve monkeypatch semantics for handler-resolved names.
from .agent_chat_admin_stream import stream_admin_agent_chat
from .agent_chat_customer_stream import stream_customer_agent_chat
from .agent_chat_request import (
    AgentChatCall,
    AgentChatTurn,
    TurnIdentity,
    build_agent_chat_turn,
)
from .chat_context import (
    _augment_ambiguous_objective,  # noqa: F401 — re-export (D-168)
    _build_graph_messages_graph,  # noqa: F401
    _build_graph_messages_manual,  # noqa: F401 — re-export (D-168)
    _build_langchain_messages,  # noqa: F401
    _build_older_history_digest,  # noqa: F401
    _canonicalize_mission_event,
    _compress_text_for_context,  # noqa: F401
    _context_gap_reason_for_followup,  # noqa: F401
    _detect_checkpoint_state,  # noqa: F401 — re-export (D-168)
    _extract_checkpoint_history,  # noqa: F401
    _extract_recent_entity_anchor,  # noqa: F401
    _is_ambiguous_followup,  # noqa: F401
    _normalize_checkpoint_content,  # noqa: F401
    _normalize_checkpoint_message,  # noqa: F401
    _normalize_checkpoint_role,  # noqa: F401
    _question_contains_explicit_entity,  # noqa: F401
)
from .chat_stream_engine import (
    _run_chat_langgraph,
    _stream_chat_langgraph,  # noqa: F401 — re-export (D-168)
    active_background_tasks,  # noqa: F401
)
from .chat_turn_context import (
    _apply_mission_type,  # noqa: F401 — re-export (D-168)
    _coerce_client_context,  # noqa: F401 — re-export (D-168)
    _extract_chat_objective,
    _hydrate_history,  # noqa: F401 — re-export (D-168)
)
from .chat_types import (
    _INJECTED_EXERCISE_MAX_CHARS,  # noqa: F401
    MAX_CHECKPOINT_ANCHOR_MESSAGES,  # noqa: F401
    MAX_HISTORY_MESSAGES,  # noqa: F401
    MAX_HISTORY_SUMMARY_CHARS,  # noqa: F401
    MAX_HISTORY_SUMMARY_ITEMS,  # noqa: F401
    MAX_HISTORY_SUMMARY_MESSAGES,  # noqa: F401
    ChatRunContext,
    MissionEventEnvelope,  # noqa: F401
    StreamFrame,  # noqa: F401
    _extract_injected_exercise,  # noqa: F401
    _extract_support_level,  # noqa: F401
)
from .chat_ws_scope import (
    ADMIN_WS_SCOPE,
    CUSTOMER_WS_SCOPE,
    ChatWsScope,  # noqa: F401 — re-export (D-168)
    WsTurnState,  # noqa: F401 — re-export (D-168)
)
from .chat_ws_turn import serve_chat_ws
from .conversation_store import (
    _create_new_conversation,  # noqa: F401
    _ensure_conversation,
    _lazy_import_history_with_retry,  # noqa: F401
    _persist_assistant_message,
    close_conv_service_client,  # noqa: F401
    get_conv_service_client,  # noqa: F401
)
from .identity_access import (
    _build_conversation_thread_id,
    _coerce_admin_state,  # noqa: F401
    _conversation_id_from_scoped_thread,
    _decode_auth_payload_or_401,
    _emit_identity_diagnostic_log,  # noqa: F401 — re-export (D-168)
    _is_admin_payload,
    _merge_admin_inputs,  # noqa: F401 — re-export (D-168)
    _resolve_effective_conversation_id,  # noqa: F401 — re-export (D-168)
    _resolve_session_id_from_incoming,  # noqa: F401 — re-export (D-168)
    _resolve_thread_id,  # noqa: F401 — re-export (D-168)
    _safe_assistant_error,  # noqa: F401 — re-export (D-168)
    _safe_conversation_id,
    _safe_thread_id,
    require_internal_admin_access,
)

# ⛔ كتلة إعادة تصديرٍ من `stream_serialization` كانت هنا وحُذفت: بعد استخراج البثّ
# (D-237) لم يبقَ في `routes.py` مستعملٌ لأيٍّ من أسمائها الستّة، ولا مُستورِدٌ ولا
# مُرقِّعٌ يصل إليها عبر `routes` (فُحص الأمر: صفر إصابة في المستودع كلّه — والاختبار
# الوحيد الذي يستعمل `_serialize_stream_frame_sync` يستورده من موطنه مباشرةً).
# §6.8: القدرة بلا مستهلكٍ حيّ تُحذَف ولا تُترَك stub. أعِدها بالسطر الذي يحتاجها فقط.
from .trace_utils import extract_trace_context

logger = logging.getLogger(__name__)

type JsonObject = dict[str, object]


router = APIRouter(
    tags=["Overmind (Super Agent)"],
)


class OutboxRelayResponse(BaseModel):
    """استجابة تشغيل relay اليدوي لسجلات outbox."""

    processed: int
    published: int
    failed: int
    skipped: int


class OutboxStatusResponse(BaseModel):
    """استجابة تلخص الحالة التشغيلية لطابور outbox."""

    pending: int
    processing: int
    failed: int
    published: int
    oldest_pending_age_seconds: int | None
    generated_at: str


@router.get(
    "/api/v1/system/outbox/status",
    response_model=OutboxStatusResponse,
    tags=["System"],
    dependencies=[Depends(require_internal_admin_access)],
)
async def outbox_status(db: AsyncSession = Depends(get_db)) -> OutboxStatusResponse:
    """يعرض لقطة تشغيلية آمنة عن outbox دون تعديل أي بيانات."""

    manager = MissionStateManager(session=db)
    snapshot = await manager.get_outbox_operational_snapshot()
    return OutboxStatusResponse(**snapshot)


@router.post(
    "/api/v1/system/outbox/relay",
    response_model=OutboxRelayResponse,
    tags=["System"],
    dependencies=[Depends(require_internal_admin_access)],
)
async def trigger_outbox_relay(
    batch_size: int = 50,
    max_failed_attempts: int = 3,
    processing_timeout_seconds: int = 300,
    db: AsyncSession = Depends(get_db),
) -> OutboxRelayResponse:
    """يشغل relay يدويًا بشكل آمن مع حدود واضحة للدفعة والمحاولات."""

    normalized_batch_size = max(1, min(batch_size, 200))
    normalized_attempts = max(1, min(max_failed_attempts, 10))
    normalized_processing_timeout = max(5, min(processing_timeout_seconds, 3600))

    manager = MissionStateManager(session=db)
    summary = await manager.relay_outbox_events(
        batch_size=normalized_batch_size,
        max_failed_attempts=normalized_attempts,
        processing_timeout_seconds=normalized_processing_timeout,
    )
    return OutboxRelayResponse(**summary)


# MCP Admin Tool Endpoints dynamically generated from contract
for tool_name in ADMIN_TOOL_CONTRACT:

    def _make_invoke(name: str):
        async def invoke_admin_tool(payload: JsonObject | None = None) -> JsonObject:
            if payload is None:
                payload = {}
            tool_fn = get_registry().get(name)
            if not tool_fn:
                raise HTTPException(status_code=404, detail="Tool not found in registry")

            try:
                import asyncio

                if hasattr(tool_fn, "ainvoke"):
                    result = await tool_fn.ainvoke(payload)
                elif asyncio.iscoroutinefunction(tool_fn) or asyncio.iscoroutinefunction(
                    getattr(tool_fn, "invoke", None)
                ):
                    result = await tool_fn(**payload)
                elif hasattr(tool_fn, "invoke"):
                    result = tool_fn.invoke(payload)
                else:
                    result = tool_fn(**payload)

                return {"status": "success", "result": result}
            except Exception:
                request_id = str(uuid.uuid4())
                logger.error(
                    "Admin tool invocation failed",
                    exc_info=True,
                    extra={"request_id": request_id, "tool_name": name},
                )
                return {
                    "status": "error",
                    "message": f"Tool execution failed. request_id={request_id}",
                }

        invoke_admin_tool.__name__ = f"invoke_admin_tool_{name.replace('.', '_')}"
        return invoke_admin_tool

    def _make_schema(name: str):
        async def get_admin_tool_schema() -> JsonObject:
            return {"name": name, "description": ADMIN_TOOL_CONTRACT.get(name), "parameters": {}}

        get_admin_tool_schema.__name__ = f"get_admin_tool_schema_{name.replace('.', '_')}"
        return get_admin_tool_schema

    def _make_health(name: str):
        async def get_admin_tool_health() -> JsonObject:
            tool_fn = get_registry().get(name)
            return {"name": name, "status": "healthy" if tool_fn else "unavailable"}

        get_admin_tool_health.__name__ = f"get_admin_tool_health_{name.replace('.', '_')}"
        return get_admin_tool_health

    router.post(
        f"/api/v1/tools/{tool_name}/invoke",
        tags=["Admin MCP Tools"],
        dependencies=[Depends(require_internal_admin_access)],
        operation_id=f"invoke_tool_{tool_name.replace('.', '_')}",
    )(_make_invoke(tool_name))

    router.get(
        f"/api/v1/tools/{tool_name}/schema",
        tags=["Admin MCP Tools"],
        dependencies=[Depends(require_internal_admin_access)],
        operation_id=f"get_schema_tool_{tool_name.replace('.', '_')}",
    )(_make_schema(tool_name))

    router.get(
        f"/api/v1/tools/{tool_name}/health",
        tags=["Admin MCP Tools"],
        dependencies=[Depends(require_internal_admin_access)],
        operation_id=f"get_health_tool_{tool_name.replace('.', '_')}",
    )(_make_health(tool_name))


class ChatRequest(BaseModel):
    question: str
    user_id: int
    conversation_id: int | None = None
    history_messages: list[dict[str, str]] = Field(default_factory=list)
    context: dict[str, object] = Field(default_factory=dict)


@router.get("/api/chat/messages", summary="Chat Health Endpoint")
async def chat_messages_health_endpoint() -> dict[str, str]:
    """يوفر نقطة صحة توافقية لمسار chat ضمن سلطة orchestrator الموحدة."""
    return {
        "status": "ok",
        "service": "orchestrator-service",
        "control_plane": "stategraph",
    }


@router.get("/api/chat/conversations", summary="List customer conversations")
async def list_customer_conversations(
    authorization: str | None = Header(default=None),
    limit: int = Query(default=50, ge=1, le=200),
) -> list[dict[str, object]]:
    """يعرض قائمة محادثات العميل الحالي من قاعدة orchestrator."""
    user_id, _payload = _decode_auth_payload_or_401(authorization)
    query = text(
        """
        SELECT id, title, created_at
        FROM customer_conversations
        WHERE user_id = :user_id
        ORDER BY created_at DESC, id DESC
        LIMIT :limit
        """
    )
    async with _psycopg_session_factory_proxy(default_factory=async_session_factory) as session:
        rows = (await session.execute(query, {"user_id": user_id, "limit": limit})).fetchall()
    return [
        {
            "conversation_id": int(row.id),
            "title": str(row.title or ""),
            "created_at": row.created_at.isoformat() if row.created_at is not None else None,
        }
        for row in rows
    ]


@router.get("/api/chat/conversations/{conversation_id}", summary="Customer conversation details")
async def get_customer_conversation(
    conversation_id: int,
    authorization: str | None = Header(default=None),
) -> dict[str, object]:
    """يعيد تفاصيل محادثة عميل ورسائلها بترتيب زمني."""
    user_id, _payload = _decode_auth_payload_or_401(authorization)
    return await _fetch_conversation_messages(
        conversation_id=conversation_id,
        user_id=user_id,
        conversation_table="customer_conversations",
        messages_table="customer_messages",
    )


@router.get("/admin/api/conversations", summary="List admin conversations")
async def list_admin_conversations(
    authorization: str | None = Header(default=None),
    limit: int = Query(default=50, ge=1, le=200),
) -> list[dict[str, object]]:
    """يعرض قائمة محادثات الأدمن الحالي."""
    user_id, payload = _decode_auth_payload_or_401(authorization)
    if not _is_admin_payload(payload):
        raise HTTPException(status_code=403, detail="forbidden")
    query = text(
        """
        SELECT id, title, created_at
        FROM admin_conversations
        WHERE user_id = :user_id
        ORDER BY created_at DESC, id DESC
        LIMIT :limit
        """
    )
    async with _psycopg_session_factory_proxy(default_factory=async_session_factory) as session:
        rows = (await session.execute(query, {"user_id": user_id, "limit": limit})).fetchall()
    return [
        {
            "conversation_id": int(row.id),
            "title": str(row.title or ""),
            "created_at": row.created_at.isoformat() if row.created_at is not None else None,
        }
        for row in rows
    ]


@router.get("/admin/api/conversations/{conversation_id}", summary="Admin conversation details")
async def get_admin_conversation(
    conversation_id: int,
    authorization: str | None = Header(default=None),
) -> dict[str, object]:
    """يعيد تفاصيل محادثة الأدمن ورسائلها."""
    user_id, jwt_payload = _decode_auth_payload_or_401(authorization)
    return await _fetch_conversation_messages(
        conversation_id=conversation_id,
        user_id=user_id,
        conversation_table="admin_conversations",
        messages_table="admin_messages",
        require_admin_payload=True,
        jwt_payload=jwt_payload,
    )


def _row_to_conversation_summary(row: object) -> dict[str, object]:
    """يوحّد تحويل صفّ المحادثة إلى صيغة ملخّص متّسقة عبر نطاقَي العميل والإدارة."""
    return {
        "conversation_id": int(row.id),
        "title": str(row.title or ""),
        "created_at": row.created_at.isoformat() if row.created_at is not None else None,
    }


async def _fetch_conversation_messages(
    *,
    conversation_id: int,
    user_id: int,
    conversation_table: str,
    messages_table: str,
    require_admin_payload: bool = False,
    jwt_payload: dict | None = None,
) -> dict[str, object]:
    """يسترد محادثةً واحدة ورسائلها بترتيبٍ زمني من جدوليَن ممرَّرَين.

    ⛔ كان منطق جلب المحادثات مكرَّرًا حرفيًا بين مسارَي العميل والإدارة
    (CodeScene: Code Duplication). هذا الموحّد يغلق الثغرة التي تُنسى فيها
    أيّ إعادة صياغة في أحد المسارين فقط.
    """
    if require_admin_payload and jwt_payload is not None and not _is_admin_payload(jwt_payload):
        raise HTTPException(status_code=403, detail="forbidden")
    check_query = text(
        f"""
        SELECT id, title, created_at
        FROM {conversation_table}
        WHERE id = :conversation_id AND user_id = :user_id
        """
    )
    messages_query = text(
        f"""
        SELECT role, content, created_at
        FROM {messages_table}
        WHERE conversation_id = :conversation_id
        ORDER BY id ASC
        """
    )
    async with _psycopg_session_factory_proxy(default_factory=async_session_factory) as session:
        conv_row = (
            await session.execute(
                check_query, {"conversation_id": conversation_id, "user_id": user_id}
            )
        ).fetchone()
        if conv_row is None:
            raise HTTPException(status_code=404, detail="Conversation not found")
        message_rows = (
            await session.execute(messages_query, {"conversation_id": conversation_id})
        ).fetchall()

    return {
        "conversation_id": int(conv_row.id),
        "title": str(conv_row.title or ""),
        "created_at": conv_row.created_at.isoformat() if conv_row.created_at is not None else None,
        "messages": [
            {
                "role": str(msg.role),
                "content": str(msg.content),
                "created_at": msg.created_at.isoformat() if msg.created_at is not None else None,
            }
            for msg in message_rows
        ],
    }


@router.post("/api/chat/messages", summary="StateGraph Chat Endpoint")
async def chat_messages_endpoint(
    payload: dict[str, object],
    request: Request,
    authorization: str | None = Header(default=None),
) -> StreamingResponse:
    """ينفّذ رسالة chat عبر خدمة LangGraph ويعيد نتيجة تشغيل موحدة عبر Stream."""
    objective = _extract_chat_objective(payload)
    if objective is None:
        raise HTTPException(status_code=422, detail="question/objective is required")

    context_payload = payload.get("context")
    context: ChatRunContext = {}
    if isinstance(context_payload, dict):
        for key, value in context_payload.items():
            if not isinstance(key, str):
                continue
            context[key] = value

    user_id, _jwt_payload = _decode_auth_payload_or_401(authorization)
    context["user_id"] = user_id

    # D-171 (ISS-132): حمولة الإدمن تُمرَّر للمحرك **فقط** حين تحمل الـ JWT الموقَّعة
    # claim إدارياً (fail-closed — المستخدم العادي يبقى بلا أي مفاتيح إدارة في الحالة).
    # كانت `_jwt_payload` تُتجاهَل هنا فتُنفَّذ الأداة ثم يرفضها ValidateAccessNode.
    _admin_payload = _jwt_payload if _is_admin_payload(_jwt_payload) else None

    chat_scope = "customer"

    requested_conversation_id = _safe_conversation_id(payload.get("conversation_id"))
    if requested_conversation_id is None:
        scoped_thread = _safe_thread_id(context.get("thread_id"))
        if scoped_thread is None:
            scoped_thread = _safe_thread_id(context.get("session_id"))
        if scoped_thread is not None:
            requested_conversation_id = _conversation_id_from_scoped_thread(
                thread_id=scoped_thread,
                user_id=user_id,
            )

    async with _psycopg_session_factory_proxy(default_factory=async_session_factory) as session:
        conversation_id, history_messages = await _ensure_conversation(
            session=session,
            chat_scope=chat_scope,
            user_id=user_id,
            question=objective,
            requested_conversation_id=requested_conversation_id,
        )
    context["conversation_id"] = conversation_id

    # حماية عزل السياق: يمنع قبول thread/session معرفَين من العميل حتى لا تختلط محادثات مستقلة.
    context["thread_id"] = _build_conversation_thread_id(user_id, conversation_id)

    async def _generator_with_persistence() -> AsyncGenerator[str, None]:
        generator = _run_chat_langgraph(
            objective,
            context,
            app_graph=getattr(request.app.state, "app_graph", None),
            admin_payload=_admin_payload,  # D-171 (ISS-132)
            history_messages=history_messages,
        )
        # ISS-STREAM-001: تجميع كل الـ deltas للحفظ الصحيح.
        # عند streaming، assistant_final يُرسل content="" لتجنب التكرار،
        # لذا يجب تجميع كل assistant_delta chunks لبناء النص الكامل.
        delta_parts: list[str] = []
        final_content = ""
        async for chunk in generator:
            try:
                chunk_data = json.loads(chunk)
                chunk_type = chunk_data.get("type", "")
                payload = chunk_data.get("payload", {})
                if chunk_type in ("assistant_delta",):
                    delta_text = payload.get("content", "")
                    if delta_text:
                        delta_parts.append(delta_text)
                elif chunk_type == "assistant_final":
                    # إذا كان content غير فارغ (fallback بدون streaming) → استخدمه
                    # إذا كان فارغاً (streaming mode) → استخدم الـ deltas المجمّعة
                    fc = payload.get("content", "")
                    if fc:
                        final_content = fc
                    elif delta_parts:
                        final_content = "".join(delta_parts)
            except Exception:
                pass
            yield chunk

        # إذا لم يصل assistant_final لكن وصلت deltas → استخدمها
        if not final_content and delta_parts:
            final_content = "".join(delta_parts)

        if final_content:
            try:
                async with _psycopg_session_factory_proxy(
                    default_factory=async_session_factory
                ) as db_session:
                    await _persist_assistant_message(
                        session=db_session,
                        chat_scope=chat_scope,
                        conversation_id=conversation_id,
                        content=final_content,
                    )
            except Exception as e:
                logger.error("[HTTP_PERSIST] failed to save final chat message: %s", e)

    return StreamingResponse(_generator_with_persistence(), media_type="text/plain")


@router.websocket("/api/chat/ws")
async def chat_ws_stategraph(websocket: WebSocket) -> None:
    """يشغّل WebSocket chat فوق LangGraph لضمان توحيد مسار التنفيذ مع mission."""
    token, selected_protocol = extract_websocket_auth(websocket)
    if not token:
        await websocket.close(code=4401)
        return

    try:
        user_id = decode_user_id(token, get_settings().SECRET_KEY)
    except HTTPException:
        await websocket.close(code=4401)
        return

    await websocket.accept(subprotocol=selected_protocol)
    await serve_chat_ws(websocket, scope=CUSTOMER_WS_SCOPE, user_id=user_id)


@router.websocket("/admin/api/chat/ws")
async def admin_chat_ws_stategraph(websocket: WebSocket) -> None:
    """يشغّل WebSocket الإداري عبر LangGraph بنفس السلطة الموحدة للـ control-plane."""
    token, selected_protocol = extract_websocket_auth(websocket)
    if not token:
        await websocket.close(code=4401)
        return

    try:
        auth_payload = jwt.decode(token, get_settings().SECRET_KEY, algorithms=["HS256"])
        user_id = int(auth_payload.get("sub", auth_payload.get("user_id", 0)) or 0)
        if user_id <= 0:
            raise HTTPException(status_code=401, detail="Invalid user")
    except (HTTPException, jwt.PyJWTError, ValueError):
        await websocket.close(code=4401)
        return

    if not _is_admin_payload(auth_payload):
        await websocket.close(code=4403)
        return

    await websocket.accept(subprotocol=selected_protocol)
    await serve_chat_ws(
        websocket, scope=ADMIN_WS_SCOPE, user_id=user_id, admin_payload=auth_payload
    )


def _get_mission_status_payload(status: str) -> dict[str, str | None]:
    if status == "partial_success":
        return {"status": "success", "outcome": "partial_success"}
    return {"status": status, "outcome": None}


def _serialize_mission(mission: Mission) -> MissionResponse:
    status_payload = _get_mission_status_payload(getattr(mission.status, "value", mission.status))
    return MissionResponse(
        id=mission.id,
        objective=mission.objective,
        status=status_payload["status"],
        outcome=status_payload["outcome"],
        created_at=mission.created_at,
        updated_at=mission.updated_at,
        result={"summary": mission.result_summary} if mission.result_summary else None,
        steps=[],
    )


def _build_chat_turn(
    request: ChatRequest,
    user_id: int,
    auth_payload: dict | None,
    trace_context: dict[str, object],
) -> "AgentChatTurn":
    """يبني دورة محادثة الوكيل من طلبٍ مصادَق عليه — مستخرج من نقطة الدخول."""
    identity = TurnIdentity(user_id, request.conversation_id, request.history_messages)
    return build_agent_chat_turn(
        request_context=request.context,
        identity=identity,
        trace_context=trace_context,
        auth_payload=auth_payload,
    )


def _select_chat_stream(
    *,
    turn,
    call: "AgentChatCall",
    app_state: object,
    request_context: dict[str, object],
) -> AsyncGenerator:
    """ينتقي مسار البثّ المناسب (إداري أم عميل) بقرارٍ واحدٍ معزول."""
    if turn.is_admin:
        return stream_admin_agent_chat(
            app_state=app_state, call=call, request_context=request_context
        )
    return stream_customer_agent_chat(
        agent=OrchestratorAgent(get_ai_client(), tool_registry),
        call=call,
        context=turn.context,
    )


@router.post("/agent/chat", summary="Chat with Orchestrator Agent")
async def chat_with_agent_endpoint(
    request: ChatRequest,
    fastapi_req: Request,
    authorization: str | None = Header(default=None),
) -> StreamingResponse:
    """Direct chat endpoint for the Orchestrator Agent (Microservice).
    Streams the response chunk by chunk."""
    trace_context = extract_trace_context(fastapi_req)
    user_id, auth_payload = _decode_auth_payload_or_401(authorization)
    request.user_id = user_id  # Override body user_id with JWT user_id
    logger.info(f"Agent Chat Request: {request.question[:50]}... User: {request.user_id}")

    turn = _build_chat_turn(request, user_id, auth_payload, trace_context)
    # ⛔ كان هذا السطر يستخدم `turn.identity` — وهو غير موجود في AgentChatTurn
    # (بياناتها: context · is_admin · is_compatibility_facade فقط) فيسقط كل
    # استدعاءٍ مباشرٍ لـ POST /agent/chat بـ 500 AttributeError. تُبنى الهوية من
    # الطلب المصادَق عليه مباشرةً، كما يفترضها تصميم agent_chat_request.
    identity = TurnIdentity(user_id, request.conversation_id, request.history_messages)
    call = AgentChatCall(request.question, identity, turn.is_compatibility_facade)
    stream = _select_chat_stream(
        turn=turn,
        call=call,
        app_state=fastapi_req.app.state,
        request_context=request.context,
    )
    return StreamingResponse(stream, media_type="text/plain")


def _extract_initiator_id_from_authorization(authorization: str | None) -> int:
    """يستخرج معرف مطلق المهمة من رمز JWT الموقّع — كان 1 مُثبَّتًا في الشفرة."""
    if not authorization:
        raise HTTPException(status_code=401, detail="Authorization header required")
    user_id, _payload = _decode_auth_payload_or_401(authorization)
    return user_id


@router.post("/missions", response_model=MissionResponse, summary="Launch Mission")
async def create_mission_endpoint(
    request: MissionCreate,
    background_tasks: BackgroundTasks,
    req: Request,
    authorization: str | None = Header(default=None),
    db: AsyncSession = Depends(get_db),
) -> MissionResponse:
    initiator_id = _extract_initiator_id_from_authorization(authorization)
    correlation_id = req.headers.get("X-Correlation-ID") or str(uuid.uuid4())
    logger.info(
        f"Orchestrator: Creating mission with Correlation ID: {correlation_id} "
        f"initiator={initiator_id}"
    )

    try:
        mission = await start_mission(
            session=db,
            objective=request.objective,
            initiator_id=initiator_id,
            context=request.context,
            force_research=False,
            idempotency_key=correlation_id,
        )

        return _serialize_mission(mission)

    except Exception as e:
        request_id = str(uuid.uuid4())
        logger.error(
            "Failed to create mission",
            exc_info=True,
            extra={"request_id": request_id},
        )
        raise HTTPException(
            status_code=500,
            detail=f"Mission creation failed. request_id={request_id}",
        ) from e


@router.get("/missions/{mission_id}", response_model=MissionResponse, summary="Get Mission")
async def get_mission_endpoint(
    mission_id: int,
    req: Request,
    authorization: str | None = Header(default=None),
    db: AsyncSession = Depends(get_db),
) -> MissionResponse:
    if not authorization:
        raise HTTPException(status_code=401, detail="Authorization header required")
    _decode_auth_payload_or_401(authorization)
    state_manager = MissionStateManager(db)
    mission = await state_manager.get_mission(mission_id)

    if not mission:
        raise HTTPException(status_code=404, detail="Mission not found")

    return _serialize_mission(mission)


@router.get(
    "/missions/{mission_id}/events",
    response_model=list[MissionEventResponse],
    summary="Get Mission Events",
)
async def get_mission_events_endpoint(
    mission_id: int,
    req: Request,
    authorization: str | None = Header(default=None),
    db: AsyncSession = Depends(get_db),
) -> list[MissionEventResponse]:
    """يسرد أحداث مهمة معيّنة بتسلسلها الزمني."""
    if not authorization:
        raise HTTPException(status_code=401, detail="Authorization header required")
    _decode_auth_payload_or_401(authorization)
    state_manager = MissionStateManager(db)
    events = await state_manager.get_mission_events(mission_id)

    return [
        MissionEventResponse(
            event_type=(
                evt.event_type.value if hasattr(evt.event_type, "value") else str(evt.event_type)
            ),
            mission_id=evt.mission_id,
            timestamp=evt.created_at,
            payload=json.loads(evt.payload_json)
            if isinstance(evt.payload_json, str)
            else evt.payload_json,
        )
        for evt in events
    ]


@router.websocket("/missions/{mission_id}/ws")
async def stream_mission_ws(
    websocket: WebSocket,
    mission_id: int,
) -> None:
    token, selected_protocol = extract_websocket_auth(websocket)
    if not token:
        await websocket.close(code=4401)
        return

    try:
        decode_user_id(token, get_settings().SECRET_KEY)
    except HTTPException:
        await websocket.close(code=4401)
        return

    await websocket.accept(subprotocol=selected_protocol)

    event_bus = get_event_bus()
    channel = f"mission:{mission_id}"

    # We need a subscription iterator
    subscription = event_bus.subscribe(channel)

    try:
        async with _psycopg_session_factory_proxy(default_factory=async_session_factory) as session:
            state_manager = MissionStateManager(session)
            mission = await state_manager.get_mission(mission_id)
            if not mission:
                await websocket.close(code=4004)
                return

            status_payload = _get_mission_status_payload(mission.status.value)
            await websocket.send_json({"type": "mission_status", "payload": status_payload})

            events = await state_manager.get_mission_events(mission_id)
            for evt in events:
                evt_type = (
                    evt.event_type.value
                    if hasattr(evt.event_type, "value")
                    else str(evt.event_type)
                )
                payload = evt.payload_json or {}
                await websocket.send_json(
                    {"type": "mission_event", "payload": {"event_type": evt_type, "data": payload}}
                )

    except Exception as e:
        logger.error(f"WS Init Error: {e}")
        await websocket.close(code=1011)
        return

    try:
        while True:
            try:
                async with asyncio.timeout(300.0):
                    event = await anext(subscription)
            except StopAsyncIteration:
                break
            except TimeoutError:
                await websocket.close(code=1011, reason="Timeout waiting for mission events")
                break

            canonical_event = _canonicalize_mission_event(event)
            if canonical_event is None:
                continue

            await websocket.send_json({"type": "mission_event", "payload": canonical_event})

            if canonical_event["event_type"] in ("mission_completed", "mission_failed"):
                # Fetch final status
                async with _psycopg_session_factory_proxy(
                    default_factory=async_session_factory
                ) as final_session:
                    sm = MissionStateManager(final_session)
                    m = await sm.get_mission(mission_id)
                    if m:
                        status_p = _get_mission_status_payload(m.status.value)
                        await websocket.send_json({"type": "mission_status", "payload": status_p})
                break

    except WebSocketDisconnect:
        logger.info(f"WS Disconnected: {mission_id}")
    except Exception as e:
        logger.error(f"WS Loop Error: {e}")
    finally:
        await websocket.close()
        try:
            await subscription.aclose()
        except Exception as e:
            logger.warning("[WS_CLEANUP] subscription.aclose() failed: %s", e)


# ═══════════════════════════════════════════════════════════════════════════
# Skills Composition Pipeline — /compose (Step 9)
# ═══════════════════════════════════════════════════════════════════════════


class ComposeRequest(BaseModel):
    """طلب تشغيل Skills Composition Pipeline."""

    query: str = Field(..., min_length=1, max_length=2000, description="سؤال الطالب أو المهمة")
    correlation_id: str | None = Field(
        default=None,
        description="معرف التتبع الموزع (يُولَّد تلقائياً إذا لم يُعطَ)",
    )


class SkillResultSchema(BaseModel):
    """نتيجة Skill واحدة في الـ Pipeline."""

    skill: str
    status: str
    data: dict[str, object]
    duration_ms: float
    error: str | None = None


class ComposeResponse(BaseModel):
    """الاستجابة الكاملة من Skills Composition Pipeline."""

    correlation_id: str
    query: str
    composed_answer: str
    pipeline_mode: str
    skills_active: list[str]
    total_duration_ms: float
    composition_confidence: float = 0.0  # D-110: ثقة التركيب [0,1]
    plan: SkillResultSchema
    research: SkillResultSchema
    reasoning: SkillResultSchema


@router.post(
    "/compose",
    response_model=ComposeResponse,
    tags=["Skills Pipeline"],
    summary="Skills Composition Pipeline",
    description=(
        "يُشغِّل Skills Composition Pipeline الكامل:\n"
        "1. PlanningSkill → خطة استراتيجية\n"
        "2. ResearchSkill → معلومات ذات صلة (بالتوازي مع Planning)\n"
        "3. ReasoningSkill → تفكير عميق MCTS + LLM\n"
        "4. Compose → إجابة مُركَّبة من الـ 3 Skills\n\n"
        "Fallback mode تلقائي عند تعذر الوصول لأي Skill."
    ),
)
async def compose_skills(
    request: ComposeRequest,
    fastapi_req: Request,
    x_correlation_id: str | None = Header(default=None, alias="X-Correlation-ID"),
) -> ComposeResponse:
    """
    يُنفِّذ Skills Composition Pipeline ويُعيد الإجابة المُركَّبة.

    يُسجِّل مقاييس Prometheus لكل استدعاء:
      - cogniforge_pipeline_invocations_total{mode=...}
      - cogniforge_pipeline_duration_seconds{mode=...}
      - cogniforge_pipeline_skill_calls_total{skill=...,status=...}
      - cogniforge_pipeline_skill_duration_seconds{skill=...}
    """
    correlation_id = request.correlation_id or x_correlation_id or str(uuid.uuid4())

    # Extract trace context
    trace_context = extract_trace_context(fastapi_req)

    set_pipeline_active(1)
    try:
        result = await run_skills_pipeline(
            query=request.query,
            correlation_id=correlation_id,
            trace_context=trace_context,
        )
    except Exception as exc:
        set_pipeline_active(0)
        record_pipeline_error("compose_error")
        logger.error("pipeline_error correlation_id=%s error=%s", correlation_id, exc)
        raise HTTPException(
            status_code=502,
            detail={
                "code": "PIPELINE_ERROR",
                "message": str(exc),
                "trace_id": correlation_id,
            },
        ) from exc

    set_pipeline_active(0)

    # تسجيل مقاييس Prometheus
    skill_results = [
        (result.plan.skill, result.plan.status, result.plan.duration_ms / 1000),
        (result.research.skill, result.research.status, result.research.duration_ms / 1000),
        (result.reasoning.skill, result.reasoning.status, result.reasoning.duration_ms / 1000),
    ]
    record_pipeline_invocation(
        mode=result.pipeline_mode,
        duration_seconds=result.total_duration_ms / 1000,
        skill_results=skill_results,
    )

    return ComposeResponse(
        correlation_id=result.correlation_id,
        query=result.query,
        composed_answer=result.composed_answer,
        pipeline_mode=result.pipeline_mode,
        skills_active=result.skills_active,
        total_duration_ms=result.total_duration_ms,
        composition_confidence=result.composition_confidence,
        plan=SkillResultSchema(**result.plan.__dict__),
        research=SkillResultSchema(**result.research.__dict__),
        reasoning=SkillResultSchema(**result.reasoning.__dict__),
    )


# ── Checkpointer Status — /checkpointer/status (Step 10) ─────────────────────


@router.get(
    "/checkpointer/status",
    summary="Postgres Checkpointer Status",
    tags=["observability"],
)
async def checkpointer_status() -> dict:
    """
    يُعيد حالة Postgres Checkpointer الحي.

    Step 10: runtime evidence للـ checkpointer.
    backend: postgres | memory | none
    """
    ckpt = get_checkpointer()
    if ckpt is None:
        return {
            "backend": "memory",
            "step": "10",
            "active": False,
            "tables_ready": False,
            "active_threads": 0,
            "message": "AsyncPostgresSaver not initialised — using MemorySaver fallback",
        }
    active_threads = len(getattr(ckpt, "_active_threads", set()))
    return {
        "backend": "postgres",
        "step": "10",
        "active": True,
        "tables_ready": True,
        "active_threads": active_threads,
        "pool_size": 5,
        "message": "AsyncPostgresSaver ACTIVE — LangGraph state persisted to PostgreSQL",
    }
