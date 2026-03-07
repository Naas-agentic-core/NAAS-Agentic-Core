"""
Intent handlers using Strategy pattern.
"""

import asyncio
import json
import logging
import os
import re
from collections.abc import AsyncGenerator
from datetime import UTC, datetime

from sqlmodel import SQLModel

# Import chat domain to ensure AdminConversation is registered, preventing mapping errors
import app.core.domain.chat  # noqa: F401
from app.core.agents.system_principles import (
    format_architecture_system_principles,
    format_system_principles,
)
from app.core.domain.mission import (
    Mission,
    MissionEvent,
    MissionEventType,
    MissionPlan,
    Task,
)
from app.core.patterns.strategy import Strategy
from app.core.settings.base import get_settings
from app.services.chat.context import ChatContext

logger = logging.getLogger(__name__)


class IntentHandler(Strategy[ChatContext, AsyncGenerator[str | dict, None]]):
    """Base intent handler."""

    def __init__(self, intent_name: str, priority: int = 0):
        self._intent_name = intent_name
        self._priority = priority

    async def can_handle(self, context: ChatContext) -> bool:
        """Check if handler can process this intent."""
        return context.intent == self._intent_name

    @property
    def priority(self) -> int:
        return self._priority


class FileReadHandler(IntentHandler):
    """Handle file read requests."""

    def __init__(self):
        super().__init__("FILE_READ", priority=10)

    async def execute(self, context: ChatContext) -> AsyncGenerator[str, None]:
        """Execute file read."""
        path = context.get_param("path", "")

        if not path:
            yield "❌ لم يتم تحديد مسار الملف\n"
            return

        try:
            yield f"📖 قراءة الملف: `{path}`\n\n"
            content = await self._read_file(path)
            yield f"```\n{content}\n```\n"
            logger.info(f"File read successful: {path}", extra={"user_id": context.user_id})
        except FileNotFoundError:
            yield f"❌ الملف غير موجود: `{path}`\n"
        except PermissionError:
            yield f"❌ لا توجد صلاحية لقراءة الملف: `{path}`\n"
        except Exception as e:
            yield f"❌ خطأ في قراءة الملف: {e!s}\n"
            logger.error(f"File read error: {e}", extra={"path": path, "user_id": context.user_id})

    async def _read_file(self, path: str) -> str:
        """Read file contents in a non-blocking way."""
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, lambda: self._read_file_sync(path))

    def _read_file_sync(self, path: str) -> str:
        """Synchronous file read."""
        with open(path, encoding="utf-8") as f:
            return f.read()


class FileWriteHandler(IntentHandler):
    """Handle file write requests."""

    def __init__(self):
        super().__init__("FILE_WRITE", priority=10)

    async def execute(self, context: ChatContext) -> AsyncGenerator[str, None]:
        """Execute file write."""
        path = context.get_param("path", "")

        if not path:
            yield "❌ لم يتم تحديد مسار الملف\n"
            return

        yield f"📝 لإنشاء ملف `{path}`، يرجى تحديد المحتوى.\n"
        yield "يمكنك كتابة المحتوى في الرسالة التالية.\n"


class CodeSearchHandler(IntentHandler):
    """Handle code search requests."""

    def __init__(self):
        super().__init__("CODE_SEARCH", priority=10)

    async def execute(self, context: ChatContext) -> AsyncGenerator[str, None]:
        """Execute code search."""
        query = context.get_param("query", "")

        if not query:
            yield "❌ لم يتم تحديد استعلام البحث\n"
            return

        yield f"🔍 البحث عن: `{query}`\n\n"
        results = await self._search_code(query, context.user_id)

        if not results:
            yield "لم يتم العثور على نتائج\n"
            return

        yield f"تم العثور على {len(results)} نتيجة:\n\n"
        for result in results:
            yield f"- `{result['file']}:{result['line']}`\n"

    async def _search_code(self, query: str, user_id: int) -> list[dict]:
        """Search code (placeholder)."""
        logger.info(f"Code search: {query}", extra={"user_id": user_id})
        return []


