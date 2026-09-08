HUMAN:
I manually verified this by forcing an upstream 500 error on the websocket endpoint in conversation service, and confirming the client receives a structured JSON error and disconnects safely rather than crashing on HTML decode.

AGENT:
I executed tests on the gateway to confirm no websocket routing was broken by this change.

---

## Why
When an upstream service (like `conversation-service` or the Next.js proxy) crashes during the WebSocket upgrade handshake or during the stream, it occasionally streams its HTTP 500 HTML error page directly down the socket. The frontend client blindly attempts to parse this as JSON, leading to silent crashes or `JSONDecodeError` (Bug A).

## Summary
- Added robust catching of `websockets.exceptions.InvalidStatus` and `InvalidStatusCode` during the initial connection phase to prevent upstream 500 HTML error bodies from being dropped silently or leaked.
- Added strict string checks inside the `upstream_to_client` (and `target_to_client`) loop to intercept rogue WebSocket messages containing HTML.
- Ensures the client receives a structured JSON error (`{"type": "error", "payload": {"code": "WS_HTML_BLEED", ...}}`) and cleanly closes the socket with code 1011 in both failure scenarios.

## Issue Number
Fixes #1

## How to Test
```bash
uv run pytest tests/microservices/test_websocket_gateway_routing.py tests/test_gateway.py
# 18 passed, 3 skipped in 6.94s
```

## Change Type
- [x] bug fix
- [ ] feature
- [ ] refactor
- [ ] governance / documentation
- [ ] security hardening

## Affected Areas
- [ ] app core
- [ ] microservices
- [ ] contracts / guardrails
- [ ] CI/CD
- [ ] docs / governance

## Risk & Rollback
- **Risk level:** low
- **Rollback plan:** Revert this commit.

## Validation Evidence
```bash
uv run pytest tests/microservices/test_websocket_gateway_routing.py tests/test_gateway.py
============================= test session starts ==============================
platform linux -- Python 3.12.13, pytest-9.1.1, pluggy-1.6.0
rootdir: /app
configfile: pytest.ini
plugins: langsmith-0.12.1, anyio-4.15.1, asyncio-1.4.0
asyncio: mode=Mode.AUTO, debug=False, asyncio_default_fixture_loop_scope=None, asyncio_default_test_loop_scope=function
collected 21 items

tests/microservices/test_websocket_gateway_routing.py ........sss        [ 52%]
tests/test_gateway.py ..........                                         [100%]

======================== 18 passed, 3 skipped in 6.94s =========================
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
Look at `app/api/routers/ws_proxy.py` and `microservices/api_gateway/websockets.py`.
