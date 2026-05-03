# CogniForge — Quick Commands

> Custom slash commands for Claude Code sessions.
> Run these to control the project without typing full commands.

---

## /project:start

Start both backend and frontend servers.

```bash
# Backend (terminal 1)
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

# Frontend (terminal 2)
cd frontend && npm run dev
```

Verify: http://localhost:8000/health + http://localhost:5000

---

## /project:test

Run the full test suite.

```bash
DATABASE_URL="sqlite+aiosqlite:///:memory:" \
SECRET_KEY="test-secret-key-for-ci-pipeline-secure-length" \
ENVIRONMENT="testing" \
LLM_MOCK_MODE="1" \
SUPABASE_URL="https://dummy.supabase.co" \
SUPABASE_ROLE_KEY="dummy" \
pytest tests/ -x -v
```

Options:
- `-x` — stop on first failure
- `-v` — verbose output
- `--co` — collect only (list tests without running)
- `-m security` — security tests only
- `-m architecture` — architecture tests only

---

## /project:test-fast

Run smoke tests only (fastest path).

```bash
DATABASE_URL="sqlite+aiosqlite:///:memory:" \
SECRET_KEY="test-secret-key-for-ci" \
ENVIRONMENT="testing" \
LLM_MOCK_MODE="1" \
pytest tests/smoke/ tests/test_health_endpoint.py tests/test_fastapi_health.py -v
```

---

## /project:lint

Check code style and imports.

```bash
ruff check . && isort --check-only .
```

Fix automatically:

```bash
ruff check . --fix && isort .
```

---

## /project:health

Check backend health endpoint.

```bash
curl -s http://localhost:8000/health | python3 -m json.tool
```

Expected response:
```json
{
    "status": "ok",
    "service": "cogniforge-api",
    "version": "..."
}
```

---

## /project:logs

Show recent backend activity (requires backend running in background).

```bash
# If running via workflow, check Replit console
# If running manually, logs appear in terminal

# Check if backend is alive
curl -s http://localhost:8000/health > /dev/null && echo "Backend: UP" || echo "Backend: DOWN"

# Check frontend
curl -s http://localhost:5000 > /dev/null && echo "Frontend: UP" || echo "Frontend: DOWN"
```

---

## /project:langgraph-test

Test LangGraph engine directly (bypasses HTTP/WebSocket).

```bash
python3 -c "
import asyncio
import sys
sys.path.insert(0, '.')

async def test():
    from app.services.chat.local_graph import run_local_graph

    print('Test 1: Arabic geography question...')
    r1 = await run_local_graph(
        question='أين تقع فرنسا؟',
        conversation_id='test-cli-001',
        history_messages=[]
    )
    print('Response:', r1[:200] if r1 else 'EMPTY')
    print()

    print('Test 2: Follow-up (memory test)...')
    r2 = await run_local_graph(
        question='ما هي عاصمتها؟',
        conversation_id='test-cli-001',
        history_messages=[]
    )
    print('Response:', r2[:200] if r2 else 'EMPTY')
    print()

    print('LangGraph: OK' if r1 and r2 else 'LangGraph: FAILED')

asyncio.run(test())
"
```

---

## /project:db-status

Check database connection and table status.

```bash
python3 -c "
import asyncio
import sys
sys.path.insert(0, '.')

async def check():
    from app.core.config import get_settings
    from app.core.database import engine
    from sqlalchemy import text

    s = get_settings()
    db_masked = (s.DATABASE_URL or '')[:40] + '...'
    print(f'DATABASE_URL: {db_masked}')

    async with engine.connect() as conn:
        result = await conn.execute(
            text(\"SELECT table_name FROM information_schema.tables WHERE table_schema = 'public' ORDER BY table_name\")
        )
        tables = [row[0] for row in result.fetchall()]
        print(f'Tables ({len(tables)}): {tables}')

asyncio.run(check())
"
```

---

## /project:check-settings

Print all settings (masked secrets).

```bash
python3 -c "
import sys
sys.path.insert(0, '.')
from app.core.config import get_settings

s = get_settings()
def mask(v): return str(v)[:8] + '...' if v and len(str(v)) > 8 else str(v)

print('=== CogniForge Settings ===')
print(f'ENVIRONMENT:           {s.ENVIRONMENT}')
print(f'DATABASE_URL:          {mask(s.DATABASE_URL)}')
print(f'SECRET_KEY:            {mask(s.SECRET_KEY)}')
print(f'OPENROUTER_API_KEY:    {mask(s.OPENROUTER_API_KEY)}')
print(f'OPENAI_API_KEY:        {mask(s.OPENAI_API_KEY)}')
print(f'ORCHESTRATOR_URL:      {s.ORCHESTRATOR_SERVICE_URL}')
print(f'FRONTEND_URL:          {s.FRONTEND_URL}')
print('==========================')
"
```

---

## /project:routes

List all registered API routes.

```bash
python3 -c "
import asyncio, sys
sys.path.insert(0, '.')

from app.main import app

routes = []
for route in app.routes:
    if hasattr(route, 'methods') and hasattr(route, 'path'):
        routes.append(f\"{sorted(route.methods)} {route.path}\")

for r in sorted(routes):
    print(r)
print(f'\nTotal: {len(routes)} routes')
"
```