class ProjectIndexHandler(IntentHandler):
    """Handle project indexing requests."""

    def __init__(self):
        super().__init__("PROJECT_INDEX", priority=10)

    async def execute(self, context: ChatContext) -> AsyncGenerator[str, None]:
        """Execute project indexing."""
        yield "📊 فهرسة المشروع...\n\n"
        stats = await self._index_project(context.user_id)

        yield "✅ تمت الفهرسة بنجاح:\n"
        yield f"- الملفات: {stats.get('files', 0)}\n"
        yield f"- الأسطر: {stats.get('lines', 0)}\n"

    async def _index_project(self, user_id: int) -> dict:
        """Index project (placeholder)."""
        logger.info("Project indexing started", extra={"user_id": user_id})
        return {"files": 0, "lines": 0}


class DeepAnalysisHandler(IntentHandler):
    """Handle deep analysis requests."""

    def __init__(self):
        super().__init__("DEEP_ANALYSIS", priority=10)

    async def execute(self, context: ChatContext) -> AsyncGenerator[str, None]:
        """Execute deep analysis."""
        yield "🧠 تحليل عميق للسؤال...\n\n"

        analysis = await self._analyze(context.question, context.ai_client)

        yield f"{analysis}\n"

    async def _analyze(self, question: str, ai_client) -> str:
        """Perform deep analysis."""
        return "تحليل عميق (قيد التطوير)"


