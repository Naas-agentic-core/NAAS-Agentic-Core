import logging
import uuid

from sqlalchemy import text

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    HTTPException,
    Request,
    WebSocket,
    WebSocketDisconnect,
)
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from microservices.orchestrator_service.src.core.config import get_settings
from microservices.orchestrator_service.src.core.database import async_session_factory, get_db
from microservices.orchestrator_service.src.core.event_bus import get_event_bus
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
    LangGraphRunRequest,
    MissionCreate,
    MissionEventResponse,
    MissionResponse,
)
from microservices.orchestrator_service.src.services.overmind.entrypoint import start_mission
from microservices.orchestrator_service.src.services.overmind.factory import (
    create_langgraph_service,
)
from microservices.orchestrator_service.src.services.overmind.state import MissionStateManager
from microservices.orchestrator_service.src.services.overmind.utils.mission_complex import (
    handle_mission_complex_stream,
)
from microservices.orchestrator_service.src.services.overmind.utils.tools import tool_registry

logger = logging.getLogger(__name__)

router = APIRouter(
    tags=["Overmind (Super Agent)"],
)


class ChatRequest(BaseModel):
    question: str
    user_id: int
    conversation_id: int | None = None
    history_messages: list[dict[str, str]] = Field(default_factory=list)
    context: dict[str, object] = Field(default_factory=dict)


def _extract_chat_objective(payload: dict[str, object]) -> str | None:
    """يستخلص الهدف النصي للدردشة من حمولة عامة بشكل صريح وآمن."""
    question = payload.get("question")
    if isinstance(question, str) and question.strip():
        return question.strip()
    objective = payload.get("objective")
    if isinstance(objective, str) and objective.strip():
        return objective.strip()
    return None


def _is_mission_complex(payload: dict[str, object]) -> bool:
    """يتحقق من مسار المهمة الخارقة عبر mission_type المباشر أو داخل metadata."""
    mission_type = payload.get("mission_type")
    if isinstance(mission_type, str) and mission_type.strip().lower() == "mission_complex":
        return True

    metadata = payload.get("metadata")
    if isinstance(metadata, dict):
        metadata_type = metadata.get("mission_type")
        if isinstance(metadata_type, str) and metadata_type.strip().lower() == "mission_complex":
            return True
    return False


def _extract_mission_context(payload: dict[str, object]) -> dict[str, object]:
    """يبني سياق المهمة بشكل صريح مع الحفاظ على conversation_id وmetadata."""
    context: dict[str, object] = {}
    if isinstance(payload.get("metadata"), dict):
        context["metadata"] = payload["metadata"]

    conversation_id = payload.get("conversation_id")
    if isinstance(conversation_id, int):
        context["conversation_id"] = conversation_id
    context["mission_type"] = "mission_complex"
    return context


async def _ensure_conversation(
    *,
    chat_scope: str,
    user_id: int,
    question: str,
    requested_conversation_id: int | None,
) -> int:
    """ينشئ أو يتحقق من المحادثة ويحفظ رسالة المستخدم لضمان اتساق التاريخ."""
    is_admin_scope = chat_scope == "admin"
    check_query = (
        text("SELECT id FROM admin_conversations WHERE id=:conversation_id AND user_id=:user_id")
        if is_admin_scope
        else text("SELECT id FROM customer_conversations WHERE id=:conversation_id AND user_id=:user_id")
    )
    create_query = (
        text("INSERT INTO admin_conversations (title, user_id) VALUES (:title, :user_id) RETURNING id")
        if is_admin_scope
        else text(
            "INSERT INTO customer_conversations (title, user_id) VALUES (:title, :user_id) RETURNING id"
        )
    )
    insert_message_query = (
        text(
            "INSERT INTO admin_messages (conversation_id, role, content) "
            "VALUES (:conversation_id, :role, :content)"
        )
        if is_admin_scope
        else text(
            "INSERT INTO customer_messages (conversation_id, role, content) "
            "VALUES (:conversation_id, :role, :content)"
        )
    )

    async with async_session_factory() as session:
        conversation_id = requested_conversation_id
        if conversation_id is not None:
            result = await session.execute(
                check_query,
                {"conversation_id": conversation_id, "user_id": user_id},
            )
            exists = result.scalar_one_or_none()
            if exists is None:
                raise HTTPException(status_code=403, detail="conversation does not belong to user")
        else:
            title = question.strip()[:120] or "Super Agent Mission"
            created = await session.execute(create_query, {"title": title, "user_id": user_id})
            created_id = created.scalar_one_or_none()
            if created_id is None:
                raise HTTPException(status_code=500, detail="failed to create conversation")
            conversation_id = int(created_id)

        await session.execute(
            insert_message_query,
            {
                "conversation_id": int(conversation_id),
                "role": "user",
                "content": question,
            },
        )
        await session.commit()

    return int(conversation_id)


