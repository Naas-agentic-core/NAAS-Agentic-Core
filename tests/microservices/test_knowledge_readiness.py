from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient


def mock_verify_token():
    return True


@patch("microservices.memory_agent.main.init_db", new_callable=AsyncMock)
def test_readiness_endpoint(mock_init_db):
    # Move imports inside test function to avoid collection-time side effects
    from microservices.memory_agent.main import create_app
    from microservices.memory_agent.security import verify_service_token

    app = create_app()
    app.dependency_overrides[verify_service_token] = mock_verify_token

    # Use a real TestClient (synchronous wrapper around async app)
    client = TestClient(app)

    # Concept Graph is loaded by default in KnowledgeService -> ConceptGraph Singleton
    # "conditional_prob" requires "combinations" (relation PREREQUISITE in DEFAULT_RELATIONS)
    # combinations name_ar = "التوفيقات"

    # Test Case 1: Ready
    payload = {
        "concept_id": "conditional_prob",
        "mastery_levels": {"combinations": 0.8},
    }
    response = client.post("/knowledge/readiness", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["concept_id"] == "conditional_prob"
    assert data["is_ready"] is True
    assert data["readiness_score"] >= 0.5
    assert not data["missing_prerequisites"]
    assert not data["weak_prerequisites"]

    # Test Case 2: Not Ready (Missing Prereq)
    payload = {"concept_id": "conditional_prob", "mastery_levels": {}}
    response = client.post("/knowledge/readiness", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["is_ready"] is False
    assert "التوفيقات" in data["missing_prerequisites"]

    # Test Case 3: Not Ready (Weak Prereq)
    payload = {"concept_id": "conditional_prob", "mastery_levels": {"combinations": 0.2}}
    response = client.post("/knowledge/readiness", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["is_ready"] is False
    assert "التوفيقات" in data["weak_prerequisites"]

    # Test Case 4: Concept Not Found
    payload = {"concept_id": "unknown_concept_123", "mastery_levels": {}}
    response = client.post("/knowledge/readiness", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["concept_id"] == "unknown_concept_123"
    assert data["is_ready"] is True  # Logic permits proceeding if unknown
    assert "غير موجود" in data["recommendation"]
