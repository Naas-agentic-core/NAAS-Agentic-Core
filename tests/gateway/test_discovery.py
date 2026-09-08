import asyncio
import contextlib
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.gateway.config import ServiceEndpoint
from app.gateway.discovery import ServiceDiscovery
from app.gateway.registry import ServiceHealth, ServiceRegistry


@pytest.fixture
def mock_registry():
    registry = MagicMock(spec=ServiceRegistry)
    # Default behavior for check_health
    registry.check_health = AsyncMock()
    return registry


@pytest.fixture
def discovery(mock_registry):
    return ServiceDiscovery(
        registry=mock_registry, health_check_interval=1, heartbeat_timeout=2
    )


@pytest.fixture
def endpoint_a():
    return ServiceEndpoint(name="service-a", base_url="http://service-a:8080")


@pytest.fixture
def endpoint_b():
    return ServiceEndpoint(name="service-b", base_url="http://service-b:8080")


def test_register_service(discovery, endpoint_a):
    instance = discovery.register_service(endpoint_a, metadata={"version": "v1"})
    assert instance.endpoint == endpoint_a
    assert instance.metadata == {"version": "v1"}
    assert "service-a" in discovery._instances
    assert len(discovery._instances["service-a"]) == 1


def test_register_multiple_instances(discovery, endpoint_a):
    discovery.register_service(endpoint_a)
    endpoint_a2 = ServiceEndpoint(name="service-a", base_url="http://service-a-2:8080")
    discovery.register_service(endpoint_a2)

    assert len(discovery._instances["service-a"]) == 2


def test_deregister_service_success(discovery, endpoint_a):
    discovery.register_service(endpoint_a)
    result = discovery.deregister_service("service-a", "http://service-a:8080")
    assert result is True
    assert len(discovery._instances["service-a"]) == 0


def test_deregister_service_not_found(discovery):
    result = discovery.deregister_service("unknown", "http://unknown")
    assert result is False


def test_deregister_instance_not_found(discovery, endpoint_a):
    discovery.register_service(endpoint_a)
    result = discovery.deregister_service("service-a", "http://other-url")
    assert result is False
    assert len(discovery._instances["service-a"]) == 1


def test_get_instances(discovery, endpoint_a):
    discovery.register_service(endpoint_a)
    instances = discovery.get_instances("service-a")
    assert len(instances) == 1
    assert instances[0].endpoint == endpoint_a


def test_heartbeat_success(discovery, endpoint_a):
    instance = discovery.register_service(endpoint_a)
    old_heartbeat = instance.last_heartbeat - timedelta(seconds=10)
    instance.last_heartbeat = old_heartbeat

    result = discovery.heartbeat("service-a", "http://service-a:8080")
    assert result is True
    assert instance.last_heartbeat > old_heartbeat


def test_heartbeat_not_found(discovery):
    result = discovery.heartbeat("unknown", "http://unknown")
    assert result is False


def test_is_instance_healthy_heartbeat_timeout(discovery, endpoint_a):
    instance = discovery.register_service(endpoint_a)
    # Simulate missed heartbeat
    instance.last_heartbeat = datetime.utcnow() - timedelta(
        seconds=discovery.heartbeat_timeout + 1
    )
    assert discovery._is_instance_healthy(instance) is False


def test_is_instance_healthy_registry_health(discovery, endpoint_a, mock_registry):
    instance = discovery.register_service(endpoint_a)

    # Heartbeat is fine
    instance.last_heartbeat = datetime.utcnow()

    # Registry says unhealthy
    mock_registry.get_health.return_value = ServiceHealth(
        is_healthy=False, last_check=datetime.utcnow()
    )
    assert discovery._is_instance_healthy(instance) is False

    # Registry says healthy
    mock_registry.get_health.return_value = ServiceHealth(
        is_healthy=True, last_check=datetime.utcnow()
    )
    assert discovery._is_instance_healthy(instance) is True

    # Registry has no info
    mock_registry.get_health.return_value = None
    assert discovery._is_instance_healthy(instance) is True


def test_get_healthy_instance(discovery, endpoint_a, mock_registry):
    instance1 = discovery.register_service(endpoint_a)
    endpoint_a2 = ServiceEndpoint(name="service-a", base_url="http://service-a-2:8080")
    instance2 = discovery.register_service(endpoint_a2)

    # Make instance1 unhealthy (heartbeat timeout)
    instance1.last_heartbeat = datetime.utcnow() - timedelta(seconds=10)

    # Make instance2 healthy
    instance2.last_heartbeat = datetime.utcnow()
    mock_registry.get_health.return_value = None

    healthy = discovery.get_healthy_instance("service-a")
    assert healthy is not None
    assert healthy.endpoint == endpoint_a2


@pytest.mark.asyncio
async def test_perform_health_checks_removes_unhealthy(
    discovery, endpoint_a, mock_registry
):
    discovery.register_service(endpoint_a)

    # Mock registry check_health to return unhealthy
    unhealthy_status = ServiceHealth(
        is_healthy=False, last_check=datetime.utcnow(), error_message="Failed"
    )
    mock_registry.check_health.return_value = unhealthy_status

    # ensure it gets unhealthy status when _is_instance_healthy is called inside _remove_unhealthy_instances
    mock_registry.get_health.return_value = unhealthy_status

    await discovery._perform_health_checks()

    # Should be removed
    assert len(discovery._instances["service-a"]) == 0