async def _persist_assistant_message(
    *,
    chat_scope: str,
    conversation_id: int,
    content: str,
    mission_id: int | None,
) -> None:
    """يحفظ رد المساعد النهائي ويربط mission_id بالمحادثة الإدارية عند توفره."""
    is_admin_scope = chat_scope == "admin"
    insert_message_query = (
        text(
            "INSERT INTO admin_messages (conversation_id, role, content) "
            "VALUES (:conversation_id, :role, :content)"
        )
        if is_admin_scope
        else text(
            "INSERT INTO customer_messages (conversation_id, role, content) "
            "VALUES (:conversation_id, :role, :content)"
        )
    )
    link_query = text(
        "UPDATE admin_conversations SET linked_mission_id=:mission_id WHERE id=:conversation_id"
    )

    async with async_session_factory() as session:
        await session.execute(
            insert_message_query,
            {
                "conversation_id": conversation_id,
                "role": "assistant",
                "content": content,
            },
        )
        if is_admin_scope and mission_id is not None:
            await session.execute(
                link_query,
                {
                    "mission_id": mission_id,
                    "conversation_id": conversation_id,
                },
            )
        await session.commit()


async def _stream_mission_complex_events(
    websocket: WebSocket,
    *,
    incoming: dict[str, object],
    objective: str,
    user_id: int,
    chat_scope: str,
) -> None:
    """يوحّد بث mission_complex عبر send_json ويحافظ على الربط مع التاريخ."""
    requested_conversation_id = incoming.get("conversation_id")
    conversation_id = requested_conversation_id if isinstance(requested_conversation_id, int) else None
    try:
        conversation_id = await _ensure_conversation(
            chat_scope=chat_scope,
            user_id=user_id,
            question=objective,
            requested_conversation_id=conversation_id,
        )
    except HTTPException as error:
        await websocket.send_json({"type": "assistant_error", "payload": {"content": error.detail}})
        return
    context = _extract_mission_context(incoming)
    context["conversation_id"] = conversation_id
    context["chat_scope"] = chat_scope

    await websocket.send_json(
        {
            "type": "conversation_init",
            "payload": {"conversation_id": conversation_id},
        }
    )

    mission_id: int | None = None
    final_content = ""
    terminal_event_emitted = False
    async for event in handle_mission_complex_stream(objective, context, user_id=user_id):
        await websocket.send_json(event)
        event_type = str(event.get("type", ""))
        payload = event.get("payload")
        payload_dict = payload if isinstance(payload, dict) else {}
        if event_type == "mission_created":
            candidate_id = payload_dict.get("mission_id")
            if isinstance(candidate_id, int):
                mission_id = candidate_id
        if event_type in {"assistant_final", "assistant_error"}:
            terminal_event_emitted = True
            content = payload_dict.get("content")
            if isinstance(content, str):
                final_content = content

    if not terminal_event_emitted:
        final_content = "تعذر إكمال المهمة الخارقة بسبب انقطاع غير متوقع في البث."
        await websocket.send_json(
            {
                "type": "assistant_error",
                "payload": {"content": final_content},
            }
        )

    if final_content.strip():
        await _persist_assistant_message(
            chat_scope=chat_scope,
            conversation_id=conversation_id,
            content=final_content,
            mission_id=mission_id,
        )


