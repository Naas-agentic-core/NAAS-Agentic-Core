"""
اختبارات وحدة لخدمة تخطيط الوكلاء وسجل الخطط.
"""

import asyncio
from datetime import UTC, datetime

from microservices.orchestrator_service.src.services.overmind.domain.api_schemas import AgentPlanData, AgentsPlanRequest
from microservices.orchestrator_service.src.services.overmind.plan_registry import AgentPlanRecord, AgentPlanRegistry
from microservices.orchestrator_service.src.services.overmind.plan_service import AgentPlanService


class StubStrategist:
    """وكيل استراتيجي بديل لإرجاع خطة ثابتة للاختبار."""

    async def create_plan(self, objective: str, context) -> dict:
        return {
            "strategy_name": "Test Strategy",
            "steps": [
                {
                    "name": "جمع المتطلبات",
                    "description": "تحديد نطاق العمل والمتطلبات الأساسية.",
                    "dependencies": "step-00",
                    "estimated_effort": 3,
                }
            ],
        }


def test_agent_plan_service_normalizes_steps() -> None:
    """يتأكد من تطبيع الحقول وتحويل الاعتمادات إلى قائمة نصية."""

    service = AgentPlanService(strategist=StubStrategist())
    payload = AgentsPlanRequest(
        objective="بناء خطة اختبارية",
        context={"source": "unit-test"},
        constraints=["OpenAPI v3.1"],
        priority="high",
    )

    plan_record = asyncio.run(service.create_plan(payload))

    assert plan_record.data.objective == payload.objective
    assert len(plan_record.data.steps) == 1
    step = plan_record.data.steps[0]
    assert step.dependencies == ["step-00"]
    assert step.estimated_effort == "3"


def test_agent_plan_registry_store_and_get() -> None:
    """يتأكد من تخزين الخطة واسترجاعها من السجل."""

    service = AgentPlanService(strategist=StubStrategist())
    payload = AgentsPlanRequest(
        objective="اختبار السجل",
        context={},
        constraints=[],
        priority="low",
    )

    plan_data = service._normalize_steps(
        {
            "steps": [
                {
                    "name": "التحقق",
                    "description": "تفاصيل الخطوة",
                }
            ]
        }
    )
    plan_record_data = AgentPlanData(
        plan_id="plan_test_registry",
        objective=payload.objective,
        steps=plan_data,
        created_at=datetime.now(UTC),
    )

    registry = AgentPlanRegistry()
    registry.store(AgentPlanRecord(data=plan_record_data))

    stored = registry.get("plan_test_registry")
    assert stored is not None
    assert stored.data.plan_id == "plan_test_registry"