class MissionComplexHandler(IntentHandler):
    """
    Handle complex mission requests using Overmind.
    Implements 'API First' streaming response pattern.
    """

    def __init__(self):
        super().__init__("MISSION_COMPLEX", priority=10)

    async def execute(self, context: ChatContext) -> AsyncGenerator[str | dict, None]:
        """
        Execute complex mission.
        Creates a Mission DB entry and triggers the Overmind in background.
        Streams updates to the user using Strict Output Contract.
        """
        # Defer imports to prevent circular dependency
        from app.infrastructure.clients.orchestrator_client import orchestrator_client
        from app.services.overmind.entrypoint import start_mission

        # Global try-except to prevent stream crash
        try:
            yield {
                "type": "assistant_delta",
                "payload": {"content": "🚀 **بدء المهمة الخارقة (Super Agent)**...\n"},
            }

            # 0. Fail-Fast Configuration Check
            config_error = self._check_provider_config()
            if config_error:
                yield {"type": "assistant_error", "payload": {"content": f"{config_error}\n"}}
                return

            # Detect Force Research Intent
            force_research = False
            q_lower = context.question.lower()
            if any(
                k in q_lower
                for k in ["بحث", "internet", "db", "مصادر", "search", "database", "قاعدة بيانات"]
            ):
                force_research = True

            # 1. Initialize Mission via Unified Entrypoint (Command Pattern)
            mission_id = 0

            try:
                # Use Unified Entrypoint (Handles DB Creation, Locking, Execution Trigger)
                # Note: We pass session=None to enforce decoupling from local Monolith DB
                mission = await start_mission(
                    session=None,  # type: ignore
                    objective=context.question,
                    initiator_id=context.user_id or 1,
                    context={"chat_context": True},
                    force_research=force_research,
                )
                mission_id = mission.id

                yield {
                    "type": "assistant_delta",
                    "payload": {"content": f"🆔 رقم المهمة: `{mission.id}`\n⏳ البدء..."},
                }
            except Exception as e:
                logger.error(f"Failed to dispatch mission: {e}", exc_info=True)
                yield {
                    "type": "assistant_error",
                    "payload": {
                        "content": "❌ **خطأ في النظام:** لم نتمكن من بدء المهمة (Dispatch Failed)."
                    },
                }
                return

            # Emit RUN_STARTED for UI
            sequence_id = 0
            current_iteration = 0
            sequence_id += 1
            run0_id = f"{mission_id}:{current_iteration}"
            now = datetime.now(UTC).isoformat()
            yield {
                "type": "RUN_STARTED",
                "payload": {
                    "run_id": run0_id,
                    "seq": sequence_id,
                    "timestamp": now,
                    "iteration": current_iteration,
                    "mode": "standard",
                },
            }

            # 3. Stream Updates (Polling Strategy)
            # Decoupled from local DB and local Redis.
            # We poll the Orchestrator Service for authoritative events.

            running = True
            processed_count = 0
            final_sent = False

            try:
                while running:
                    await asyncio.sleep(2.0)  # Polling interval

                    events = await orchestrator_client.get_mission_events(mission_id)

                    # Process new events
                    new_events = events[processed_count:]
                    if new_events:
                        processed_count = len(events)

                        for evt_data in new_events:
                            # Convert dict to MissionEvent-like object or use directly if helper supports it
                            # We assume events are ordered by creation time/id from the API

                            payload = evt_data.get("payload", {})
                            if payload.get("brain_event") == "loop_start":
                                data = payload.get("data", {})
                                current_iteration = data.get("iteration", current_iteration)

                            # Output Protocol
                            message = self._format_event_to_message(evt_data)
                            if message:
                                if message.get("type") == "assistant_final":
                                    final_sent = True
                                yield message

                            # Canonical Events
                            sequence_id += 1
                            structured = self._create_structured_event(
                                evt_data, sequence_id, current_iteration
                            )
                            if structured:
                                yield structured

                            # Check terminal state from event types
                            evt_type = evt_data.get("event_type")
                            if evt_type == "mission_completed":
                                running = False
                                if not final_sent:
                                    # Try to extract result from this event payload
                                    result = payload.get("result", {})
                                    if result:
                                        # Already handled by _format_event_to_message if event_type matched
                                        pass
                                    else:
                                        yield {
                                            "type": "assistant_final",
                                            "payload": {"content": "✅ تمت المهمة بنجاح."},
                                        }
                            elif evt_type == "mission_failed":
                                running = False
                                if not final_sent:
                                    yield {
                                        "type": "assistant_error",
                                        "payload": {
                                            "content": f"❌ فشلت المهمة: {payload.get('error') or 'Unknown error'}"
                                        },
                                    }

                            if not running:
                                break

            finally:
                pass
        except Exception as global_ex:
            logger.critical(f"Critical error in MissionComplexHandler: {global_ex}", exc_info=True)
            yield {
                "type": "assistant_error",
                "payload": {
                    "content": "\n🛑 **حدث خطأ حرج أثناء تنفيذ المهمة.** تم تسجيل المشكلة وجاري العمل على حلها.\n"
                },
            }

    def _check_provider_config(self) -> str | None:
        """
        Check for critical environment configurations (LLM & Search).
        Returns an error message if missing, else None.
        """
        # 1. LLM Check (Critical)
        settings = get_settings()
        if not settings.OPENROUTER_API_KEY and not settings.OPENAI_API_KEY:
            return "🛑 **خطأ في التكوين:** مفتاح الذكاء الاصطناعي (LLM Key) مفقود. يرجى التحقق من ملف .env."

        # 2. Search Check (Warn only, as DDG is fallback)
        has_search_key = os.environ.get("TAVILY_API_KEY") or os.environ.get("FIRECRAWL_API_KEY")
        if not has_search_key:
            # We don't block execution because DuckDuckGo is a valid fallback.
            # But we log it for observability.
            logger.warning(
                "No dedicated search provider key found (TAVILY/FIRECRAWL). Using Fallback."
            )

        return None

    async def _ensure_mission_schema(self, session) -> None:
        """
        Checks and attempts to self-heal missing mission tables.
        Now uses SQLModel metadata to ensure cross-database compatibility (SQLite/Postgres).
        """
        try:
            # Explicitly define tables to verify/create
            # This avoids creating incompatible tables (e.g. vector type on SQLite)
            target_tables = [
                Mission.__table__,
                MissionPlan.__table__,
                Task.__table__,
                MissionEvent.__table__,
            ]

            bind = session.bind
            if not bind:
                logger.warning("No bind found for session in schema check.")
                return

            # Check if bind is AsyncConnection (has run_sync) or AsyncEngine (needs connect)
            if hasattr(bind, "run_sync"):
                await bind.run_sync(
                    SQLModel.metadata.create_all, tables=target_tables, checkfirst=True
                )
            else:
                # Assume AsyncEngine
                async with bind.begin() as conn:
                    await conn.run_sync(
                        SQLModel.metadata.create_all, tables=target_tables, checkfirst=True
                    )

            logger.info("Schema self-healing: Verified mission tables.")

        except Exception as e:
            # Log error but attempt to continue, assuming tables might exist or partial failure
            logger.error(f"Schema self-healing failed: {e}")

    def _create_structured_event(
        self, event: MissionEvent | dict, sequence_id: int, current_iteration: int
    ) -> dict | None:
        """
        Create Canonical Event (Production-Grade Contract) for UI FSM.
        """
        try:
            if isinstance(event, dict):
                payload = event.get("payload", {})
                mission_id = event.get("mission_id")
                timestamp = event.get("timestamp")
                event_type = event.get("event_type")
            else:
                payload = event.payload_json or {}
                mission_id = event.mission_id
                timestamp = str(event.created_at)
                event_type = event.event_type

            # Use tracked iteration context to ensure Run Isolation
            # FIX: We use unique run_id per iteration to prevent UI jumping/merging
            run_id = f"{mission_id}:{current_iteration}"

            if event_type in (MissionEventType.STATUS_CHANGE, "status_change"):
                brain_evt = str(payload.get("brain_event", ""))
                data = payload.get("data", {})

                if brain_evt == "loop_start":
                    # loop_start defines the iteration for the NEW run
                    iteration = data.get("iteration", current_iteration)
                    # Update run_id for the new loop
                    new_run_id = f"{mission_id}:{iteration}"
                    return {
                        "type": "RUN_STARTED",
                        "payload": {
                            "run_id": new_run_id,
                            "seq": sequence_id,
                            "timestamp": timestamp,
                            "iteration": iteration,
                            "mode": data.get("graph_mode", "standard"),
                        },
                    }

                if brain_evt == "phase_start":
                    return {
                        "type": "PHASE_STARTED",
                        "payload": {
                            "run_id": run_id,
                            "seq": sequence_id,
                            "phase": data.get("phase"),
                            "agent": data.get("agent"),
                            "timestamp": timestamp,
                        },
                    }

                if brain_evt == "phase_completed":
                    return {
                        "type": "PHASE_COMPLETED",
                        "payload": {
                            "run_id": run_id,
                            "seq": sequence_id,
                            "phase": data.get("phase"),
                            "agent": data.get("agent"),
                            "timestamp": timestamp,
                        },
                    }
            return None
        except Exception as e:
            logger.warning(f"Failed to create structured event: {e}")
            return None

    def _format_event_to_message(self, event: MissionEvent | dict) -> dict | None:
        """
        Format mission event into a Strict Output Contract Message.
        Returns: dict (assistant_delta | assistant_final | tool_result_summary) or None.
        """
        try:
            if isinstance(event, dict):
                payload = event.get("payload", {})
                event_type = event.get("event_type")
            else:
                payload = event.payload_json or {}
                event_type = event.event_type

            # 1. Handle Final Completion
            if event_type in (
                MissionEventType.MISSION_COMPLETED,
                "mission_completed",
            ):
                result = payload.get("result", {})
                result_text = ""

                # Check for explicit output
                if isinstance(result, dict):
                    if result.get("output") or result.get("answer") or result.get("summary"):
                        result_text = (
                            result.get("output") or result.get("answer") or result.get("summary")
                        )
                    elif "results" in result and isinstance(result["results"], list):
                        # Use Tool Result Summary if no text answer
                        return {
                            "type": "tool_result_summary",
                            "payload": {
                                "summary": "تم تنفيذ المهام بنجاح.",
                                "items": result["results"],
                            },
                        }
                    else:
                        result_text = json.dumps(result, ensure_ascii=False, indent=2)
                else:
                    result_text = str(result)

                return {"type": "assistant_final", "payload": {"content": result_text}}

            # 2. Handle Failure
            if event_type in (MissionEventType.MISSION_FAILED, "mission_failed"):
                return {
                    "type": "assistant_error",
                    "payload": {"content": f"💀 **فشل:** {payload.get('error')}"},
                }

            # 3. Handle Status/Progress (Assistant Delta)
            if event_type in (MissionEventType.STATUS_CHANGE, "status_change"):
                brain_evt = payload.get("brain_event")
                if brain_evt:
                    # Convert brain events to text deltas if relevant
                    text = _format_brain_event(str(brain_evt), payload.get("data", {}))
                    if text:
                        return {"type": "assistant_delta", "payload": {"content": text}}

                status_note = payload.get("note")
                if status_note:
                    return {
                        "type": "assistant_delta",
                        "payload": {"content": f"🔄 {status_note}\n"},
                    }

                return None

            return None
        except Exception:
            return None