async def _run_chat_langgraph(
    objective: str,
    context: dict[str, str | int | float | bool | None],
) -> dict[str, object]:
    """يشغّل LangGraph كعمود فقري لرحلة chat ويعيد حمولة موحدة قابلة للبث."""
    service = create_langgraph_service()
    request = LangGraphRunRequest(objective=objective, context=context)
    run_data = await service.run(request)
    execution_summary = run_data.execution or {}
    response_text = str(execution_summary.get("summary") or objective)
    return {
        "status": "ok",
        "response": response_text,
        "run_id": run_data.run_id,
        "timeline": [event.model_dump(mode="json") for event in run_data.timeline],
        "graph_mode": "stategraph",
    }


@router.get("/api/chat/messages", summary="Chat Health Endpoint")
async def chat_messages_health_endpoint() -> dict[str, str]:
    """يوفر نقطة صحة توافقية لمسار chat ضمن سلطة orchestrator الموحدة."""
    return {
        "status": "ok",
        "service": "orchestrator-service",
        "control_plane": "stategraph",
    }


@router.post("/api/chat/messages", summary="StateGraph Chat Endpoint")
async def chat_messages_endpoint(payload: dict[str, object]) -> dict[str, object]:
    """ينفّذ رسالة chat عبر خدمة LangGraph ويعيد نتيجة تشغيل موحدة."""
    objective = _extract_chat_objective(payload)
    if objective is None:
        raise HTTPException(status_code=422, detail="question/objective is required")

    context_payload = payload.get("context")
    context: dict[str, str | int | float | bool | None] = {}
    if isinstance(context_payload, dict):
        for key, value in context_payload.items():
            if not isinstance(key, str):
                continue
            if isinstance(value, str | int | float | bool) or value is None:
                context[key] = value

    return await _run_chat_langgraph(objective, context)


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
    try:
        while True:
            incoming = await websocket.receive_json()
            if not isinstance(incoming, dict):
                await websocket.send_json({"status": "error", "message": "invalid payload"})
                continue
            objective = _extract_chat_objective(incoming)
            if objective is None:
                await websocket.send_json(
                    {"status": "error", "message": "question/objective required"}
                )
                continue

            if _is_mission_complex(incoming):
                await _stream_mission_complex_events(
                    websocket,
                    incoming=incoming,
                    objective=objective,
                    user_id=user_id,
                    chat_scope="customer",
                )
                continue

            result = await _run_chat_langgraph(objective, {})
            result["route_id"] = "chat_ws_customer"
            await websocket.send_json(result)
    except WebSocketDisconnect:
        logger.info("Customer chat websocket disconnected")


@router.websocket("/admin/api/chat/ws")
async def admin_chat_ws_stategraph(websocket: WebSocket) -> None:
    """يشغّل WebSocket الإداري عبر LangGraph بنفس السلطة الموحدة للـ control-plane."""
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
    try:
        while True:
            incoming = await websocket.receive_json()
            if not isinstance(incoming, dict):
                await websocket.send_json({"status": "error", "message": "invalid payload"})
                continue
            objective = _extract_chat_objective(incoming)
            if objective is None:
                await websocket.send_json(
                    {"status": "error", "message": "question/objective required"}
                )
                continue

            if _is_mission_complex(incoming):
                await _stream_mission_complex_events(
                    websocket,
                    incoming=incoming,
                    objective=objective,
                    user_id=user_id,
                    chat_scope="admin",
                )
                continue

            result = await _run_chat_langgraph(objective, {})
            result["route_id"] = "chat_ws_admin"
            await websocket.send_json(result)
    except WebSocketDisconnect:
        logger.info("Admin chat websocket disconnected")