@pytest.mark.asyncio
async def test_perform_health_checks_callback_exception_handled(
    discovery, endpoint_a, mock_registry
):
    discovery.register_service(endpoint_a)

    healthy_status = ServiceHealth(is_healthy=True, last_check=datetime.utcnow())
    mock_registry.check_health.return_value = healthy_status

    # Add a callback that raises an exception
    def failing_callback(name, health):
        raise ValueError("Callback failed")

    def working_callback(name, health):
        working_callback.called = True

    working_callback.called = False

    discovery.add_health_callback(failing_callback)
    discovery.add_health_callback(working_callback)

    # This should not raise an exception
    await discovery._perform_health_checks()

    # Second callback should still have been called
    assert working_callback.called is True
    # Instance should still be registered
    assert len(discovery._instances["service-a"]) == 1


@pytest.mark.asyncio
async def test_perform_health_checks_registry_check_exception_handled(
    discovery, endpoint_a, mock_registry
):
    discovery.register_service(endpoint_a)

    # Mock check_health to raise an exception
    mock_registry.check_health.side_effect = Exception("Registry check failed")

    # This should not raise an exception
    await discovery._perform_health_checks()

    # Instance is preserved (or not, depending on how _perform_health_checks handles it;
    # since it swallows the exception and doesn't remove, it remains)
    assert len(discovery._instances["service-a"]) == 1


@pytest.mark.asyncio
async def test_start_stop_health_checks(discovery):
    # Verify it's not running initially
    assert discovery._running is False
    assert discovery._health_check_task is None

    await discovery.start_health_checks()
    assert discovery._running is True
    assert discovery._health_check_task is not None
    assert not discovery._health_check_task.done()

    # Calling start again should not create a new task
    original_task = discovery._health_check_task
    await discovery.start_health_checks()
    assert discovery._health_check_task is original_task

    await discovery.stop_health_checks()
    assert discovery._running is False
    # Task should be done/cancelled
    assert (
        discovery._health_check_task.cancelled() or discovery._health_check_task.done()
    )


def test_get_service_stats(discovery, endpoint_a):
    discovery.register_service(endpoint_a)
    endpoint_a2 = ServiceEndpoint(name="service-a", base_url="http://service-a-2:8080")
    discovery.register_service(endpoint_a2)

    endpoint_b = ServiceEndpoint(name="service-b", base_url="http://service-b:8080")
    discovery.register_service(endpoint_b)

    stats = discovery.get_service_stats()

    assert stats["total_services"] == 2
    assert stats["total_instances"] == 3
    assert "service-a" in stats["services"]
    assert stats["services"]["service-a"]["total_instances"] == 2


def test_get_healthy_instance_no_instances(discovery):
    # Missing 163 (instances is empty)
    healthy = discovery.get_healthy_instance("unknown-service")
    assert healthy is None


def test_get_healthy_instance_all_unhealthy(discovery, endpoint_a, mock_registry):
    # Missing 169 (healthy_instances is empty)
    instance = discovery.register_service(endpoint_a)
    instance.last_heartbeat = datetime.utcnow() - timedelta(seconds=10)
    mock_registry.get_health.return_value = None

    healthy = discovery.get_healthy_instance("service-a")
    assert healthy is None


@pytest.mark.asyncio
async def test_health_check_loop_exception(discovery, endpoint_a, mock_registry):
    # Test missing lines 247-255 (exception in _health_check_loop)
    discovery.register_service(endpoint_a)
    discovery.health_check_interval = 0.01  # small interval for test
    discovery._running = True

    # Let's mock _perform_health_checks to raise an exception on first call,
    # then on the second call we'll set _running to False to stop the loop
    call_count = 0

    async def side_effect():
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise RuntimeError("Loop error")
        discovery._running = False

    discovery._perform_health_checks = AsyncMock(side_effect=side_effect)

    task = asyncio.create_task(discovery._health_check_loop())
    await asyncio.wait_for(task, timeout=1.0)

    assert call_count >= 2
    assert not discovery._running


def test_remove_unhealthy_instances_not_found(discovery):
    # Missing 292 (name not in instances for _remove_unhealthy_instances)
    # _remove_unhealthy_instances is "private" but we can call it to hit the coverage
    discovery._remove_unhealthy_instances("unknown-service")
    assert "unknown-service" not in discovery._instances


@pytest.mark.asyncio
async def test_health_check_loop_cancelled(discovery, endpoint_a, mock_registry):
    discovery.register_service(endpoint_a)
    discovery.health_check_interval = 1.0
    discovery._running = True
    discovery._perform_health_checks = AsyncMock()

    task = asyncio.create_task(discovery._health_check_loop())
    await asyncio.sleep(0.01)

    task.cancel()

    # Catch the cancelled error here if it bubbles up, or just wait if it handles it internally
    with contextlib.suppress(asyncio.CancelledError):
        await task

    assert discovery._perform_health_checks.called


import threading


def test_concurrent_registration_deregistration(discovery, endpoint_a, endpoint_b):
    # Test concurrent dictionary updates
    def register_a():
        for i in range(100):
            ep = ServiceEndpoint(
                name="service-a", base_url=f"http://service-a:{8080+i}"
            )
            discovery.register_service(ep)

    def register_b():
        for i in range(100):
            ep = ServiceEndpoint(
                name="service-b", base_url=f"http://service-b:{8080+i}"
            )
            discovery.register_service(ep)

    def deregister_a():
        for i in range(100):
            discovery.deregister_service("service-a", f"http://service-a:{8080+i}")

    t1 = threading.Thread(target=register_a)
    t2 = threading.Thread(target=register_b)

    t1.start()
    t2.start()

    t1.join()
    t2.join()

    assert len(discovery._instances["service-a"]) == 100
    assert len(discovery._instances["service-b"]) == 100

    t3 = threading.Thread(target=deregister_a)
    t3.start()
    t3.join()

    assert len(discovery._instances["service-a"]) == 0
