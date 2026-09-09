import os

import pytest

from app.caching.factory import CacheFactory
from app.caching.namespace_cache import NamespacedCache


@pytest.fixture(autouse=True)
def reset_cache_factory() -> None:
    CacheFactory._instance = None


def _clear_namespace_env() -> None:
    for key in ("CACHE_NAMESPACE", "SERVICE_NAME", "AGENT_NAME", "AGENT_ID"):
        os.environ.pop(key, None)


def test_cache_factory_prefers_cache_namespace(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear_namespace_env()
    monkeypatch.setenv("CACHE_NAMESPACE", "core-service")
    monkeypatch.setenv("SERVICE_NAME", "ignored-service")

    cache = CacheFactory.get_cache()

    assert isinstance(cache, NamespacedCache)
    assert cache._namespace == "core-service"


def test_cache_factory_falls_back_to_service_name(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear_namespace_env()
    monkeypatch.setenv("SERVICE_NAME", "gateway")

    cache = CacheFactory.get_cache()

    assert isinstance(cache, NamespacedCache)
    assert cache._namespace == "gateway"


@pytest.mark.parametrize(
    ("env_key", "expected"),
    [
        ("AGENT_NAME", "alpha-agent"),
        ("AGENT_ID", "agent-42"),
    ],
)
def test_cache_factory_uses_agent_identity(
    monkeypatch: pytest.MonkeyPatch, env_key: str, expected: str
) -> None:
    _clear_namespace_env()
    monkeypatch.setenv(env_key, expected)

    cache = CacheFactory.get_cache()

    assert isinstance(cache, NamespacedCache)
    assert cache._namespace == expected
