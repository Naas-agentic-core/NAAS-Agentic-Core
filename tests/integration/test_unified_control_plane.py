from unittest.mock import AsyncMock, patch

import pytest

from app.core.domain.mission import MissionStatus
from app.infrastructure.clients.orchestrator_client import MissionResponse
from microservices.orchestrator_service.src.services.overmind.entrypoint import start_mission


@pytest.mark.asyncio
async def test_start_mission_success(db_session):
    """
    Verifies that start_mission calls the Orchestrator Client.
    """
    session = db_session

    # Mock Orchestrator Client
    with patch("microservices.orchestrator_service.src.services.overmind.entrypoint.orchestrator_client") as mock_client:
        mock_response = MissionResponse(
            id=123,
            objective="Test Unified Control Plane",
            status="pending",
            created_at="2024-01-01T00:00:00",
            updated_at="2024-01-01T00:00:00",
        )
        mock_client.create_mission = AsyncMock(return_value=mock_response)

        mission = await start_mission(
            session=session,
            objective="Test Unified Control Plane",
            initiator_id=1,
            context={"test": True},
            idempotency_key="unique-key-123",
        )

        # 1. Verify Client Call
        mock_client.create_mission.assert_called_once()
        call_args = mock_client.create_mission.call_args
        assert call_args.kwargs["objective"] == "Test Unified Control Plane"
        assert call_args.kwargs["idempotency_key"] == "unique-key-123"

        # 2. Verify Return
        assert mission.id == 123
        assert mission.objective == "Test Unified Control Plane"
        assert mission.status == MissionStatus.PENDING


@pytest.mark.asyncio
async def test_start_mission_idempotency(db_session):
    """
    Verifies that start_mission passes idempotency key to client.
    """
    session = db_session
    key = "idempotent-key-999"

    with patch("microservices.orchestrator_service.src.services.overmind.entrypoint.orchestrator_client") as mock_client:
        mock_response = MissionResponse(
            id=999,
            objective="Obj",
            status="pending",
            created_at="2024-01-01",
            updated_at="2024-01-01",
        )
        mock_client.create_mission = AsyncMock(return_value=mock_response)

        await start_mission(session, "Obj", 1, idempotency_key=key)

        mock_client.create_mission.assert_called_once()
        assert mock_client.create_mission.call_args.kwargs["idempotency_key"] == key
