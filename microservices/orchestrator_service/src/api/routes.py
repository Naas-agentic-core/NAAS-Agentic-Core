import asyncio
import json
import logging
import os
import re
import time
import uuid
from collections.abc import AsyncGenerator
from contextlib import suppress
from typing import TypedDict

import anyio
import httpx
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
from langchain_core.messages import AIMessage, HumanMessage
from cachetools import TTLCache
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from microservices.orchestrator_service.src.api.context_utils import (
    _extract_client_context_messages,
    _merge_history_with_client_context,
)
from microservices.orchestrator_service.src.contracts.admin_tools import ADMIN_TOOL_CONTRACT
from microservices.orchestrator_service.src.core.config import get_settings
from microservices.orchestrator_service.src.core.database import (
    async_session_factory,
    get_checkpointer,
    get_db,
)
from microservices.orchestrator_service.src.core.event_bus import get_event_bus
from microservices.orchestrator_service.src.core.security import (
    decode_user_id,
    extract_bearer_token,
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
from microservices.orchestrator_service.src.services.overmind.graph import create_unified_graph
from microservices.orchestrator_service.src.services.overmind.state import MissionStateManager
from microservices.orchestrator_service.src.services.overmind.utils.tools import tool_registry
from microservices.orchestrator_service.src.services.tools.registry import get_registry

logger = logging.getLogger(__name__)

active_background_tasks = set()
MAX_HISTORY_MESSAGES = 24
MAX_CHECKPOINT_ANCHOR_MESSAGES = 4
MAX_HISTORY_SUMMARY_MESSAGES = 40
MAX_HISTORY_SUMMARY_CHARS = 2400
MAX_HISTORY_SUMMARY_ITEMS = 18

type JsonObject = dict[str, object]


class ChatRunContext(TypedDict, total=False):
    """غلاف سياقي محدود لمسار تشغيل الدردشة لتجنّب القواميس المفتوحة في الحدود الحرجة."""

    mission_type: str
    conversation_id: int | str
    thread_id: int | str
    session_id: int | str
    user_id: int


class MissionEventEnvelope(TypedDict):
    """العقد الداخلي القياسي لبث أحداث المهمات عبر WebSocket."""

    event_type: str
    data: dict[str, object]


class StreamFrame(BaseModel):
    """يمثل إطارًا موحّدًا لبث الدردشة ويفصل نص المستخدم عن الإشارات التحكمية."""

    type: str
    payload: dict[str, object] = Field(default_factory=dict)


def _compress_text_for_context(content: str) -> str:
    """يضغط النص للسياق عبر إزالة الضوضاء وتوحيد المسافات وتقليص الطول."""
    collapsed = " ".join(content.replace("\x00", "").split())
    cleaned = collapsed.replace("```", "").strip()
    if len(cleaned) <= 260:
        return cleaned
    return f"{cleaned[:260]}…"


def _build_older_history_digest(rows: list[object]) -> str:
    """يبني ملخصًا موجزًا للرسائل الأقدم مع إزالة التكرارات البنيوية."""
    if not rows:
        return ""

    digest_items: list[str] = []
    seen: set[str] = set()
    current_size = 0
    for old_message in rows:
        role_value = getattr(old_message, "role", "")
        content_value = getattr(old_message, "content", "")
        role_label = "المستخدم" if str(role_value) == "user" else "المساعد"
        compact = _compress_text_for_context(str(content_value))
        if not compact:
            continue
        item = f"- {role_label}: {compact}"
        fingerprint = item.casefold()
        if fingerprint in seen:
            continue
        allowed = MAX_HISTORY_SUMMARY_CHARS - current_size
        if allowed <= 0:
            break
        if len(item) > allowed:
            item = f"{item[:allowed]}…"
        digest_items.append(item)
        seen.add(fingerprint)
        current_size += len(item)
        if len(digest_items) >= MAX_HISTORY_SUMMARY_ITEMS:
            break
    return "\n".join(digest_items)


def _build_langchain_messages(
    source_messages: list[dict[str, str]] | None,
) -> list[HumanMessage | AIMessage]:
    """يبني نافذة سياق محدودة ويزيل التكرارات المتجاورة لتقليل تلوث السياق."""
    if not source_messages:
        return []

    normalized_messages: list[HumanMessage | AIMessage] = []
    last_signature: tuple[str, str] | None = None
    for message in source_messages[-MAX_HISTORY_MESSAGES:]:
        role = message.get("role")
        content = str(message.get("content", "")).strip()
        if role not in {"user", "assistant"} or not content:
            continue
        signature = (role, content)
        if signature == last_signature:
            continue
        if role == "user":
            normalized_messages.append(HumanMessage(content=content))
        else:
            normalized_messages.append(AIMessage(content=content))
        last_signature = signature
    return normalized_messages


def _build_graph_messages(
    *,
    objective: str,
    history_messages: list[dict[str, str]] | None,
    checkpointer_available: bool,
    checkpoint_has_state: bool,
) -> list[HumanMessage | AIMessage]:
    """يبني رسائل الإدخال للرسم البياني مع مسار احتياطي صريح ضد عمى السياق."""
    latest_user_message = HumanMessage(content=objective)
    if checkpointer_available and checkpoint_has_state:
        # Prevent context amnesia and exponential message duplication in LangGraph
        # by relying purely on the checkpointer to manage history. Do not inject manually.
        return [latest_user_message]

    # عند غياب checkpointer (أو تعطل تهيئته)، نمرّر نافذة تاريخية محدودة صراحةً.
    seeded_history = _build_langchain_messages(history_messages)
    seeded_history.append(latest_user_message)
    return seeded_history


def _question_contains_explicit_entity(question: str) -> bool:
    """يتحقق مما إذا كان السؤال يحتوي كيانًا صريحًا بدل الضمير المرجعي."""
    normalized = question.strip()
    if not normalized:
        return False

    if re.search(r"\b(?:france|algeria|egypt|morocco|tunisia|germany|spain)\b", normalized, re.I):
        return True

    arabic_tokens = [
        token.strip("؟،.!:؛") for token in re.findall(r"[\u0600-\u06FF]+", normalized) if token
    ]
    arabic_tokens = [token for token in arabic_tokens if token]
    if not arabic_tokens:
        return False

    stop_words = {
        "ما",
        "ماذا",
        "من",
        "هي",
        "هو",
        "هل",
        "كم",
        "عدد",
        "في",
        "على",
        "عن",
        "الى",
        "إلى",
        "هذه",
        "هذا",
        "ذلك",
        "تلك",
        "الدولة",
        "البلد",
        "المدينة",
        "عاصمة",
        "عاصمتها",
        "سكانها",
        "عددها",
        "عددهم",
        "موقعها",
        "مساحتها",
        "حدثني",
        "اخبرني",
        "أخبرني",
        "قل",
        "تكلم",
        "احك",
    }
    return any(token not in stop_words and len(token) > 2 for token in arabic_tokens)


def _extract_recent_entity_anchor(history_messages: list[dict[str, str]] | None) -> str | None:
    """يستخرج مرساة كيان حديثة من آخر رسائل المستخدم كحل احتياطي ضد فقدان السياق."""
    if not history_messages:
        return None

    stop_words = {
        "و",
        "ما",
        "وما",
        "ماذا",
        "وماذا",
        "من",
        "هي",
        "هو",
        "هل",
        "كم",
        "عدد",
        "في",
        "على",
        "عن",
        "الى",
        "إلى",
        "هذه",
        "هذا",
        "ذلك",
        "تلك",
        "عاصمتها",
        "سكانها",
        "عددها",
        "موقعها",
        "مساحتها",
    }

    for message in reversed(history_messages):
        if message.get("role") != "user":
            continue
        content = str(message.get("content", "")).strip()
        if not content:
            continue

        english_entities = re.findall(
            r"\b(?:France|Algeria|Egypt|Morocco|Tunisia|Germany|Spain)\b",
            content,
            flags=re.IGNORECASE,
        )
        if english_entities:
            return english_entities[-1]

        arabic_tokens = [
            token.strip("؟،.!:؛") for token in re.findall(r"[\u0600-\u06FF]+", content) if token
        ]
        arabic_tokens = [token for token in arabic_tokens if token]
        candidate_tokens = [
            token for token in arabic_tokens if len(token) > 2 and token not in stop_words
        ]
        if not candidate_tokens:
            continue

        tail = candidate_tokens[-3:]
        return " ".join(tail)
    return None


def _augment_ambiguous_objective(
    objective: str,
    history_messages: list[dict[str, str]] | None,
) -> str:
    """يعزّز السؤال الإحالي بمرساة كيان صريحة قبل تمريره للنموذج."""
    normalized = objective.strip()
    if not normalized:
        return normalized
    if not _is_ambiguous_followup(normalized):
        return normalized
    if _question_contains_explicit_entity(normalized):
        return normalized

    anchor = _extract_recent_entity_anchor(history_messages)
    if not anchor:
        return normalized
    return f"{normalized}\n\nمرجع سياقي إلزامي: الكيان المقصود في هذا السؤال هو: {anchor}."


async def _detect_checkpoint_state(thread_id: str) -> tuple[bool, bool]:
    """يفحص توفّر checkpointer ووجود حالة محفوظة للخيط الحالي بشكل آمن."""
    checkpointer = get_checkpointer()
    if checkpointer is None:
        return False, False

    try:
        checkpoint_config = {"configurable": {"thread_id": thread_id}}
        async with asyncio.timeout(1.5):
            checkpoint_tuple = await checkpointer.aget_tuple(checkpoint_config)
        return True, checkpoint_tuple is not None
    except Exception as exc:
        logger.warning(
            "[CHECKPOINTER] state probe failed for thread_id=%s; falling back to injected history. reason=%s",
            thread_id,
            exc,
        )
        return False, False


def _is_ambiguous_followup(query: str) -> bool:
    """يكتشف الاستعلامات الإحالية القصيرة التي تحتاج سياقًا صريحًا."""
    normalized = query.strip().casefold()
    if not normalized:
        return False
    triggers = (
        "عاصمتها",
        "عاصمته",
        "عاصمتهم",
        "عدد سكانها",
        "عدد سكانه",
        "سكانها",
        "سكانه",
        "موقعها",
        "موقعه",
        "اين تقعها",
        "أين تقعها",
        "where is it",
        "where is she",
        "where is he",
        "what is its population",
        "how many people live there",
        "what is its",
        "its capital",
        "their capital",
    )
    if any(trigger in normalized for trigger in triggers):
        return True

    demonstratives = ("هذا", "هذه", "ذلك", "تلك", "هاته", "there", "this", "that")
    followup_nouns = (
        "الدولة",
        "البلد",
        "المدينة",
        "الكيان",
        "الدالة",
        "المعادلة",
        "التمرين",
        "السؤال",
        "function",
        "equation",
        "problem",
    )
    if any(word in normalized for word in demonstratives) and any(
        noun in normalized for noun in followup_nouns
    ):
        return True

    vague_leads = ("كيف جاءت", "كيف حصل", "كيف صارت", "لماذا جاءت", "كيف طلعت")
    if any(normalized.startswith(prefix) for prefix in vague_leads):
        return True

    tokens = normalized.split()
    pronoun_like_terms = {
        "عاصمتها",
        "عاصمته",
        "عاصمتهم",
        "عاصمتها؟",
        "عاصمته؟",
        "عاصمتهم؟",
        "سكانها",
        "سكانه",
        "سكانها؟",
        "سكانه؟",
        "عددهم",
        "عددها",
    }
    if len(tokens) <= 6 and any(token in pronoun_like_terms for token in tokens):
        return True

    return (
        any(len(token) > 2 and token.endswith(("ها", "هم")) for token in tokens)
        and len(tokens) <= 8
    )


def _canonicalize_mission_event(event: object) -> MissionEventEnvelope | None:
    """يوحّد أشكال الحدث التاريخية إلى غلاف داخلي ثابت مع توافق رجعي عند الحافة."""

    if not isinstance(event, dict):
        return None

    raw_event_type = event.get("event_type")
    if not isinstance(raw_event_type, str) or not raw_event_type.strip():
        return None

    payload_candidate = event.get("payload_json")
    if not isinstance(payload_candidate, dict):
        payload_candidate = event.get("data")
    if not isinstance(payload_candidate, dict):
        payload_candidate = {}

    return {"event_type": raw_event_type, "data": payload_candidate}


async def _append_telemetry_line(line: str) -> None:
    """يكتب سطر تتبع حرج إلى ملف أدلة قابل للفحص خارج مخرجات الطرفية."""

    def write_sync():
        import os

        path = os.path.join(os.getenv("STATE_DIR", "/app"), "telemetry_evidence.txt")
        with open(path, "a", encoding="utf-8") as telemetry_file:
            telemetry_file.write(f"{line}\n")

    import anyio

    await anyio.to_thread.run_sync(write_sync)


router = APIRouter(
    tags=["Overmind (Super Agent)"],
)

_conv_service_client: httpx.AsyncClient | None = None


async def get_conv_service_client() -> httpx.AsyncClient:
    global _conv_service_client
    if _conv_service_client is None or _conv_service_client.is_closed:
        _conv_service_client = httpx.AsyncClient(
            base_url=os.getenv("CONVERSATION_SERVICE_URL", "http://conversation-service:8010"),
            timeout=10.0,
            limits=httpx.Limits(max_connections=20, max_keepalive_connections=10),
        )
    return _conv_service_client


async def close_conv_service_client() -> None:
    global _conv_service_client
    if _conv_service_client and not _conv_service_client.is_closed:
        await _conv_service_client.aclose()


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


def _is_admin_payload(payload: dict[str, object]) -> bool:
    """يتحقق من صلاحيات الإدارة داخل حمولة JWT وفق مبدأ أقل صلاحية وfail-closed."""
    role = str(payload.get("role", "")).lower().strip()
    scope_text = str(payload.get("scope", "")).lower()
    has_admin_role = role in {"admin", "super_admin", "superadmin"}
    has_admin_flag = payload.get("is_admin") is True
    has_admin_scope = "admin" in scope_text and "tool" in scope_text
    return has_admin_role or has_admin_flag or has_admin_scope


def _coerce_admin_state(payload: dict[str, object] | None = None) -> dict[str, object]:
    """يبني حالة إدارة ضيقة ومتوافقة لعقدة التحكم دون توسيع الواجهة العامة."""

    safe_payload = payload or {}
    role = str(safe_payload.get("role", "")).strip().lower()
    scope = str(safe_payload.get("scope", "")).strip().lower()
    is_admin = _is_admin_payload(safe_payload)
    return {
        "is_admin": is_admin,
        "user_role": role,
        "scope": scope,
    }


def _merge_admin_inputs(
    base_inputs: dict[str, object], admin_payload: dict[str, object] | None
) -> dict[str, object]:
    """يحقن غلاف الإدارة الموحد فقط عند الحاجة، مع إبقاء المسارات الأخرى دون تغيير."""

    if admin_payload is None:
        return base_inputs
    return {**base_inputs, **_coerce_admin_state(admin_payload)}


async def require_internal_admin_access(
    authorization: str | None = Header(default=None),
    x_internal_admin_key: str | None = Header(default=None),
) -> int:
    """يفرض مصادقة وتفويضاً مغلقين لمسارات الأدوات عبر مفتاح داخلي أو JWT إداري صريح."""
    settings = get_settings()

    if (
        x_internal_admin_key
        and settings.ADMIN_TOOL_API_KEY
        and x_internal_admin_key == settings.ADMIN_TOOL_API_KEY
    ):
        return 0

    token = extract_bearer_token(authorization)
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=["HS256"])
    except jwt.PyJWTError as exc:
        raise HTTPException(status_code=401, detail="Invalid token") from exc

    if not _is_admin_payload(payload):
        raise HTTPException(status_code=403, detail="forbidden")

    user_id = decode_user_id(token, settings.SECRET_KEY)
    if user_id <= 0:
        raise HTTPException(status_code=403, detail="forbidden")
    return user_id


