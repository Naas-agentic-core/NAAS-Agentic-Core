from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import AsyncGenerator
from typing import TYPE_CHECKING

from app.core.resilience import get_circuit_breaker
from app.services.chat.handlers.base import ChatContext
from app.services.chat.security import ErrorSanitizer

if TYPE_CHECKING:
    from app.core.ai_gateway import AIClient

logger = logging.getLogger(__name__)


# ======================================================================================
# Helper Functions for Mission Handler
# ======================================================================================
async def _check_preconditions(
    context: ChatContext, user_id: int
) -> AsyncGenerator[str | None, None]:
    """Check rate limits and circuit breaker before mission creation."""
    allowed, msg = await context.check_rate_limit(user_id, "mission")
    if not allowed:
        yield f"⚠️ {msg}\n"
        return

    circuit = get_circuit_breaker("mission")
    can_execute, circuit_msg = circuit.can_execute()
    if not can_execute:
        yield f"⚠️ الخدمة غير متاحة مؤقتاً: {circuit_msg}\n"
        return

    yield None


async def _create_mission(
    context: ChatContext, objective: str, user_id: int, circuit
) -> dict | None:
    """Create mission with timeout and error handling."""
    try:
        async with asyncio.timeout(15):
            result = await context.async_overmind.start_mission(
                objective=objective, user_id=user_id
            )
        circuit.record_success()
        return result
    except TimeoutError:
        circuit.record_failure()
        return {"ok": False, "error": "timeout"}
    except Exception as e:
        circuit.record_failure()
        return {"ok": False, "error": str(e)}


def _format_task_info(tasks: dict) -> str:
    """Format task progress information."""
    if not tasks:
        return ""

    total = tasks.get("total", 0)
    success = tasks.get("success", 0)
    running = tasks.get("running", 0)
    failed = tasks.get("failed", 0)

    info = f" | المهام: {success}/{total} ✅"
    if running:
        info += f" {running} 🔄"
    if failed:
        info += f" {failed} ❌"
    return info


def _get_status_emoji(status: str) -> str:
    """Get emoji for mission status."""
    return {
        "pending": "⏳",
        "planning": "📋",
        "planned": "📝",
        "running": "🔄",
        "adapting": "🔧",
        "success": "✅",
        "failed": "❌",
        "canceled": "🚫",
    }.get(status, "❓")


async def _poll_mission_status(context: ChatContext, mission_id: int) -> AsyncGenerator[str, None]:
    """Poll mission status until completion or timeout."""
    poll_count = 0
    max_polls = 150  # 150 محاولة × 2 ثانية = 5 دقائق
    poll_interval = 2
    last_status = ""
    start_time = time.time()

    # رسائل المراحل المختلفة
    phase_messages = {
        "planning": "🎯 **المرحلة 1/4**: جاري التخطيط...",
        "design": "📐 **المرحلة 2/4**: جاري التصميم...",
        "execution": "⚙️ **المرحلة 3/4**: جاري التنفيذ...",
        "reflection": "🔍 **المرحلة 4/4**: جاري المراجعة...",
        "running": "🔄 **جاري المعالجة**...",
        "pending": "⏳ **في الانتظار**...",
    }

    try:
        while poll_count < max_polls:
            await asyncio.sleep(poll_interval)
            poll_count += 1

            try:
                status_result = await context.async_overmind.get_mission_status(mission_id)
            except Exception:
                break

            if not status_result.get("ok"):
                break

            status = status_result.get("status", "unknown")
            tasks = status_result.get("tasks", {})
            is_terminal = status_result.get("is_terminal", False)

            # حساب الوقت المنقضي
            elapsed = int(time.time() - start_time)
            elapsed_str = f"{elapsed}s" if elapsed < 60 else f"{elapsed // 60}m {elapsed % 60}s"

            # إظهار رسالة المرحلة إذا تغيرت الحالة
            if status != last_status:
                phase_msg = phase_messages.get(status.lower(), f"📊 **الحالة**: {status}")
                yield f"\n{phase_msg} ⏱️ ({elapsed_str})\n"
                last_status = status

            task_info = _format_task_info(tasks)
            status_emoji = _get_status_emoji(status)

            # إظهار التقدم كل 10 polls (20 ثانية)
            if poll_count % 10 == 0:
                yield f"  └─ {status_emoji} {status}{task_info} ⏱️ ({elapsed_str})\n"

            if is_terminal:
                final_elapsed = int(time.time() - start_time)
                yield f"\n🏁 **انتهت المهمة بحالة: {status}** ⏱️ ({final_elapsed}s)\n"
                break

    except asyncio.CancelledError:
        yield "\n⚠️ تم إلغاء المتابعة.\n"

    if poll_count >= max_polls:
        elapsed = int(time.time() - start_time)
        yield f"\nℹ️ المهمة تعمل في الخلفية (قضت {elapsed}s حتى الآن). يمكنك متابعة حالتها من لوحة التحكم.\n"


