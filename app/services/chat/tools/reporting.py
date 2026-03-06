"""
أدوات التحليل وإعداد التقارير التعليمية.
"""

from sqlalchemy import desc, select

from app.core.database import async_session_factory
from app.core.domain.chat import CustomerConversation, CustomerMessage, MessageRole
from app.core.domain.mission import Mission, MissionStatus
from app.core.logging import get_logger
from microservices.orchestrator_service.src.services.overmind.user_knowledge.service import UserKnowledge

logger = get_logger("reporting-tools")


async def fetch_comprehensive_student_history(user_id: int) -> dict[str, object]:
    """
    جلب تاريخ الطالب الشامل (محادثات + مهام) لتحليله بالذكاء الاصطناعي.
    """
    async with async_session_factory() as session:
        # 1. جلب المحادثات السابقة (آخر 50 رسالة من آخر 5 محادثات مثلاً)
        chat_logs = await _fetch_raw_chat_logs(session, user_id, message_limit=60)

        # 2. جلب تفاصيل المهام
        missions_summary = await _get_detailed_missions_summary(user_id)

        # 3. جلب الملف الشخصي
        async with UserKnowledge() as knowledge:
            profile = await knowledge.get_user_complete_profile(user_id)

    return {
        "user_id": user_id,
        "chat_history_text": chat_logs,
        "missions_summary": missions_summary,
        "profile_stats": profile.get("statistics", {}),
    }


async def _fetch_raw_chat_logs(session, user_id: int, message_limit: int = 60) -> str:
    """
    تجميع سجلات الدردشة كنص خام للتحليل.
    """
    # جلب معرفات آخر محادثات للمستخدم
    conv_stmt = (
        select(CustomerConversation.id)
        .where(CustomerConversation.user_id == user_id)
        .order_by(desc(CustomerConversation.updated_at))
        .limit(5)
    )
    conv_result = await session.execute(conv_stmt)
    conv_ids = conv_result.scalars().all()

    if not conv_ids:
        return "لا توجد سجلات محادثة سابقة."

    # جلب الرسائل من هذه المحادثات
    msg_stmt = (
        select(CustomerMessage)
        .where(CustomerMessage.conversation_id.in_(conv_ids))
        .order_by(desc(CustomerMessage.created_at))
        .limit(message_limit)
    )
    msg_result = await session.execute(msg_stmt)
    messages = msg_result.scalars().all()

    # إعادة ترتيب زمني
    messages.reverse()

    logs = []
    for msg in messages:
        role_label = "Student" if msg.role == MessageRole.USER else "AI Tutor"
        # اقتطاع المحتوى الطويل جداً لتوفير التوكنز
        content = msg.content[:500] + "..." if len(msg.content) > 500 else msg.content
        logs.append(f"{role_label} ({msg.created_at.strftime('%Y-%m-%d %H:%M')}): {content}")

    return "\n".join(logs)


async def get_student_diagnostic_report(user_id: int) -> dict[str, object]:
    """
    (Legacy Wrapper) توليد تقرير تشخيصي شامل للطالب يغطي الأداء والتقدم ونقاط القوة،
    معتمد على بيانات حقيقية من المهام (Missions).
    """
    # This is kept for backward compatibility if needed, but the Agent now prefers 'fetch_comprehensive_student_history'
    # calling the same internal logic
    return await fetch_comprehensive_student_history(user_id)


async def analyze_learning_curve(user_id: int) -> dict[str, object]:
    """
    تحليل منحنى التعلم للطالب بناءً على تواريخ إنجاز المهام.
    """
    async with async_session_factory() as session:
        # جلب تواريخ المهام المكتملة
        stmt = (
            select(Mission.updated_at, Mission.objective)
            .where(Mission.initiator_id == user_id, Mission.status == MissionStatus.SUCCESS)
            .order_by(Mission.updated_at)
        )
        result = await session.execute(stmt)
        history = result.all()

    if not history:
        return {"status": "no_data", "message": "لا توجد بيانات كافية لتحليل المنحنى."}

    # تحليل بسيط للسرعة (عدد المهام في الأسبوع)
    # يمكن تطويره ليكون أكثر تعقيداً
    return {
        "total_completed": len(history),
        "last_achievement": history[-1].objective if history else None,
        "last_active_date": history[-1].updated_at.isoformat() if history else None,
        "consistency_score": "High" if len(history) > 5 else "Growing",
        "trend": "Active Learner",
    }


async def _get_detailed_missions_summary(user_id: int) -> dict[str, object]:
    """
    جلب ملخص تفصيلي عن آخر المهام.
    """
    async with async_session_factory() as session:
        stmt = (
            select(Mission)
            .where(Mission.initiator_id == user_id)
            .order_by(desc(Mission.created_at))
            .limit(10)
        )
        result = await session.execute(stmt)
        missions = result.scalars().all()

    recent = []
    topics = set()

    for m in missions:
        recent.append(
            {
                "id": m.id,
                "title": m.objective[:50] + "..." if len(m.objective) > 50 else m.objective,
                "status": m.status.value,
                "date": m.created_at.isoformat(),
            }
        )
        words = m.objective.split()
        if len(words) > 0:
            topics.add(words[0])

    return {"recent_missions": recent, "topics": list(topics)}


def _calculate_completion_rate(stats: dict) -> str:
    total = stats.get("total_missions", 0)
    completed = stats.get("completed_missions", 0)
    if total == 0:
        return "N/A"
    return f"{(completed / total * 100):.1f}%"


def _generate_smart_recommendations(summary: dict) -> list[str]:
    recent = summary.get("recent_missions", [])
    if not recent:
        return ["ابدأ أول مهمة لك اليوم!"]

    failed_missions = [m for m in recent if m["status"] == "failed"]
    if failed_missions:
        return [f"مراجعة أسباب فشل المهمة: {failed_missions[0]['title']}"]

    return ["استمر في التقدم، أداؤك جيد!"]
