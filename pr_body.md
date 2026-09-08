HUMAN:
I manually verified this by running pytest and confirming the coverage is 100%.

AGENT:
I executed tests on the gateway to confirm the service discovery is tested correctly.

---

## Why
Because it is required to have a test file for the entire discovery module, which contains core logic for microservices.

## Summary
Added a missing test file (`tests/gateway/test_discovery.py`) for the `ServiceDiscovery` module.
The new test suite covers the following scenarios:
- **Registration/Deregistration:** Adding new services, multiple instances, and removing them. Includes concurrent registration/deregistration assertions.
- **Heartbeat & Health:** Validation of heartbeat timestamps, fallback to registry health checks, and round-robin healthy instance fetching.
- **Error Handling:** Verification that exceptions inside health callbacks or registry checks are safely caught and do not crash the discovery background loop.
- **Async Loop Management:** Starting, stopping, and cancelling the background health check task correctly.

Fixed lint errors in tests/services/test_ws_proxy_html_bleed.py that were breaking required-ci pipeline.

## Issue Number
Fixes #1

## How to Test
```bash
uv run pytest tests/gateway/test_discovery.py
uv run pytest tests/services/test_ws_proxy_html_bleed.py
```

## Change Type
- [ ] bug fix
- [ ] feature
- [ ] refactor
- [ ] governance / documentation
- [ ] security hardening
- [x] test

## Affected Areas
- [ ] app core
- [x] microservices
- [ ] contracts / guardrails
- [ ] CI/CD
- [ ] docs / governance

## Risk & Rollback
- **Risk level:** low
- **Rollback plan:** Revert this commit.

## Validation Evidence
```bash
uv run pytest tests/gateway/test_discovery.py
============================== 22 passed in 7.33s ==============================

uv run pytest tests/services/test_ws_proxy_html_bleed.py
============================== 3 passed in 4.13s ===============================
```

## Video/Screenshots
N/A

## Governance Checklist (Required)
- [ ] I updated docs when runtime/CI behavior changed.
- [ ] I did not add duplicate CI truth layers.
- [ ] I confirmed mergeability depends on `required-ci`.
- [ ] I removed or justified any skipped tests.
- [ ] I verified no PII or sensitive secrets were added.

## Safeguarding Impact
N/A

## Reviewer Guide
Look at `tests/gateway/test_discovery.py` and `tests/services/test_ws_proxy_html_bleed.py`.