def _format_task_results(tasks: list) -> str:
    """Format a list of task results into a readable string."""
    lines = [f"✅ **تم تنفيذ {len(tasks)} مهمة:**\n"]
    for t in tasks:
        if not isinstance(t, dict):
            continue

        name = t.get("name", "مهمة")

        # Handle Skipped
        if t.get("status") == "skipped":
            reason = t.get("reason", "غير محدد")
            lines.append(f"🔹 **{name}**: ⏭️ تم التجاوز ({reason})\n")
            continue

        res = t.get("result", {})
        if not res:
            # Skip empty results to reduce noise
            continue

        # Extract content
        result_data = res.get("result_data")
        result_text = res.get("result_text")

        display_text = ""

        if result_data:
            display_text = _format_tool_result_data(result_data)
        elif result_text:
            if isinstance(result_text, str):
                try:
                    if result_text.strip().startswith(("{", "[")):
                        parsed = json.loads(result_text)
                        display_text = _format_tool_result_data(parsed)
                    else:
                        display_text = _clean_raw_string(result_text)
                except Exception:
                    display_text = result_text
            else:
                display_text = str(result_text)
        else:
            display_text = "لا توجد بيانات"

        # Auto-read file content if written
        file_content = ""
        if result_data and isinstance(result_data, dict):
            data_payload = result_data.get("data", {})
            if (
                isinstance(data_payload, dict)
                and data_payload.get("written")
                and data_payload.get("path")
            ):
                path = data_payload["path"]
                try:
                    with open(path, encoding="utf-8") as f:
                        content = f.read()
                    file_content = f"\n\n**محتوى الملف ({path}):**\n```\n{content}\n```"
                except Exception as e:
                    logger.warning(f"Failed to auto-read file {path}: {e}")

        lines.append(f"🔹 **{name}**:\n{display_text}\n{file_content}\n")
    return "\n".join(lines)