def _safe_assistant_error(request_id: str) -> str:
    """يبني رسالة خطأ آمنة للمستخدم دون أي تسريب تشخيصي داخلي."""
    return f"تعذر معالجة طلب الدردشة حالياً. رقم المتابعة: {request_id}"


def _safe_conversation_id(raw_value: object) -> int | None:
    """يحوّل conversation_id بشكل آمن لدعم int أو string رقمي مع تتبع تشخيصي واضح."""
    if raw_value is None:
        return None
    if isinstance(raw_value, int):
        return raw_value
    if isinstance(raw_value, str):
        stripped = raw_value.strip()
        if not stripped:
            return None
        try:
            parsed = int(stripped)
            logger.warning(
                "[CONV_ID_TYPE] Received conversation_id as string '%s' and converted to int=%s",
                raw_value,
                parsed,
            )
            return parsed
        except ValueError:
            logger.error(
                "[CONV_ID_TYPE] Invalid numeric conversion for conversation_id='%s'; using None",
                raw_value,
            )
            return None

    logger.error(
        "[CONV_ID_TYPE] Unexpected conversation_id type=%s; using None",
        type(raw_value).__name__,
    )
    return None


def _resolve_effective_conversation_id(
    *, incoming_value: object, sticky_value: int | None
) -> int | None:
    """يحدّد conversation_id النهائي مع أولوية للطلب الحالي ثم ذاكرة الاتصال."""
    parsed = _safe_conversation_id(incoming_value)
    if parsed is not None:
        return parsed
    return sticky_value


