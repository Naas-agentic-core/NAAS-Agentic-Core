import logging
import uuid

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
from langchain_core.messages import HumanMessage
from pydantic import BaseModel, Field
from sqlalchemy import text
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
    MissionCreate,
    MissionEventResponse,
    MissionResponse,
)
from microservices.orchestrator_service.src.services.overmind.entrypoint import start_mission
from microservices.orchestrator_service.src.services.overmind.graph.main import create_unified_graph
from microservices.orchestrator_service.src.services.overmind.state import MissionStateManager
from typing import Any

from microservices.orchestrator_service.src.services.overmind.utils.tools import tool_registry
from microservices.orchestrator_service.src.contracts.admin_tools import ADMIN_TOOL_CONTRACT
from microservices.orchestrator_service.src.services.tools.registry import get_registry

logger = logging.getLogger(__name__)

router = APIRouter(
    tags=["Overmind (Super Agent)"],
)

# MCP Admin Tool Endpoints dynamically generated from contract
for tool_name in ADMIN_TOOL_CONTRACT.keys():

    @router.post(f"/api/v1/tools/{tool_name}/invoke", tags=["Admin MCP Tools"])
    async def invoke_admin_tool(payload: dict[str, Any] = {}, name=tool_name) -> dict[str, Any]:
        tool_fn = get_registry().get(name)
        if not tool_fn:
            raise HTTPException(status_code=404, detail="Tool not found in registry")

        try:
            import asyncio
            if hasattr(tool_fn, "ainvoke"):
                result = await tool_fn.ainvoke(payload)
            elif asyncio.iscoroutinefunction(tool_fn) or asyncio.iscoroutinefunction(getattr(tool_fn, "invoke", None)):
                result = await tool_fn(**payload)
            elif hasattr(tool_fn, "invoke"):
                result = tool_fn.invoke(payload)
            else:
                result = tool_fn(**payload)

            return {"status": "success", "result": result}
        except Exception as e:
            return {"status": "error", "message": str(e)}

    @router.get(f"/api/v1/tools/{tool_name}/schema", tags=["Admin MCP Tools"])
    async def get_admin_tool_schema(name=tool_name) -> dict[str, Any]:
        return {
            "name": name,
            "description": ADMIN_TOOL_CONTRACT.get(name),
            "parameters": {}
        }

    @router.get(f"/api/v1/tools/{tool_name}/health", tags=["Admin MCP Tools"])
    async def get_admin_tool_health(name=tool_name) -> dict[str, Any]:
        tool_fn = get_registry().get(name)
        return {
            "name": name,
            "status": "healthy" if tool_fn else "unavailable"
        }


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
        else text(
            "SELECT id FROM customer_conversations WHERE id=:conversation_id AND user_id=:user_id"
        )
    )
    create_query = (
        text(
            "INSERT INTO admin_conversations (title, user_id) VALUES (:title, :user_id) RETURNING id"
        )
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


import asyncio


async def _stream_chat_langgraph(
    websocket: WebSocket,
    objective: str,
    context: dict[str, Any],
    chat_scope: str,
    conversation_id: int,
) -> None:
    """يشغّل LangGraph الموحد لمسارات البحث والإدارة ويبث الأحداث."""
    queue: asyncio.Queue[dict[str, object]] = asyncio.Queue()

    async def _runner():
        try:
            app_graph = create_unified_graph()
            config = {"configurable": {"thread_id": str(conversation_id)}}
            inputs = {"query": objective, "messages": [HumanMessage(content=objective)]}

            res = await app_graph.ainvoke(inputs, config=config)

            await queue.put({"type": "__DONE__", "result": res})
        except Exception as e:
            await queue.put({"type": "__ERROR__", "error": str(e)})

    task = asyncio.create_task(_runner())
    _task_ref = task  # store reference to avoid GC

    from datetime import UTC, datetime

    now = datetime.now(UTC).isoformat()
    await websocket.send_json(
        {
            "type": "RUN_STARTED",
            "payload": {
                "run_id": "sync-run",
                "seq": 1,
                "timestamp": now,
                "iteration": 0,
                "mode": context.get("mission_type", "auto"),
            },
        }
    )

    final_content = ""
    while True:
        evt = await queue.get()
        if evt["type"] == "__DONE__":
            run_data = evt["result"]

            # Extract the final response from our custom Unified Graph output
            final_resp = run_data.get("final_response")

            if isinstance(final_resp, dict):
                import json

                response_text = json.dumps(final_resp, ensure_ascii=False)
            else:
                response_text = str(final_resp or "لا توجد تفاصيل متاحة.")

            final_content = response_text
            await websocket.send_json(
                {
                    "type": "assistant_final",
                    "payload": {
                        "content": response_text,
                        "status": "ok",
                        "run_id": "sync-run",
                        "timeline": [],
                        "graph_mode": "unified_stategraph",
                        "route_id": f"chat_ws_{chat_scope}",
                    },
                }
            )
            break
        if evt["type"] == "__ERROR__":
            final_content = f"❌ خطأ أثناء التنفيذ: {evt['error']}"
            await websocket.send_json(
                {"type": "assistant_error", "payload": {"content": final_content}}
            )
            break
        if evt["type"] == "phase_start":
            phase_name = evt["payload"].get("phase", "") if isinstance(evt["payload"], dict) else ""
            agent_name = evt["payload"].get("agent", "") if isinstance(evt["payload"], dict) else ""
            await websocket.send_json(
                {
                    "type": "PHASE_STARTED",
                    "payload": {
                        "run_id": "sync-run",
                        "seq": 2,
                        "phase": phase_name,
                        "agent": agent_name,
                        "timestamp": datetime.now(UTC).isoformat(),
                    },
                }
            )
            await websocket.send_json(
                {
                    "type": "assistant_delta",
                    "payload": {"content": f"🔄 جاري التنفيذ: {phase_name}\n"},
                }
            )
        elif evt["type"] == "phase_completed":
            phase_name = evt["payload"].get("phase", "") if isinstance(evt["payload"], dict) else ""
            agent_name = evt["payload"].get("agent", "") if isinstance(evt["payload"], dict) else ""
            await websocket.send_json(
                {
                    "type": "PHASE_COMPLETED",
                    "payload": {
                        "run_id": "sync-run",
                        "seq": 3,
                        "phase": phase_name,
                        "agent": agent_name,
                        "timestamp": datetime.now(UTC).isoformat(),
                    },
                }
            )
        elif evt["type"] == "loop_start":
            iteration = (
                evt["payload"].get("iteration", 0) if isinstance(evt["payload"], dict) else 0
            )
            mode = (
                evt["payload"].get("graph_mode", "standard")
                if isinstance(evt["payload"], dict)
                else "standard"
            )
            await websocket.send_json(
                {
                    "type": "RUN_STARTED",
                    "payload": {
                        "run_id": f"sync-run:{iteration}",
                        "seq": 4,
                        "timestamp": datetime.now(UTC).isoformat(),
                        "iteration": iteration,
                        "mode": mode,
                    },
                }
            )
        else:
            await websocket.send_json(evt)

    await websocket.send_json({"type": "complete", "payload": {}})

    if final_content.strip():
        await _persist_assistant_message(
            chat_scope=chat_scope,
            conversation_id=conversation_id,
            content=final_content,
            mission_id=None,
        )


async def _run_chat_langgraph(
    objective: str,
    context: dict[str, Any],
) -> dict[str, object]:
    """يشغّل LangGraph كعمود فقري لرحلة chat ويعيد حمولة موحدة قابلة للبث (HTTP legacy fallback)."""
    app_graph = create_unified_graph()
    config = {"configurable": {"thread_id": "http_run"}}
    inputs = {"query": objective, "messages": [HumanMessage(content=objective)]}

    res = await app_graph.ainvoke(inputs, config=config)
    final_resp = res.get("final_response")

    if isinstance(final_resp, dict):
        import json

        response_text = json.dumps(final_resp, ensure_ascii=False)
    else:
        response_text = str(final_resp or "لا توجد تفاصيل متاحة.")

    return {
        "status": "ok",
        "response": response_text,
        "run_id": "http-run",
        "timeline": [],
        "graph_mode": "unified_stategraph",
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
    context: dict[str, Any] = {}
    if isinstance(context_payload, dict):
        for key, value in context_payload.items():
            if not isinstance(key, str):
                continue
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

            requested_conversation_id = incoming.get("conversation_id")
            conversation_id = (
                requested_conversation_id if isinstance(requested_conversation_id, int) else None
            )
            try:
                conversation_id = await _ensure_conversation(
                    chat_scope="customer",
                    user_id=user_id,
                    question=objective,
                    requested_conversation_id=conversation_id,
                )
            except HTTPException as error:
                await websocket.send_json(
                    {"type": "assistant_error", "payload": {"content": error.detail}}
                )
                continue

            await websocket.send_json(
                {
                    "type": "conversation_init",
                    "payload": {"conversation_id": conversation_id},
                }
            )

            context_payload = incoming.get("context")
            context: dict[str, Any] = {}
            if isinstance(context_payload, dict):
                for key, value in context_payload.items():
                    if not isinstance(key, str):
                        continue
                    context[key] = value

            if "mission_type" in incoming:
                context["mission_type"] = incoming["mission_type"]
            elif (
                "metadata" in incoming
                and isinstance(incoming["metadata"], dict)
                and "mission_type" in incoming["metadata"]
            ):
                context["mission_type"] = incoming["metadata"]["mission_type"]

            await _stream_chat_langgraph(
                websocket,
                objective=objective,
                context=context,
                chat_scope="customer",
                conversation_id=conversation_id,
            )

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

            requested_conversation_id = incoming.get("conversation_id")
            conversation_id = (
                requested_conversation_id if isinstance(requested_conversation_id, int) else None
            )
            try:
                conversation_id = await _ensure_conversation(
                    chat_scope="admin",
                    user_id=user_id,
                    question=objective,
                    requested_conversation_id=conversation_id,
                )
            except HTTPException as error:
                await websocket.send_json(
                    {"type": "assistant_error", "payload": {"content": error.detail}}
                )
                continue

            await websocket.send_json(
                {
                    "type": "conversation_init",
                    "payload": {"conversation_id": conversation_id},
                }
            )

            context_payload = incoming.get("context")
            context: dict[str, Any] = {}
            if isinstance(context_payload, dict):
                for key, value in context_payload.items():
                    if not isinstance(key, str):
                        continue
                    context[key] = value

            if "mission_type" in incoming:
                context["mission_type"] = incoming["mission_type"]
            elif (
                "metadata" in incoming
                and isinstance(incoming["metadata"], dict)
                and "mission_type" in incoming["metadata"]
            ):
                context["mission_type"] = incoming["metadata"]["mission_type"]

            await _stream_chat_langgraph(
                websocket,
                objective=objective,
                context=context,
                chat_scope="admin",
                conversation_id=conversation_id,
            )

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