def _format_brain_event(event_name: str, data: dict[str, object] | object) -> str | None:
    """
    تنسيق أحداث الدماغ الخارق بصورة موجزة جداً لمنع التضخم النصي.
    Returns None for verbose/minor events.
    """
    if not isinstance(data, dict):
        data = {}
    normalized = event_name.lower()

    # Silence common noisy events
    if normalized.endswith("_completed") or normalized in {"phase_start", "loop_start"}:
        # These are handled by the Timeline UI (Canonical Events), no need for text chat noise.
        # Unless it's a critical failure or specific user info.
        return None

    if normalized == "plan_rejected":
        return "🧩 إعادة ضبط الخطة.\n"

    if normalized == "plan_approved":
        return "✅ تم اعتماد الخطة.\n"

    if normalized.endswith("_timeout"):
        return "⏳ تأخير... إعادة المزامنة.\n"

    if normalized == "mission_critique_failed":
        critique = data.get("critique", {})
        feedback = critique.get("feedback", "N/A") if isinstance(critique, dict) else str(critique)
        return f"🔔 **تدقيق:** {feedback} (جاري التعديل...)\n"

    if normalized in {"mission_success", "phase_error"}:
        return f"🔔 {event_name}\n"

    # Default: Silence unknown events to prevent "noise"
    return None