def _safe_thread_id(raw_value: object) -> str | None:
    """يطبّع thread_id لدعم int/str مع رفض القيم الفارغة."""
    if raw_value is None:
        return None
    if isinstance(raw_value, int):
        return str(raw_value)
    if isinstance(raw_value, str):
        normalized = raw_value.strip()
        if normalized:
            return normalized
    return None


def _resolve_thread_id(context: ChatRunContext, fallback_conversation_id: int | str) -> str:
    """يستخرج thread_id ثابتًا من السياق مع عزل المستخدم."""
    explicit = _safe_thread_id(context.get("thread_id"))
    if explicit:
        return explicit

    conv_id = context.get("conversation_id", fallback_conversation_id)
    user_id = context.get("user_id")
    if user_id is None:
        raise ValueError(
            f"[THREAD_RESOLUTION] user_id required for safe thread binding. conv_id={conv_id!r}"
        )
    return f"u{user_id}:c{conv_id}"


def _decode_auth_payload_or_401(authorization: str | None) -> tuple[int, dict[str, object]]:
    """يفك JWT من ترويسة Authorization ويعيد user_id والحمولة مع فشل مغلق."""
    token = extract_bearer_token(authorization)
    settings = get_settings()
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=["HS256"])
    except jwt.PyJWTError as exc:
        raise HTTPException(status_code=401, detail="Invalid token") from exc
    user_id = int(payload.get("sub", payload.get("user_id", 0)) or 0)
    if user_id <= 0:
        raise HTTPException(status_code=401, detail="Invalid user")
    return user_id, payload


async def _serialize_json_async(payload: object) -> str:
    """يُسلسل الحمولة إلى JSON داخل خيط منفصل لحماية حلقة الأحداث من الحجب."""
    return await anyio.to_thread.run_sync(lambda p: json.dumps(p, ensure_ascii=False), payload)


async def _serialize_stream_frame(payload: object) -> str:
    """يبني NDJSON صارمًا لضمان عدم تسريب dict خام إلى عميل البث النصي."""
    return _serialize_stream_frame_sync(payload)


def _serialize_stream_frame_sync(payload: object) -> str:
    """سريع، متزامن، آمن لـ event loop."""
    if isinstance(payload, dict):
        frame = StreamFrame.model_validate(payload).model_dump()
    else:
        frame = StreamFrame(type="assistant_delta", payload={"content": str(payload)}).model_dump()
    return json.dumps(frame, ensure_ascii=False) + "\n"


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


def _extract_chat_objective(payload: dict[str, object]) -> str | None:
    """يستخلص الهدف النصي للدردشة من حمولة عامة بشكل صريح وآمن."""
    question = payload.get("question")
    if isinstance(question, str) and question.strip():
        return question.strip()
    objective = payload.get("objective")
    if isinstance(objective, str) and objective.strip():
        return objective.strip()
    return None


async def _create_new_conversation(
    user_id: int, question: str, is_admin_scope: bool, session: AsyncSession
) -> int:
    create_query = (
        text(
            "INSERT INTO admin_conversations (title, user_id) VALUES (:title, :user_id) RETURNING id"
        )
        if is_admin_scope
        else text(
            "INSERT INTO customer_conversations (title, user_id) VALUES (:title, :user_id) RETURNING id"
        )
    )
    title = question.strip()[:120] or "Super Agent Mission"
    try:
        async with asyncio.timeout(5.0):
            created = await session.execute(create_query, {"title": title, "user_id": user_id})
    except TimeoutError as e:
        raise HTTPException(
            status_code=504, detail="Database timeout during conversation creation"
        ) from e
    created_id = created.scalar_one_or_none()
    if created_id is None:
        raise HTTPException(status_code=500, detail="failed to create conversation")
    return int(created_id)


_last_imported_count: TTLCache = TTLCache(maxsize=10_000, ttl=3600)


