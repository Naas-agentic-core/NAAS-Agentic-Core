"""
اختبارات توحيد أسماء الأدوات في منفذ المهام.
"""

import pytest

from app.core.domain.mission import Task
from microservices.orchestrator_service.src.services.overmind.executor import TaskExecutor


class _NullStateManager:
    """بديل بسيط لمدير الحالة المطلوب من منفذ المهام."""

    async def update_task_status(self, *args, **kwargs):  # pragma: no cover - واجهة توافقية فقط
        return None


@pytest.mark.asyncio
async def test_task_executor_canonicalizes_tool_name():
    """
    يجب أن يوحّد منفذ المهام اسم الأداة قبل التنفيذ لضمان العثور عليها في السجل.
    """

    async def write_file(**kwargs):
        return {"ok": True, "args": kwargs}

    registry = {"write_file": write_file}
    executor = TaskExecutor(state_manager=_NullStateManager(), registry=registry)
    task = Task(
        mission_id=1,
        task_key="tool-canonical",
        description="اكتب ملفاً جديداً",
        tool_name="file.write",
        tool_args_json={"path": "x.txt", "content": "hi"},
    )

    result = await executor.execute_task(task)

    assert result["status"] == "success"
    assert result["meta"]["tool"] == "write_file"
    assert result["meta"]["original_tool"] == "file.write"
    assert result["result_data"]["ok"] is True