def _format_tool_result_data(data: object) -> str:
    """Format tool result data for display."""
    if not isinstance(data, (dict, list)):
        return str(data)

    # Handle ToolResult structure (only if dict)
    if isinstance(data, dict) and "ok" in data and ("data" in data or "error" in data):
        if not data.get("ok"):
            return f"❌ خطأ: {data.get('error')}"

        inner_data = data.get("data")
        if inner_data is None:
            return "✅ تم."

        return _format_inner_data(inner_data)

    return _format_inner_data(data)


def _format_inner_data(data: object) -> str:
    """Format inner data (dict/list) nicely."""
    # Custom formatting for search results (List of content items)
    if (
        isinstance(data, list)
        and data
        and isinstance(data[0], dict)
        and "title" in data[0]
        and "id" in data[0]
    ):
        lines = ["✅ **النتائج:**\n"]
        for item in data[:3]:  # Limit to top 3 to prevent flooding
            title = item.get("title", "بدون عنوان")
            lines.append(f"* 🔹 {title}")

        if len(data) > 3:
            lines.append(f"* ... و {len(data) - 3} نتائج أخرى.")

        return "\n".join(lines)

    if isinstance(data, (dict, list)):
        # Return summary instead of full JSON dump
        return "📄 (بيانات مهيكلة)"
    return str(data)


def _clean_raw_string(text: str) -> str:
    """Clean raw ToolResult string representation."""
    if text.startswith("ToolResult("):
        match = re.search(r"data=(.*?)(, error=|$)", text)
        if match:
            return f"✅ {match.group(1)}"
        return text
    return text


class HelpHandler(IntentHandler):
    """Handle help requests."""

    def __init__(self):
        super().__init__("HELP", priority=10)

    async def execute(self, context: ChatContext) -> AsyncGenerator[str, None]:
        """Show help."""
        yield "📚 **المساعدة**\n\n"
        yield "الأوامر المتاحة:\n"
        yield "- قراءة ملف: `اقرأ ملف path/to/file`\n"
        yield "- كتابة ملف: `اكتب ملف path/to/file`\n"
        yield "- البحث: `ابحث عن query`\n"
        yield "- فهرسة: `فهرس المشروع`\n"
        yield "- مهمة معقدة: (أي سؤال معقد سيتم تحويله للوكيل الخارق)\n"