async def _lazy_import_history_with_retry(
    *,
    conversation_id: int,
    user_id: int,
    conv_metadata: dict[str, str],
    messages: list[dict[str, str]],
    max_attempts: int = 3,
) -> None:
    """يحاول استيراد التاريخ إلى conversation-service مع إعادة المحاولة قبل الفشل."""
    already_imported = _last_imported_count.get(conversation_id, 0)
    if len(messages) <= already_imported:
        return

    delta_messages = messages[already_imported:]

    payload = {
        "conversation_id": conversation_id,
        "user_id": user_id,
        "idempotency_key": f"{conversation_id}:{user_id}:{len(messages)}",
        "max_messages": 50,
        "conversation_metadata": conv_metadata,
        "messages": delta_messages,
    }
    last_error: Exception | None = None
    for attempt in range(1, max_attempts + 1):
        try:
            client = await get_conv_service_client()
            resp = await client.post("/api/v1/conversations/import", json=payload)
            resp.raise_for_status()
            data = resp.json()
            if data.get("status") not in {"imported", "already_exists"}:
                raise ValueError(f"Unexpected import status: {data.get('status')}")
            _last_imported_count[conversation_id] = len(messages)
            return
        except Exception as exc:
            last_error = exc
            if attempt < max_attempts:
                wait_seconds = 0.5 * attempt
                logger.warning(
                    "[HISTORY_RETRY] attempt=%s/%s failed for conv=%s user=%s error=%s; retrying in %.1fs",
                    attempt,
                    max_attempts,
                    conversation_id,
                    user_id,
                    exc,
                    wait_seconds,
                )
                await asyncio.sleep(wait_seconds)
            else:
                logger.error(
                    "[HISTORY_RETRY] all attempts failed for conv=%s user=%s: %s",
                    conversation_id,
                    user_id,
                    last_error,
                )
    if last_error is not None:
        raise last_error


