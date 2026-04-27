# Context Continuity Forensic Report

## Scope
Diagnose the most-upstream break in context continuity for NAAS-Agentic-Core chat flow.

## Runtime trace executed
Command:

```bash
SKIP_GATEWAY_STARTUP_PROBE=1 python - <<'PY'
import logging
from fastapi.testclient import TestClient
import microservices.api_gateway.main as gateway

records=[]
class Capture(logging.Handler):
    def emit(self, record):
        msg=record.getMessage()
        if 'session_id presence' in msg or 'GATEWAY_IDENTITY_DIAGNOSTIC' in msg or 'ws_routing' in msg:
            records.append(msg)

h=Capture()
logger=logging.getLogger('api_gateway')
logger.setLevel(logging.INFO)
logger.addHandler(h)

async def fake_proxy(ws, target_url):
    await ws.accept()
    await ws.send_json({'ok':True,'target':target_url})
    await ws.close()

gateway.websocket_proxy=fake_proxy

with TestClient(gateway.app) as client:
    with client.websocket_connect('/api/chat/ws?token=fake.jwt.token', subprotocols=['jwt','fake.jwt.token']) as ws:
        print('WS_RESPONSE', ws.receive_json())

logger.removeHandler(h)
for r in records:
    print(r)
PY
```

Observed output excerpts:

- `WS_RESPONSE {'ok': True, 'target': 'ws://orchestrator-service:8006/api/chat/ws'}`
- `[GATEWAY_IDENTITY_DIAGNOSTIC] route=gateway_ws_customer conversation_id=missing thread_id=missing session_id=missing ...`
- `session_id presence: absent in chat_ws_proxy`
- `ws_routing session_id=absent bucket=29`

## Proven break point
Frontend websocket construction sends authentication token but does not attach `session_id` in URL query, headers, or JSON payload for outbound messages.

## Upstream causality evidence map
1. Frontend emits websocket with `token` query and `['jwt', token]` subprotocol, but no `session_id` field is attached.
2. Gateway extractor reads only `session_id` from query/header and logs missing identity.
3. Gateway routing identity falls back to random UUID when `session_id` missing.
4. Orchestrator receives message payload and can log missing `session_id` unless client includes it in JSON/context.
5. LangGraph persistence is keyed by `thread_id`; without stable identity from transport, continuity relies on compensatory conversation-scoped reconstruction.

## Identity continuity check (3 consecutive in-chat messages)
Function-level runtime simulation confirmed the same derived `conversation_id`/`thread_id` can remain stable while `session_id` stays missing:

```text
{'msg_index': 1, 'conversation_id': 901, 'thread_id': 'u42:c901', 'session_id': None}
{'msg_index': 2, 'conversation_id': 901, 'thread_id': 'u42:c901', 'session_id': None}
{'msg_index': 3, 'conversation_id': 901, 'thread_id': 'u42:c901', 'session_id': None}
```

Interpretation: continuity can be reconstructed downstream, but transport identity remains absent at the first upstream boundary.