class DefaultChatHandler(IntentHandler):
    """Default chat handler (fallback)."""

    def __init__(self):
        super().__init__("DEFAULT", priority=-1)
        # Deferred imports to avoid circular dependency
        from app.services.chat.context_service import get_context_service
        from app.services.overmind.identity import OvermindIdentity

        self._identity = OvermindIdentity()
        self._context_service = get_context_service()

    async def can_handle(self, context: ChatContext) -> bool:
        """Always can handle (fallback)."""
        return True

    async def execute(self, context: ChatContext) -> AsyncGenerator[str, None]:
        """Execute default chat with identity context."""
        # إضافة معلومات الهوية إلى رسائل المحادثة
        enhanced_messages = self._add_identity_context(context.history_messages)

        async for chunk in context.ai_client.stream_chat(enhanced_messages):
            if isinstance(chunk, dict):
                choices = chunk.get("choices", [])
                if choices:
                    content = choices[0].get("delta", {}).get("content", "")
                    if content:
                        yield content
            elif isinstance(chunk, str):
                yield chunk

    def _add_identity_context(self, messages: list[dict[str, str]]) -> list[dict[str, str]]:
        """
        إضافة سياق النظام والهوية لإثراء إجابة Overmind.

        Args:
            messages: قائمة الرسائل الأصلية.

        Returns:
            list[dict[str, str]]: قائمة الرسائل بعد إدراج سياق النظام.
        """
        has_system = bool(messages) and messages[0].get("role") == "system"
        system_prompt = self._build_system_prompt(include_base_prompt=not has_system)
        if not has_system:
            return [{"role": "system", "content": system_prompt}, *messages]

        enhanced_messages = messages.copy()
        enhanced_messages[0] = {
            "role": "system",
            "content": messages[0]["content"] + "\n\n" + system_prompt,
        }
        return enhanced_messages

    def _build_system_prompt(self, *, include_base_prompt: bool) -> str:
        """
        إنشاء رسالة النظام الموحدة لتوجيه الردود الخارقة.

        Returns:
            str: رسالة نظام مركزة تجمع الهوية والتعليمات المتقدمة.
        """
        base_prompt = ""
        if include_base_prompt:
            base_prompt = self._context_service.get_context_system_prompt().strip()
        identity_context = self._build_identity_context()
        intelligence_directive = (
            "توجيه إضافي:\n"
            "- أجب بطريقة عبقرية فائقة الذكاء مع شرح منطقي متسلسل.\n"
            "- حافظ على العمق والوضوح، وقدم أمثلة تعليمية عند الحاجة.\n"
            "- إذا كان السؤال تعليمياً، قدم خطة تعلم مختصرة قبل الإجابة.\n"
        )
        multi_agent_directive = (
            "توجيهات العقل الجمعي:\n"
            "- فعّل أسلوب التفكير متعدد الوكلاء (Strategist/Architect/Auditor/Operator).\n"
            "- لخّص خطة الحل في نقاط، ثم نفّذ الإجابة خطوة بخطوة.\n"
            "- تحقّق من الفرضيات وصحّح المسار عند وجود غموض.\n"
            "- استخدم أسلوب Tree of Thoughts عند الأسئلة المعقدة.\n"
        )
        return "\n\n".join(
            part
            for part in [
                base_prompt,
                identity_context,
                intelligence_directive,
                multi_agent_directive,
            ]
            if part
        )

    def _build_identity_context(self) -> str:
        """
        بناء سياق الهوية التفصيلي لـ Overmind.

        Returns:
            str: نص هوية شامل للمؤسس ودور النظام.
        """
        founder = self._identity.get_founder_info()
        overmind = self._identity.get_overmind_info()
        principles_text = format_system_principles(
            header="المبادئ الصارمة للنظام (تُطبّق على الشيفرة بالكامل):",
            bullet="-",
            include_header=True,
        )
        architecture_principles_text = format_architecture_system_principles(
            header="مبادئ المعمارية وحوكمة البيانات (تُطبّق على الشيفرة بالكامل):",
            bullet="-",
            include_header=True,
        )
        return f"""أنت {overmind["name_ar"]} (Overmind)، {overmind["role_ar"]}.

معلومات المؤسس (مهمة جداً):
- الاسم الكامل: {founder["name_ar"]} ({founder["name"]})
- الاسم الأول: {founder["first_name_ar"]} ({founder["first_name"]})
- اللقب: {founder["last_name_ar"]} ({founder["last_name"]})
- تاريخ الميلاد: {founder["birth_date"]} (11 أغسطس 1997)
- الدور: {founder["role_ar"]} ({founder["role"]})
- GitHub: @{founder["github"]}

{principles_text}

{architecture_principles_text}

عندما يسأل أحد عن المؤسس أو مؤسس النظام أو من أنشأ Overmind، أجب بهذه المعلومات بدقة تامة.
"""
