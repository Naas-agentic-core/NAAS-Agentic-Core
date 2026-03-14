import asyncio
import os
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from microservices.orchestrator_service.src.models.mission import OrchestratorSQLModel

# Force SQLite before any imports
os.environ["ORCHESTRATOR_DATABASE_URL"] = "sqlite+aiosqlite:///:memory:"
os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///:memory:"


def test_create_mission_endpoint():
    """
    Test creating a mission via the Orchestrator Service API.
    Ensures the microservice is correctly wired up and handles requests.
    """
    # IMPORT DOMAIN MODELS TO REGISTER THEM WITH SQLALCHEMY METADATA
    # This fixes the "NoForeignKeysError" because both Mission and User must be
    # registered in the same metadata instance before create_all is called.
    import app.core.domain.mission
    import app.core.domain.user  # noqa: F401

    # Lazy import to ensure env vars take effect
    # Rename to avoid conflict with top-level 'app' package
    from microservices.orchestrator_service.main import app as fastapi_app
    from microservices.orchestrator_service.src.core.database import get_db

    test_engine = create_async_engine("sqlite+aiosqlite:///:memory:", future=True)

    async def init_tables() -> None:
        """تهيئة جداول خدمة المنسّق داخل قاعدة SQLite معزولة للاختبار."""
        async with test_engine.begin() as conn:
            await conn.run_sync(OrchestratorSQLModel.metadata.create_all)

    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

    loop.run_until_complete(init_tables())

    test_session_maker = async_sessionmaker(
        test_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )

    async def override_get_db():
        async with test_session_maker() as session:
            yield session

    fastapi_app.dependency_overrides[get_db] = override_get_db

    mock_event_bus = AsyncMock()
    mock_event_bus.publish = AsyncMock()
    mock_event_bus.subscribe.return_value = AsyncMock()
    mock_event_bus.close = AsyncMock()

    mock_redis_client = AsyncMock()
    mock_lock = AsyncMock()
    mock_lock.acquire.return_value = True
    mock_lock.release = AsyncMock()
    mock_lock.__aenter__.return_value = mock_lock
    mock_lock.__aexit__.return_value = None

    mock_redis_client.lock = MagicMock(return_value=mock_lock)
    mock_redis_client.close = AsyncMock()

    try:
        with (
            patch(
                "microservices.orchestrator_service.src.core.database.init_db",
                new_callable=AsyncMock,
            ) as _,
            patch(
                "microservices.orchestrator_service.main.init_db",
                new_callable=AsyncMock,
            ) as _,
            patch(
                "microservices.orchestrator_service.src.core.event_bus.event_bus",
                mock_event_bus,
            ),
            patch(
                "redis.asyncio.from_url",
                return_value=mock_redis_client,
            ),
            patch("microservices.orchestrator_service.main.event_bus", mock_event_bus),
        ):
            with TestClient(fastapi_app) as client:
                payload = {
                    "objective": "Test Mission Objective",
                    "context": {"env": "test"},
                    "priority": 1,
                }
                headers = {"X-Correlation-ID": "test-idempotency-key-123"}

                response = client.post("/missions", json=payload, headers=headers)
                if response.status_code != 200:
                    print(f"Response: {response.text}")

                assert response.status_code == 200
                data = response.json()

                assert data["objective"] == "Test Mission Objective"
                assert data["status"] == "pending"
                assert "id" in data

                mission_id = data["id"]
                response_get = client.get(f"/missions/{mission_id}")
                assert response_get.status_code == 200
                data_get = response_get.json()
                assert data_get["id"] == mission_id
                assert data_get["objective"] == "Test Mission Objective"
    finally:
        fastapi_app.dependency_overrides.pop(get_db, None)
        loop.run_until_complete(test_engine.dispose())



def test_canonicalize_mission_event_accepts_legacy_shapes() -> None:
    from microservices.orchestrator_service.src.api.routes import _canonicalize_mission_event

    payload_shape = _canonicalize_mission_event({"event_type": "mission_started", "payload_json": {"a": 1}})
    data_shape = _canonicalize_mission_event({"event_type": "mission_started", "data": {"b": 2}})

    assert payload_shape == {"event_type": "mission_started", "data": {"a": 1}}
    assert data_shape == {"event_type": "mission_started", "data": {"b": 2}}