def _get_mission_status_payload(status: str) -> dict[str, str | None]:
    if status == "partial_success":
        return {"status": "success", "outcome": "partial_success"}
    return {"status": status, "outcome": None}


def _serialize_mission(mission: Mission) -> MissionResponse:
    status_payload = _get_mission_status_payload(mission.status.value)
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


@router.post("/agent/chat", summary="Chat with Orchestrator Agent")
async def chat_with_agent_endpoint(
    request: ChatRequest,
) -> StreamingResponse:
    """
    Direct chat endpoint for the Orchestrator Agent (Microservice).
    Streams the response chunk by chunk.
    """
    logger.info(f"Agent Chat Request: {request.question[:50]}... User: {request.user_id}")

    ai_client = get_ai_client()
    agent = OrchestratorAgent(ai_client, tool_registry)

    # Prepare context
    context = request.context.copy()
    context.update(
        {
            "user_id": request.user_id,
            "conversation_id": request.conversation_id,
            "history_messages": request.history_messages,
        }
    )

    async def _stream_generator():
        try:
            run_result = agent.run(request.question, context=context)
            async for chunk in run_result:
                yield chunk
        except Exception as e:
            logger.error(f"Agent Chat Error: {e}", exc_info=True)
            yield f"Error: {e}"

    return StreamingResponse(_stream_generator(), media_type="text/plain")


@router.post("/missions", response_model=MissionResponse, summary="Launch Mission")
async def create_mission_endpoint(
    request: MissionCreate,
    background_tasks: BackgroundTasks,
    req: Request,
    db: AsyncSession = Depends(get_db),
) -> MissionResponse:
    correlation_id = req.headers.get("X-Correlation-ID") or str(uuid.uuid4())
    logger.info(f"Orchestrator: Creating mission with Correlation ID: {correlation_id}")

    try:
        mission = await start_mission(
            session=db,
            objective=request.objective,
            initiator_id=1,  # Default system user for now, or extract from token if forwarded
            context=request.context,
            force_research=False,
            idempotency_key=correlation_id,
        )

        return _serialize_mission(mission)

    except Exception as e:
        logger.error(f"Failed to create mission: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.get("/missions/{mission_id}", response_model=MissionResponse, summary="Get Mission")
async def get_mission_endpoint(
    mission_id: int, req: Request, db: AsyncSession = Depends(get_db)
) -> MissionResponse:
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
    mission_id: int, req: Request, db: AsyncSession = Depends(get_db)
) -> list[MissionEventResponse]:
    """
    Retrieve historical events for a mission.
    """
    state_manager = MissionStateManager(db)
    events = await state_manager.get_mission_events(mission_id)

    return [
        MissionEventResponse(
            event_type=(
                evt.event_type.value if hasattr(evt.event_type, "value") else str(evt.event_type)
            ),
            mission_id=evt.mission_id,
            timestamp=evt.created_at,
            payload=evt.payload_json or {},
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
        async with async_session_factory() as session:
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
        async for event in subscription:
            payload = {}
            evt_type = ""

            if isinstance(event, dict):
                # Check structure from Redis (published by log_event or entrypoint)
                # entrypoint might publish raw dicts?
                # MissionStateManager.log_event publishes to Redis.
                # Let's assume it matches what we expect
                payload = event.get("payload_json", {}) or event.get("data", {})
                evt_type = event.get("event_type", "")

            await websocket.send_json(
                {"type": "mission_event", "payload": {"event_type": evt_type, "data": payload}}
            )

            if evt_type in ("mission_completed", "mission_failed"):
                # Fetch final status
                async with async_session_factory() as final_session:
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
        # Subscription is a generator, we just break loop to stop it,
        # but cleanup of redis pubsub happens in generator finally block if we break?
        # Python async generators support cleanup on garbage collection or aclose()
        # Ideally we should use `async with` on the generator if it supported it, or manually close.
        # My implementation of subscribe uses try/finally. If we break, `finally` runs?
        # Yes, if we stop iterating, the generator is closed.
        pass
