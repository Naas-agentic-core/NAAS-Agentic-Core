import logging

from app.services.skills.retrieval_rerank_skill import _rec


def test_retrieval_telemetry_silenced_exception(monkeypatch, caplog):
    """
    Test that exceptions raised during telemetry recording in RetrievalRerankSkill
    are caught and logged at the debug level without propagating to the caller.
    """

    # Create a mock label that raises an exception when called
    class MockLabels:
        def labels(self, stage, status):
            raise RuntimeError("Simulated Prometheus error")

    # Mock _INVOCATIONS in the module to use our mock
    monkeypatch.setattr("app.services.skills.retrieval_rerank_skill._INVOCATIONS", MockLabels())

    # Ensure we capture debug logs from the right logger
    with caplog.at_level(logging.DEBUG, logger="cogniforge.skills.retrieval_rerank"):
        # Call the recording function
        _rec("test_stage", "test_status", 0.5)

    # Assert that the correct log message is recorded
    assert (
        "Failed to record retrieval telemetry (stage=test_stage, status=test_status)" in caplog.text
    )
    # Assert that exc_info was included (traceback is present)
    assert "Traceback (most recent call last):" in caplog.text
    assert "Simulated Prometheus error" in caplog.text