async def _ensure_conversation(
    *,
    chat_scope: str,
    user_id: int,
    question: str,
    requested_conversation_id: int | None,
) -> tuple[int, list[dict[str, str]]]:
    """ينشئ أو يتحقق من المحادثة ويحفظ رسالة المستخدم لضمان اتساق التاريخ."""
    is_admin_scope = chat_scope == "admin"
    check_query = (
        text(
            "SELECT id, title, created_at FROM admin_conversations WHERE id=:conversation_id AND user_id=:user_id"
        )
        if is_admin_scope
        else text(
            "SELECT id, title, created_at FROM customer_conversations WHERE id=:conversation_id AND user_id=:user_id"
        )
    )
    get_messages_query = (
        text(
            """
            SELECT id, role, content, created_at
            FROM (
                SELECT id, role, content, created_at
                FROM admin_messages
                WHERE conversation_id=:conversation_id
                ORDER BY id DESC
                LIMIT :history_limit
            ) recent
            ORDER BY id ASC
            """
        )
        if is_admin_scope
        else text(
            """
            SELECT id, role, content, created_at
            FROM (
                SELECT id, role, content, created_at
                FROM customer_messages
                WHERE conversation_id=:conversation_id
                ORDER BY id DESC
                LIMIT :history_limit
            ) recent
            ORDER BY id ASC
            """
        )
    )
    get_older_messages_query = (
        text(
            """
            SELECT id, role, content
            FROM admin_messages
            WHERE conversation_id=:conversation_id
              AND id < :min_recent_id
            ORDER BY id DESC
            LIMIT :summary_limit
            """
        )
        if is_admin_scope
        else text(
            """
            SELECT id, role, content
            FROM customer_messages
            WHERE conversation_id=:conversation_id
              AND id < :min_recent_id
            ORDER BY id DESC
            LIMIT :summary_limit
            """
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

    messages: list[dict[str, str]] = []
    conversation_id = requested_conversation_id
    conv_metadata_to_import: dict[str, str] | None = None
    messages_to_import: list[dict[str, str]] = []

    async with async_session_factory() as session:
        if conversation_id is not None:
            try:
                async with asyncio.timeout(5.0):
                    result = await session.execute(
                        check_query,
                        {"conversation_id": conversation_id, "user_id": user_id},
                    )
            except TimeoutError as e:
                raise HTTPException(
                    status_code=504, detail="Database timeout checking conversation"
                ) from e
            conv_row = result.fetchone()
            if conv_row is None:
                raise HTTPException(status_code=403, detail="conversation does not belong to user")

            try:
                try:
                    async with asyncio.timeout(5.0):
                        messages_res = await session.execute(
                            get_messages_query,
                            {
                                "conversation_id": conversation_id,
                                "history_limit": MAX_HISTORY_MESSAGES,
                            },
                        )
                except TimeoutError as e:
                    raise HTTPException(
                        status_code=504, detail="Database timeout retrieving messages"
                    ) from e
                messages_rows = messages_res.fetchall()

                messages = [
                    {
                        "role": str(m.role),
                        "content": str(m.content),
                        "created_at": m.created_at.isoformat(),
                    }
                    for m in messages_rows
                ]

                min_id = min(m.id for m in messages_rows) if messages_rows else 0
                older_messages_rows = []
                if min_id > 0:
                    async with asyncio.timeout(5.0):
                        older_messages_res = await session.execute(
                            get_older_messages_query,
                            {
                                "conversation_id": conversation_id,
                                "min_recent_id": min_id,
                                "summary_limit": MAX_HISTORY_SUMMARY_MESSAGES,
                            },
                        )
                    older_messages_rows = list(reversed(older_messages_res.fetchall()))
                if older_messages_rows:
                    digest = _build_older_history_digest(older_messages_rows)
                    if digest:
                        messages.insert(
                            0,
                            {
                                "role": "assistant",
                                "content": "ملخص موجز لما سبق في نفس المحادثة:\n" + digest,
                                "created_at": "",
                            },
                        )
                logger.info(
                    "[CONV_LIFECYCLE] stage=history_loaded role=%s user=%s conv_id=%s msg_count=%s",
                    "admin" if is_admin_scope else "customer",
                    user_id,
                    conversation_id,
                    len(messages),
                )
                conv_metadata_to_import = {
                    "title": str(conv_row.title),
                    "created_at": conv_row.created_at.isoformat(),
                }
                messages_to_import = list(messages)
            except Exception as e:
                logger.error(
                    "[ENSURE_CONV] failed preparing history for import for conversation=%s user=%s; preserving same conversation_id. error=%s",
                    conversation_id,
                    user_id,
                    e,
                )
        else:
            conversation_id = await _create_new_conversation(
                user_id, question, is_admin_scope, session
            )

        try:
            async with asyncio.timeout(5.0):
                await session.execute(
                    insert_message_query,
                    {
                        "conversation_id": int(conversation_id),
                        "role": "user",
                        "content": question.replace("\x00", ""),
                    },
                )
        except TimeoutError as e:
            raise HTTPException(status_code=504, detail="Database timeout inserting message") from e
        await session.commit()

    if conv_metadata_to_import is not None and conversation_id is not None:
        try:
            await _lazy_import_history_with_retry(
                conversation_id=conversation_id,
                user_id=user_id,
                conv_metadata=conv_metadata_to_import,
                messages=messages_to_import,
            )
        except Exception as e:
            logger.error(
                "[ENSURE_CONV] failed lazy import for conversation=%s user=%s. error=%s",
                conversation_id,
                user_id,
                e,
            )

    return int(conversation_id), messages


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
        try:
            async with asyncio.timeout(5.0):
                await session.execute(
                    insert_message_query,
                    {
                        "conversation_id": conversation_id,
                        "role": "assistant",
                        "content": content.replace("\x00", ""),
                    },
                )
        except TimeoutError as e:
            raise HTTPException(
                status_code=504, detail="Database timeout persisting assistant message"
            ) from e

        if is_admin_scope and mission_id is not None:
            try:
                async with asyncio.timeout(5.0):
                    await session.execute(
                        link_query,
                        {
                            "mission_id": mission_id,
                            "conversation_id": conversation_id,
                        },
                    )
            except TimeoutError as e:
                raise HTTPException(
                    status_code=504, detail="Database timeout linking mission"
                ) from e
        await session.commit()


async def _stream_chat_langgraph(
    websocket: WebSocket,
    objective: str,
    context: ChatRunContext,
    chat_scope: str,
    conversation_id: int,
    app_graph: object = None,
    admin_payload: dict[str, object] | None = None,
    history_messages: list[dict[str, str]] | None = None,
) -> None:
    """يشغّل LangGraph الموحد لمسارات البحث والإدارة ويبث الأحداث."""
    queue: asyncio.Queue[dict[str, object]] = asyncio.Queue(maxsize=256)
    prepared_objective = _augment_ambiguous_objective(objective, history_messages)

    async def _runner():
        async def _safe_put(evt: dict[str, object]) -> None:
            try:
                queue.put_nowait(evt)
            except asyncio.QueueFull:
                logger.warning("[QUEUE_OVERFLOW] dropping event type=%s", evt.get("type"))

        try:
            _graph = app_graph or getattr(websocket.app.state, "app_graph", None)
            if not _graph:
                _graph = create_unified_graph()
            thread_id = _resolve_thread_id(context, conversation_id)
            incoming_messages = history_messages or []
            await _append_telemetry_line(
                f"[TELEMETRY] INGRESS | "
                f"conversation_id={conversation_id!r} | "
                f"thread_id={thread_id!r} | "
                f"messages_in_request={len(incoming_messages)}"
            )
            config = {"configurable": {"thread_id": thread_id}}
            checkpointer_available, checkpoint_has_state = await _detect_checkpoint_state(thread_id)
            langchain_msgs = _build_graph_messages(
                objective=prepared_objective,
                history_messages=history_messages,
                checkpointer_available=checkpointer_available,
                checkpoint_has_state=checkpoint_has_state,
            )
            logger.info(
                "[CONTEXT_MODE] channel=websocket conv_id=%s thread_id=%s checkpointer_available=%s checkpoint_has_state=%s seeded_history=%s",
                conversation_id,
                thread_id,
                checkpointer_available,
                checkpoint_has_state,
                max(0, len(langchain_msgs) - 1),
            )

            inputs: dict[str, object] = {
                "query": prepared_objective,
                "messages": langchain_msgs,
            }
            inputs = _merge_admin_inputs(inputs, admin_payload if chat_scope == "admin" else None)
            state_dict = inputs
            payload_messages = state_dict.get("messages", [])
            await _append_telemetry_line(
                f"[TELEMETRY] PRE-INVOKE | "
                f"messages type={type(payload_messages).__name__} | "
                f"count={len(payload_messages)} | "
                f"last_msg={str(payload_messages[-1])[:120] if payload_messages else 'EMPTY'}"
            )
            checkpointer = get_checkpointer()
            if checkpointer is None:
                await _append_telemetry_line("[TELEMETRY] CHECKPOINTER NOT IN SCOPE")
            else:
                _t = time.monotonic()
                try:
                    _ckpt = await checkpointer.aget(config)
                    _elapsed = time.monotonic() - _t
                    _keys = list(_ckpt.channel_values.keys()) if _ckpt else None
                    await _append_telemetry_line(
                        f"[TELEMETRY] CHECKPOINTER | "
                        f"elapsed={_elapsed:.4f}s | "
                        f"state={'NONE — silent failure' if _ckpt is None else _keys}"
                    )
                except Exception as _e:
                    await _append_telemetry_line(
                        f"[TELEMETRY] CHECKPOINTER CRASHED | {type(_e).__name__}: {_e}"
                    )

            final_res = None
            async for event in _graph.astream_events(inputs, config=config, version="v2"):
                if event["event"] == "on_chain_start":
                    node_name = event.get("name", "")
                    if node_name and not node_name.startswith("__") and node_name != "LangGraph":
                        await _safe_put(
                            {
                                "type": "phase_start",
                                "payload": {"phase": node_name, "agent": "orchestrator"},
                            }
                        )
                elif event["event"] == "on_chain_end":
                    node_name = event.get("name", "")
                    if node_name and not node_name.startswith("__") and node_name != "LangGraph":
                        await _safe_put(
                            {
                                "type": "phase_completed",
                                "payload": {"phase": node_name, "agent": "orchestrator"},
                            }
                        )
                    if not node_name or node_name == "LangGraph":
                        final_res = event["data"].get("output", {})
                        if (
                            final_res
                            and isinstance(final_res, dict)
                            and "final_response" in final_res
                        ):
                            pass  # We have our final response
                        elif (
                            final_res
                            and isinstance(final_res, dict)
                            and "messages" in final_res
                            and final_res["messages"]
                        ):
                            # Fallback to extract final response from last message
                            last_msg = final_res["messages"][-1]
                            if hasattr(last_msg, "content"):
                                final_res = {"final_response": last_msg.content}

            if checkpointer is not None:
                _t2 = time.monotonic()
                try:
                    _ckpt_after = await checkpointer.aget(config)
                    _elapsed2 = time.monotonic() - _t2
                    _msgs_saved = (
                        len(_ckpt_after.channel_values.get("messages", [])) if _ckpt_after else 0
                    )
                    await _append_telemetry_line(
                        f"[TELEMETRY] POST-INVOKE | "
                        f"elapsed={_elapsed2:.4f}s | "
                        f"messages_persisted={_msgs_saved} | "
                        f"state={'NONE — not saved' if _ckpt_after is None else 'SAVED'}"
                    )
                except Exception as _e:
                    await _append_telemetry_line(
                        f"[TELEMETRY] POST-INVOKE CRASHED | {type(_e).__name__}: {_e}"
                    )

            if not final_res:
                final_res = {"final_response": "لم يتم العثور على رد من النظام"}

            await _safe_put({"type": "__DONE__", "result": final_res})
        except Exception as e:
            await _safe_put({"type": "__ERROR__", "error": str(e)})

    task = asyncio.create_task(_runner())
    active_background_tasks.add(task)

    def _cleanup_task(t: asyncio.Task) -> None:
        active_background_tasks.discard(t)
        try:
            t.result()
        except asyncio.CancelledError:
            pass
        except Exception:
            logger.error("LangGraph task failed", exc_info=True)

    task.add_done_callback(_cleanup_task)
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
    try:
        while True:
            evt = await queue.get()
            if evt["type"] == "__DONE__":
                run_data = evt["result"]

                # Extract the final response from our custom Unified Graph output
                final_resp = run_data.get("final_response")

                if isinstance(final_resp, dict):
                    response_text = await _serialize_json_async(final_resp)
                else:
                    response_text = str(final_resp or "لا توجد تفاصيل متاحة.")

                final_content = response_text
                logger.info(f"FINAL RESPONSE → {response_text[:100]}")
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
                request_id = str(uuid.uuid4())
                logger.error(
                    "LangGraph streaming failure",
                    exc_info=True,
                    extra={"request_id": request_id, "chat_scope": chat_scope},
                )
                final_content = _safe_assistant_error(request_id)
                await websocket.send_json(
                    {"type": "assistant_error", "payload": {"content": final_content}}
                )
                break
            if evt["type"] == "phase_start":
                phase_name = (
                    evt["payload"].get("phase", "") if isinstance(evt["payload"], dict) else ""
                )
                agent_name = (
                    evt["payload"].get("agent", "") if isinstance(evt["payload"], dict) else ""
                )
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
                phase_name = (
                    evt["payload"].get("phase", "") if isinstance(evt["payload"], dict) else ""
                )
                agent_name = (
                    evt["payload"].get("agent", "") if isinstance(evt["payload"], dict) else ""
                )
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

        if final_content.strip():
            try:
                await _persist_assistant_message(
                    chat_scope=chat_scope,
                    conversation_id=conversation_id,
                    content=final_content,
                    mission_id=None,
                )
                await websocket.send_json(
                    {"type": "assistant_delta", "payload": {"content": "\n\n✅ [DB SAVED]"}}
                )
            except Exception as e:
                error_msg = str(e)
                await websocket.send_json(
                    {
                        "type": "assistant_delta",
                        "payload": {"content": f"\n\n🚨 **SYSTEM DB ERROR:** {error_msg}"},
                    }
                )
    finally:
        if not task.done():
            task.cancel()
            with suppress(asyncio.CancelledError):
                await task

    await websocket.send_json({"type": "complete", "payload": {}})


async def _run_chat_langgraph(
    objective: str,
    context: ChatRunContext,
    app_graph: object = None,
    admin_payload: dict[str, object] | None = None,
    history_messages: list[dict[str, str]] | None = None,
) -> AsyncGenerator[str, None]:
    """يشغّل LangGraph كعمود فقري لرحلة chat ويعيد حمولة موحدة قابلة للبث (HTTP legacy fallback)."""
    if not app_graph:
        app_graph = create_unified_graph()
    requested_conversation_id = context.get("conversation_id") if context else None
    safe_conversation_id = _safe_conversation_id(requested_conversation_id)
    conversation_id: int | str = (
        safe_conversation_id if safe_conversation_id is not None else str(uuid.uuid4())
    )
    thread_id = _resolve_thread_id(context, conversation_id)
    prepared_objective = _augment_ambiguous_objective(objective, history_messages)
    config = {"configurable": {"thread_id": thread_id}}
    logger.info(
        "[THREAD_BINDING] channel=http thread_id=%s source=%s conversation_id=%s",
        thread_id,
        "request_context"
        if "thread_id" in context or "session_id" in context
        else "conversation_fallback",
        str(conversation_id),
    )
    checkpointer_available, checkpoint_has_state = await _detect_checkpoint_state(thread_id)
    langchain_msgs = _build_graph_messages(
        objective=prepared_objective,
        history_messages=history_messages,
        checkpointer_available=checkpointer_available,
        checkpoint_has_state=checkpoint_has_state,
    )
    logger.info(
        "[CONTEXT_MODE] channel=http conv_id=%s thread_id=%s checkpointer_available=%s checkpoint_has_state=%s seeded_history=%s",
        conversation_id,
        thread_id,
        checkpointer_available,
        checkpoint_has_state,
        max(0, len(langchain_msgs) - 1),
    )

    inputs: dict[str, object] = {"query": prepared_objective, "messages": langchain_msgs}
    inputs = _merge_admin_inputs(inputs, admin_payload)

    final_resp = None
    async for event in app_graph.astream_events(inputs, config=config, version="v2"):
        if event["event"] == "on_chain_start":
            node_name = event.get("name", "")
            if node_name and not node_name.startswith("__") and node_name != "LangGraph":
                yield await _serialize_stream_frame(
                    {
                        "type": "phase_start",
                        "payload": {"phase": node_name, "agent": "orchestrator"},
                    }
                )
        elif event["event"] == "on_chain_end":
            node_name = event.get("name", "")
            if node_name and not node_name.startswith("__") and node_name != "LangGraph":
                yield await _serialize_stream_frame(
                    {
                        "type": "phase_completed",
                        "payload": {"phase": node_name, "agent": "orchestrator"},
                    }
                )
            if not node_name or node_name == "LangGraph":
                final_res = event["data"].get("output", {})
                if final_res and isinstance(final_res, dict) and "final_response" in final_res:
                    final_resp = final_res["final_response"]
                elif (
                    final_res
                    and isinstance(final_res, dict)
                    and "messages" in final_res
                    and final_res["messages"]
                ):
                    last_msg = final_res["messages"][-1]
                    if hasattr(last_msg, "content"):
                        final_resp = last_msg.content

    if isinstance(final_resp, dict):
        response_text = await _serialize_json_async(final_resp)
    else:
        response_text = str(final_resp or "لا توجد تفاصيل متاحة.")

    yield await _serialize_stream_frame(
        {
            "type": "assistant_final",
            "payload": {
                "content": response_text,
                "status": "ok",
                "run_id": "http-run",
                "graph_mode": "unified_stategraph",
            },
        }
    )


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
    async with async_session_factory() as session:
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
    check_query = text(
        """
        SELECT id, title, created_at
        FROM customer_conversations
        WHERE id = :conversation_id AND user_id = :user_id
        """
    )
    messages_query = text(
        """
        SELECT role, content, created_at
        FROM customer_messages
        WHERE conversation_id = :conversation_id
        ORDER BY id ASC
        """
    )
    async with async_session_factory() as session:
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
    async with async_session_factory() as session:
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
    user_id, payload = _decode_auth_payload_or_401(authorization)
    if not _is_admin_payload(payload):
        raise HTTPException(status_code=403, detail="forbidden")
    check_query = text(
        """
        SELECT id, title, created_at
        FROM admin_conversations
        WHERE id = :conversation_id AND user_id = :user_id
        """
    )
    messages_query = text(
        """
        SELECT role, content, created_at
        FROM admin_messages
        WHERE conversation_id = :conversation_id
        ORDER BY id ASC
        """
    )
    async with async_session_factory() as session:
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

    chat_scope = str(context.get("chat_scope", "customer"))

    requested_conversation_id = _safe_conversation_id(payload.get("conversation_id"))

    conversation_id, history_messages = await _ensure_conversation(
        chat_scope=chat_scope,
        user_id=user_id,
        question=objective,
        requested_conversation_id=requested_conversation_id,
    )
    context["conversation_id"] = conversation_id

    requested_thread_id = _safe_thread_id(payload.get("thread_id"))
    if requested_thread_id is not None:
        context["thread_id"] = requested_thread_id
    requested_session_id = _safe_thread_id(payload.get("session_id"))
    if requested_session_id is not None:
        context["session_id"] = requested_session_id

    async def _generator_with_persistence() -> AsyncGenerator[str, None]:
        generator = _run_chat_langgraph(
            objective,
            context,
            app_graph=getattr(request.app.state, "app_graph", None),
            history_messages=history_messages,
        )
        final_content = ""
        async for chunk in generator:
            try:
                chunk_data = json.loads(chunk)
                if chunk_data.get("type") == "assistant_final":
                    final_content = chunk_data.get("payload", {}).get("content", "")
            except Exception:
                pass
            yield chunk

        if final_content:
            try:
                await _save_chat_to_db(
                    chat_scope=chat_scope,
                    user_id=user_id,
                    conversation_id=conversation_id,
                    user_msg=objective,
                    ai_msg=final_content,
                )
            except Exception as e:
                logger.error("[HTTP_PERSIST] failed to save final chat message: %s", e)

    return StreamingResponse(_generator_with_persistence(), media_type="text/plain")


@router.websocket("/api/chat/ws")
async def chat_ws_stategraph(websocket: WebSocket) -> None:
    from microservices.orchestrator_service.src.core.logging import get_logger

    logger = get_logger("routes")
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
    sticky_conversation_id: int | None = None
    sticky_thread_id: str | None = None
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
            requested_thread_id = _safe_thread_id(incoming.get("thread_id"))
            requested_session_id = _safe_thread_id(incoming.get("session_id"))

            logger.info(
                "[CONV_LIFECYCLE] stage=ws_received role=customer user=%s conv_id=%s type=%s",
                user_id,
                requested_conversation_id,
                type(requested_conversation_id).__name__,
            )
            conversation_id = _resolve_effective_conversation_id(
                incoming_value=requested_conversation_id,
                sticky_value=sticky_conversation_id,
            )
            if (
                requested_conversation_id is not None
                and requested_conversation_id != sticky_conversation_id
            ):
                sticky_thread_id = None
            resolved_thread_id = requested_thread_id or requested_session_id or sticky_thread_id
            logger.info(
                "[CONV_LIFECYCLE] stage=parsed role=customer user=%s conv_id=%s type=%s",
                user_id,
                conversation_id,
                type(conversation_id).__name__,
            )
            try:
                logger.info(f"ORCHESTRATOR received | chat_scope=customer | role={user_id}")
                logger.info(
                    "[CONV_LIFECYCLE] stage=ensure_entry role=customer user=%s conv_id=%s",
                    user_id,
                    conversation_id,
                )
                conversation_id, history_messages = await _ensure_conversation(
                    chat_scope="customer",
                    user_id=user_id,
                    question=objective,
                    requested_conversation_id=conversation_id,
                )
                logger.info(
                    "[CONV_LIFECYCLE] stage=ensure_exit role=customer user=%s conv_id=%s msg_count=%s",
                    user_id,
                    conversation_id,
                    len(history_messages),
                )
                sticky_conversation_id = conversation_id
                sticky_thread_id = resolved_thread_id or str(conversation_id)
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
            context: ChatRunContext = {}
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
            context["conversation_id"] = conversation_id
            context["user_id"] = user_id
            if sticky_thread_id:
                context["thread_id"] = sticky_thread_id

            try:
                client_context = _extract_client_context_messages(incoming)
                hydrated_messages = _merge_history_with_client_context(
                    history_messages, client_context
                )
            except Exception as e:
                logger.error(
                    "[HYDRATION_GUARD] Context hydration failed — "
                    f"falling back to DB history only. "
                    f"Error: {type(e).__name__}: {e}"
                )
                hydrated_messages = history_messages

            await _stream_chat_langgraph(
                websocket,
                objective=objective,
                context=context,
                chat_scope="customer",
                conversation_id=conversation_id,
                app_graph=getattr(websocket.app.state, "app_graph", None),
                history_messages=hydrated_messages,
            )
            logger.info(
                "[CONV_LIFECYCLE] stage=response_sent role=customer user=%s conv_id=%s",
                user_id,
                conversation_id,
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
    sticky_conversation_id: int | None = None
    sticky_thread_id: str | None = None
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
            requested_thread_id = _safe_thread_id(incoming.get("thread_id"))
            requested_session_id = _safe_thread_id(incoming.get("session_id"))

            logger.info(
                "[CONV_LIFECYCLE] stage=ws_received role=admin user=%s conv_id=%s type=%s",
                user_id,
                requested_conversation_id,
                type(requested_conversation_id).__name__,
            )
            conversation_id = _resolve_effective_conversation_id(
                incoming_value=requested_conversation_id,
                sticky_value=sticky_conversation_id,
            )
            if (
                requested_conversation_id is not None
                and requested_conversation_id != sticky_conversation_id
            ):
                sticky_thread_id = None
            resolved_thread_id = requested_thread_id or requested_session_id or sticky_thread_id
            logger.info(
                "[CONV_LIFECYCLE] stage=parsed role=admin user=%s conv_id=%s type=%s",
                user_id,
                conversation_id,
                type(conversation_id).__name__,
            )
            try:
                logger.info(f"ORCHESTRATOR received | chat_scope=admin | role={user_id}")
                logger.info(
                    "[CONV_LIFECYCLE] stage=ensure_entry role=admin user=%s conv_id=%s",
                    user_id,
                    conversation_id,
                )
                conversation_id, history_messages = await _ensure_conversation(
                    chat_scope="admin",
                    user_id=user_id,
                    question=objective,
                    requested_conversation_id=conversation_id,
                )
                logger.info(
                    "[CONV_LIFECYCLE] stage=ensure_exit role=admin user=%s conv_id=%s msg_count=%s",
                    user_id,
                    conversation_id,
                    len(history_messages),
                )
                sticky_conversation_id = conversation_id
                sticky_thread_id = resolved_thread_id or str(conversation_id)
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
            context: ChatRunContext = {}
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
            context["conversation_id"] = conversation_id
            context["user_id"] = user_id
            if sticky_thread_id:
                context["thread_id"] = sticky_thread_id

            try:
                client_context = _extract_client_context_messages(incoming)
                hydrated_messages = _merge_history_with_client_context(
                    history_messages, client_context
                )
            except Exception as e:
                logger.error(
                    "[HYDRATION_GUARD] Context hydration failed — "
                    f"falling back to DB history only. "
                    f"Error: {type(e).__name__}: {e}"
                )
                hydrated_messages = history_messages

            await _stream_chat_langgraph(
                websocket,
                objective=objective,
                context=context,
                chat_scope="admin",
                conversation_id=conversation_id,
                app_graph=getattr(websocket.app.state, "app_graph", None),
                admin_payload=auth_payload,
                history_messages=hydrated_messages,
            )
            logger.info(
                "[CONV_LIFECYCLE] stage=response_sent role=admin user=%s conv_id=%s",
                user_id,
                conversation_id,
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
    fastapi_req: Request,
    authorization: str | None = Header(default=None),
) -> StreamingResponse:
    """
    Direct chat endpoint for the Orchestrator Agent (Microservice).
    Streams the response chunk by chunk.
    """
    user_id, auth_payload = _decode_auth_payload_or_401(authorization)
    request.user_id = user_id  # Override body user_id with JWT user_id

    logger.info(f"Agent Chat Request: {request.question[:50]}... User: {request.user_id}")

    # Prepare context
    context = request.context.copy()
    context.update(
        {
            "user_id": request.user_id,
            "conversation_id": request.conversation_id,
            "history_messages": request.history_messages,
        }
    )

    # Validate admin explicitly from JWT payload
    is_admin = auth_payload.get("role") == "admin"

    if is_admin:

        async def _admin_stream() -> AsyncGenerator[str, None]:
            try:
                admin_app = getattr(fastapi_req.app.state, "admin_app", None)
                if admin_app is None:
                    admin_app = create_unified_graph()
                    logger.warning("[ADMIN_STREAM] admin_app not on app.state — using fresh graph")

                if isinstance(request.context, dict):
                    request.context["is_admin"] = True
                    request.context["role"] = "admin"
                    admin_payload = request.context
                else:
                    admin_payload = {"is_admin": True, "role": "admin"}

                langchain_msgs: list[HumanMessage | AIMessage] = []

                # Checkpointer natively handles history now, append only the current human query
                langchain_msgs.append(HumanMessage(content=request.question))

                admin_inputs = _merge_admin_inputs(
                    {"query": request.question, "messages": langchain_msgs}, admin_payload
                )

                conversation_id = (
                    request.conversation_id
                    if getattr(request, "conversation_id", None)
                    else str(uuid.uuid4())
                )

                thread_id = _resolve_thread_id(
                    {"user_id": request.user_id, "conversation_id": request.conversation_id},
                    fallback_conversation_id=str(conversation_id),
                )

                final_resp = None
                config = {"configurable": {"thread_id": thread_id}}
                async for event in admin_app.astream_events(
                    admin_inputs, config=config, version="v2"
                ):
                    if event["event"] == "on_chain_start":
                        node_name = event.get("name", "")
                        if (
                            node_name
                            and not node_name.startswith("__")
                            and node_name != "LangGraph"
                        ):
                            yield await _serialize_stream_frame(
                                {
                                    "type": "phase_start",
                                    "payload": {"phase": node_name, "agent": "admin"},
                                }
                            )
                    elif event["event"] == "on_chain_end":
                        node_name = event.get("name", "")
                        if (
                            node_name
                            and not node_name.startswith("__")
                            and node_name != "LangGraph"
                        ):
                            yield await _serialize_stream_frame(
                                {
                                    "type": "phase_completed",
                                    "payload": {"phase": node_name, "agent": "admin"},
                                }
                            )
                        if not node_name or node_name == "LangGraph":
                            output_data = event["data"].get("output", {})
                            if output_data and isinstance(output_data, dict):
                                if "final_response" in output_data:
                                    final_resp = output_data["final_response"]
                                elif output_data.get("messages"):
                                    last_msg = output_data["messages"][-1]
                                    if hasattr(last_msg, "content"):
                                        final_resp = last_msg.content

                if isinstance(final_resp, dict):
                    response_text = await _serialize_json_async(final_resp)
                else:
                    response_text = str(final_resp or "لا توجد تفاصيل متاحة.")
                yield await _serialize_stream_frame(
                    {"type": "assistant_final", "payload": {"content": response_text}}
                )

                full_user_message = request.question
                full_ai_response = response_text
                try:
                    async with async_session_factory() as db_session:
                        conv_id, _ = await _ensure_conversation(
                            session=db_session,
                            conversation_id=request.conversation_id,
                            user_id=request.user_id,
                            question=full_user_message,
                            is_admin_scope=True,
                            messages=request.history_messages,
                        )
                        await _persist_assistant_message(
                            session=db_session,
                            conversation_id=conv_id,
                            is_admin_scope=True,
                            message=full_ai_response,
                        )
                    yield await _serialize_stream_frame(
                        {"type": "assistant_delta", "payload": {"content": "\n\n✅ [DB SAVED]"}}
                    )
                except Exception as e:
                    error_msg = str(e)
                    yield await _serialize_stream_frame(
                        {
                            "type": "assistant_error",
                            "payload": {"content": f"\n\n🚨 **SYSTEM DB ERROR:** {error_msg}"},
                        }
                    )
            except Exception:
                request_id = str(uuid.uuid4())
                logger.error(
                    "Admin Chat Error",
                    exc_info=True,
                    extra={"request_id": request_id},
                )
                yield await _serialize_stream_frame(
                    {
                        "type": "assistant_error",
                        "payload": {"content": _safe_assistant_error(request_id)},
                    }
                )

        return StreamingResponse(_admin_stream(), media_type="text/plain")

    ai_client = get_ai_client()
    agent = OrchestratorAgent(ai_client, tool_registry)

    async def _stream_generator():
        try:
            run_result = agent.run(request.question, context=context)
            ai_chunks = []
            async for chunk in run_result:
                if isinstance(chunk, str):
                    ai_chunks.append(chunk)
                elif isinstance(chunk, dict) and chunk.get("type") == "assistant_delta":
                    delta_content = chunk.get("payload", {}).get("content", "")
                    if delta_content:
                        ai_chunks.append(str(delta_content))
                elif isinstance(chunk, dict) and chunk.get("type") == "assistant_final":
                    final_content = chunk.get("payload", {}).get("content", "")
                    if final_content:
                        ai_chunks.append(str(final_content))

                yield await _serialize_stream_frame(chunk)

            # The run completed successfully, trigger persistence
            full_user_message = request.question
            full_ai_response = "".join(ai_chunks)
            if full_ai_response:
                try:
                    await _save_chat_to_db(
                        chat_scope="customer",
                        user_id=request.user_id,
                        conversation_id=request.conversation_id,
                        user_msg=full_user_message,
                        ai_msg=full_ai_response,
                    )
                    yield await _serialize_stream_frame(
                        {"type": "assistant_delta", "payload": {"content": "\n\n✅ [DB SAVED]"}}
                    )
                except Exception as e:
                    error_msg = str(e)
                    yield await _serialize_stream_frame(
                        {
                            "type": "assistant_error",
                            "payload": {"content": f"\n\n🚨 **SYSTEM DB ERROR:** {error_msg}"},
                        }
                    )

        except Exception:
            request_id = str(uuid.uuid4())
            logger.error(
                "Agent Chat Error",
                exc_info=True,
                extra={"request_id": request_id},
            )
            yield await _serialize_stream_frame(
                {
                    "type": "assistant_error",
                    "payload": {"content": _safe_assistant_error(request_id)},
                }
            )

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
            canonical_event = _canonicalize_mission_event(event)
            if canonical_event is None:
                continue

            await websocket.send_json({"type": "mission_event", "payload": canonical_event})

            if canonical_event["event_type"] in ("mission_completed", "mission_failed"):
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
        try:
            await subscription.aclose()
        except Exception as e:
            logger.warning("[WS_CLEANUP] subscription.aclose() failed: %s", e)