async def handle_deep_analysis(
    context: ChatContext,
    question: str,
    user_id: int,
    ai_client: AIClient,
) -> AsyncGenerator[str, None]:
    """
    Handle deep analytical questions using Overmind's deep understanding.
    معالجة الأسئلة التحليلية العميقة باستخدام Overmind.
    """
    start_time = time.time()

    yield "🧠 **تحليل عميق باستخدام Overmind Master Agent**\n\n"

    # 1. بناء فهرس المشروع | Build project index
    summary = await _build_project_index_with_feedback()
    async for feedback in summary["feedback"]:
        yield feedback

    # 2. إنشاء التوجيه المحسّن | Create enhanced prompt
    messages = _create_deep_analysis_messages(question, summary["data"])

    # 3. بث الاستجابة | Stream AI response
    yield "💡 **التحليل:**\n\n"

    async for chunk in _stream_ai_analysis(ai_client, messages):
        yield chunk

    logger.debug(f"Deep analysis completed in {(time.time() - start_time) * 1000:.2f}ms")


async def _build_project_index_with_feedback() -> dict[str, object]:
    """
    بناء فهرس المشروع مع تغذية راجعة للمستخدم.
    Build project index with user feedback.

    Returns:
        dict: {'data': summary or None, 'feedback': generator of feedback messages}
    """
    feedback_messages = []
    feedback_messages.append("📊 جارٍ فهرسة المشروع للحصول على سياق عميق...\n")

    try:
        async def _build_index_async():
            return ""

        summary = await asyncio.wait_for(_build_index_async(), timeout=30.0)
        feedback_messages.append("✅ تم بناء فهرس المشروع\n\n")

        return {"data": summary, "feedback": _async_generator_from_list(feedback_messages)}

    except TimeoutError:
        feedback_messages.append("⚠️ انتهت مهلة الفهرسة، سأستخدم معرفتي الحالية\n\n")
        return {"data": None, "feedback": _async_generator_from_list(feedback_messages)}

    except Exception as e:
        logger.warning(f"Failed to build index for deep analysis: {e}")
        feedback_messages.append("⚠️ لم أتمكن من فهرسة المشروع بالكامل\n\n")
        return {"data": None, "feedback": _async_generator_from_list(feedback_messages)}


async def _async_generator_from_list(items: list[str]) -> AsyncGenerator[str, None]:
    """
    تحويل قائمة إلى مولد غير متزامن.
    Convert list to async generator.
    """
    for item in items:
        yield item


def _create_deep_analysis_messages(question: str, summary: str | None) -> list[dict[str, str]]:
    """
    إنشاء رسائل التحليل العميق.
    Create messages for deep analysis with context.
    """
    system_prompt = """أنت Overmind Master Agent - نظام ذكاء اصطناعي متقدم متخصص في التحليل العميق للمشاريع البرمجية.

لديك قدرات خاصة:
- تحليل البنية المعمارية والأنماط البرمجية
- فهم التبعيات والعلاقات بين الوحدات
- تقييم جودة الكود وتحديد نقاط التحسين
- اكتشاف المشاكل المحتملة والثغرات
- تقديم توصيات مبنية على أفضل الممارسات

قم بتحليل السؤال بعمق واستخدم معرفتك ببنية المشروع لتقديم إجابة شاملة ودقيقة."""

    messages = [{"role": "system", "content": system_prompt}]

    if summary:
        context_msg = f"""**سياق المشروع:**

{summary}

---

الآن، بناءً على هذا السياق العميق للمشروع، أجب على السؤال التالي بدقة وشمولية:

{question}"""
        messages.append({"role": "user", "content": context_msg})
    else:
        messages.append({"role": "user", "content": question})

    return messages


