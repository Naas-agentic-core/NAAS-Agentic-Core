import pytest
from microservices.api_gateway.main import (
    _extract_session_id,
    _build_routing_identity,
    _rollout_bucket,
    _should_route_to_conversation
)
from types import SimpleNamespace

def test_same_session_id_produces_same_bucket():
    session_id = "sess-12345"
    identity1 = _build_routing_identity("route1", "path1", session_id)
    identity2 = _build_routing_identity("route2", "path2", session_id)
    assert identity1 == identity2
    assert _rollout_bucket(identity1) == _rollout_bucket(identity2)

def test_different_sessions_distribute_across_buckets():
    buckets = set()
    for i in range(100):
        identity = _build_routing_identity("route1", "path1", f"sess-{i}")
        buckets.add(_rollout_bucket(identity))
    # Should distribute to more than 1 bucket
    assert len(buckets) > 1

def test_extract_session_id_from_query_param():
    class MockWS:
        query_params = {"session_id": "sess-12345"}
        headers = {}
    assert _extract_session_id(MockWS()) == "sess-12345"

def test_extract_session_id_from_header_fallback():
    class MockWS:
        query_params = {}
        headers = {"x-session-id": "sess-67890"}
    assert _extract_session_id(MockWS()) == "sess-67890"

def test_query_param_takes_priority_over_header():
    class MockWS:
        query_params = {"session_id": "sess-from-query"}
        headers = {"x-session-id": "sess-from-header"}
    assert _extract_session_id(MockWS()) == "sess-from-query"

def test_missing_session_id_returns_none():
    class MockWS:
        query_params = {}
        headers = {}
    assert _extract_session_id(MockWS()) is None

    # Also test short session ids
    class MockWSShort:
        query_params = {"session_id": "short"}
        headers = {"x-session-id": "short"}
    assert _extract_session_id(MockWSShort()) is None

def test_rollout_at_10_percent_routes_roughly_10_percent():
    routed = 0
    for i in range(1000):
        identity = _build_routing_identity("route1", "path1", f"sess-test-{i}")
        if _should_route_to_conversation(identity, 10):
            routed += 1
    # Check distribution is roughly 10% +/- 30
    assert 70 <= routed <= 130