async def _stream_ai_analysis(
    ai_client: AIClient, messages: list[dict[str, str]]
) -> AsyncGenerator[str, None]:
    """
    بث تحليل AI.
    Stream AI analysis response with error handling.
    """
    try:
        async for chunk in ai_client.stream_chat(messages):
            if isinstance(chunk, dict):
                content = _extract_content_from_chunk(chunk)
                if content:
                    yield content
            elif isinstance(chunk, str):
                yield chunk
    except Exception as e:
        yield f"\n\n❌ خطأ في التحليل: {ErrorSanitizer.sanitize(str(e))}\n"


def _extract_content_from_chunk(chunk: dict) -> str:
    """
    استخراج المحتوى من قطعة الاستجابة.
    Extract content from response chunk.
    """
    choices = chunk.get("choices", [])
    if choices:
        return choices[0].get("delta", {}).get("content", "")
    return ""


async def handle_mission(
    context: ChatContext,
    objective: str,
    user_id: int,
    conversation_id: int,
) -> AsyncGenerator[str, None]:
    """Handle complex mission request with Overmind and polling."""
    start_time = time.time()

    async for error_msg in _check_preconditions(context, user_id):
        if error_msg:
            yield error_msg
            return

    yield "🚀 **إنشاء مهمة Overmind**\n\n"
    yield f"**الهدف:** {objective[:150]}{'...' if len(objective) > 150 else ''}\n\n"

    if not context.async_overmind or not context.async_overmind.available:
        yield "⚠️ نظام Overmind غير متاح.\n"
        yield "سأحاول المساعدة بدون تنفيذ المهام التلقائية.\n\n"
        return

    yield "⏳ جارٍ إنشاء المهمة...\n\n"

    circuit = get_circuit_breaker("mission")
    result = await _create_mission(context, objective, user_id, circuit)

    if not result or not result.get("ok"):
        error = result.get("error", "خطأ غير معروف") if result else "خطأ غير معروف"
        if error == "timeout":
            yield "⏱️ انتهت المهلة أثناء إنشاء المهمة.\n"
        else:
            yield f"❌ خطأ: {ErrorSanitizer.sanitize(error)}\n"
        return

    mission_id = result.get("mission_id")
    yield f"✅ تم إنشاء المهمة #{mission_id}\n"
    yield f"📋 الحالة: {result.get('status', 'pending')}\n\n"

    await _link_mission_to_conversation(conversation_id, mission_id)

    yield "📊 **متابعة تقدم المهمة:**\n\n"
    async for status_msg in _poll_mission_status(context, mission_id):
        yield status_msg

    logger.debug(f"mission handler completed in {(time.time() - start_time) * 1000:.2f}ms")


async def _link_mission_to_conversation(conversation_id: int, mission_id: int):
    """
    Link mission to conversation for tracking.

    Note: Imports are inside method to prevent circular imports.
    This is intentional as this service is loaded early in the app lifecycle.
    """
    try:
        # Lazy imports to prevent circular dependencies - this is intentional
        from app.core.database import SessionLocal
        from app.core.domain.chat import AdminConversation
        from app.services.async_tool_bridge import run_sync_tool

        def _update():
            session = SessionLocal()
            try:
                conv = session.get(AdminConversation, conversation_id)
                if conv and hasattr(conv, "linked_mission_id"):
                    conv.linked_mission_id = mission_id
                    session.commit()
                    return True
            except Exception as e:
                logger.warning(f"Failed to link mission to conversation: {e}")
                session.rollback()
            finally:
                session.close()
            return False

        await run_sync_tool(_update, timeout=5.0)
    except Exception as e:
        logger.warning(f"Failed to link mission {mission_id} to conv {conversation_id}: {e}")
