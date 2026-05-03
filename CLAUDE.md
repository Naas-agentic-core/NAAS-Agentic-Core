# CogniForge — Claude Code Context

> **AI tutor for Algerian students** | FastAPI 8000 + Next.js 5000 + LangGraph 1.1.10
> Arabic / French / Darija | BAC preparation platform

---

## 1. What This Project Does

CogniForge is an educational AI platform for Algerian high-school students preparing for the Baccalaureate exam. Students chat in Arabic, French, or Darija and receive tutoring in math, physics, and sciences. The backend is a FastAPI monolith. All microservices visible in `microservices/` are **fully dormant in Replit** — they require Docker and never start here.

---

## 2. Start Commands

```bash
# Backend (port 8000)
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

# Frontend (port 5000)
cd frontend && npm run dev

# Health check
curl -s http://localhost:8000/health | python -m json.tool
```

---

## 3. Architecture at a Glance

```
Browser
  └── Next.js (port 5000)
        └── next.config.js rewrites /api/* → localhost:8000
              └── FastAPI (port 8000)
                    ├── /api/security/login, /register
                    ├── /api/chat/ws  (WebSocket)
                    │     └── OrchestratorClient (fallback chain)
                    │           ├── [1] File count detection
                    │           ├── [2] Exercise retrieval (BAC)
                    │           ├── [3] HTTP → orchestrator:8006 → ConnectError (DORMANT)
                    │           └── [4] LangGraph local_graph.py ← PRIMARY HANDLER
                    ├── /api/v1/auth/*, /api/v1/users/*
                    ├── /v1/content/*
                    └── /api/v1/data-mesh/*
```

**LangGraph flow:**
```
supervisor_node → chat_node → END
     ↓
Intent: "educational" | "general" | "chat"
Memory: MemorySaver(thread_id=conversation_id)
LLM: OpenRouter (OPENROUTER_API_KEY)
```

---

## 4. Critical Files — Never Break These

| File | Why Critical |
|---|---|
| `app/core/settings/base.py` | All config lives here — break it = backend won't start |
| `app/kernel.py` | Full bootstrap: middleware + routers + lifespan |
| `app/core/database.py` | PostgreSQL async engine factory |
| `app/core/db_schema.py` | Auto-creates 18 tables on startup |
| `app/core/db_schema_config.py` | 18 table definitions — change requires manual migration |
| `app/infrastructure/clients/orchestrator_client.py` | Fallback chain — break it = chat goes silent |
| `app/services/chat/local_graph.py` | LangGraph engine — tested and verified working |
| `app/services/security/auth_persistence.py` | PostgreSQL `RETURNING id` fix — do NOT revert |
| `app/api/routers/registry.py` | Source of truth for all routes |
| `frontend/next.config.js` | `/api/*` rewrites — break it = 404 on all API calls |
| `frontend/app/components/CogniForgeApp.jsx` | Entire frontend auth + chat in one component |

---

## 5. Safe Areas to Modify

```
app/services/chat/local_graph.py    — add LangGraph nodes/edges
app/api/routers/content.py          — content endpoints
app/core/prompts.py                 — system prompts
app/services/system/                — system utilities
frontend/app/components/ChatInterface.jsx
frontend/app/components/AgentTimeline.jsx
tests/                              — add tests freely
scripts/                            — helper scripts
docs/                               — documentation
```

---

## 6. Common Pitfalls

### NEVER use `os.environ` directly in app code
```python
# ❌ Wrong
import os
db_url = os.environ["DATABASE_URL"]

# ✅ Correct
from app.core.config import get_settings
db_url = get_settings().DATABASE_URL
```

### NEVER use synchronous SQLAlchemy
```python
# ❌ Wrong — blocks the event loop
user = db.query(User).filter_by(email=email).first()

# ✅ Correct
from sqlalchemy import select
result = await db.execute(select(User).where(User.email == email))
user = result.scalar_one_or_none()
```

### NEVER assume microservices are reachable
```python
# In Replit, ALL of these fail with ConnectError:
# http://orchestrator-service:8006  → Docker DNS — not running
# http://user-service:8000          → not running
# http://research-agent:8007        → not running

# LangGraph (local_graph.py) is the REAL handler — always falls through to it
```

### NEVER change the auth_persistence.py RETURNING pattern
```python
# ❌ Wrong — lastrowid doesn't work reliably with asyncpg/PostgreSQL
cursor = await conn.execute(insert_query)
user_id = cursor.lastrowid

# ✅ Correct — what's already there
result = await conn.execute(
    text("INSERT INTO users (...) VALUES (...) RETURNING id")
)
user_id = result.scalar()
```

### Port quirk
```python
# settings auto-converts PgBouncer port 6543 → 5432
# Don't override this behavior in database.py
```

---

## 7. Testing

```bash
# Run all tests
pytest tests/

# Specific suites
pytest tests/api/ -v
pytest tests/architecture/ -v
pytest -m security
pytest -m architecture

# With coverage
pytest --cov=app --cov-report=term-missing

# REQUIRED environment for tests (SQLite in-memory, mock LLM)
export DATABASE_URL="sqlite+aiosqlite:///:memory:"
export SECRET_KEY="test-secret-key-for-ci-pipeline-secure-length"
export ENVIRONMENT="testing"
export LLM_MOCK_MODE="1"
export SUPABASE_URL="https://dummy.supabase.co"
export SUPABASE_ROLE_KEY="dummy"
```

**Framework:** pytest + pytest-asyncio (`asyncio_mode = auto` in `pytest.ini`)
**DB in tests:** SQLite in-memory — no PostgreSQL needed
**LLM in tests:** `LLM_MOCK_MODE=1` blocks all real API calls

---

## 8. Linting

```bash
ruff check .          # check (line-length=100, config in pyproject.toml)
ruff check . --fix    # auto-fix
isort --check-only .  # check import order
isort .               # fix import order
```

---

## 9. Database Schema (18 Tables)

```
Authentication:  users, roles, permissions, user_roles, role_permissions, refresh_tokens
Audit:           audit_log
Chat:            customer_conversations, customer_messages, admin_conversations
Missions:        missions, mission_plans, tasks, mission_events
AI/Learning:     prompt_templates, generated_prompts, knowledge_nodes, knowledge_edges
```

- All tables **auto-created on startup** by `app/core/db_schema.py`
- Adding a new table: edit `app/core/db_schema_config.py` + `_ALLOWED_TABLES` frozenset
- `knowledge_nodes.embedding` requires `pgvector` — index is **skipped silently** if extension missing

---

## 10. Environment Variables

| Variable | Status | Description |
|---|---|---|
| `APP_DATABASE_URL` | ✅ Set (Replit secret) | Supabase PostgreSQL — takes priority |
| `DATABASE_URL` | ✅ Auto-set | Re-derived from APP_DATABASE_URL |
| `SECRET_KEY` | ⚠️ In-memory | **Ephemeral — restart = all users logged out** |
| `OPENROUTER_API_KEY` | ✅ Set | Primary LLM provider |
| `OPENAI_API_KEY` | ✅ Set | Secondary LLM provider |
| `ENVIRONMENT` | ✅ `development` | Controls dev behavior |
| `ORCHESTRATOR_SERVICE_URL` | ❌ Not set | Defaults to Docker DNS — always fails in Replit |
| `REDIS_URL` | ❌ Not set | Redis unavailable in Replit — cache falls back to memory |

---

## 11. Code Conventions

- **Language:** Python code in English, comments/docstrings in Arabic
- **Formatting:** `ruff` at line-length=100, `isort` for imports
- **Types:** Pydantic v2 strict, `TypedDict` for LangGraph state
- **Imports:** Always absolute (`from app.core...` — never relative)
- **Async:** Everything async/await — zero synchronous DB calls
- **Logging:** `logging.getLogger("cogniforge.module_name")`
- **Settings:** Always `get_settings()` — never `os.environ` in app code
- **Naming:** `PascalCase` classes, `snake_case` functions/variables

---

## 12. LangGraph Extension Guide

To add a new node to `app/services/chat/local_graph.py`:

```python
# 1. Add to state
class LocalChatState(TypedDict):
    question: str
    intent: str
    history_messages: list[dict]
    final_response: str
    # new_field: str  ← add here

# 2. Define node function
async def my_new_node(state: LocalChatState) -> dict:
    # process state
    return {"final_response": "..."}

# 3. Add to graph
graph.add_node("my_new_node", my_new_node)
graph.add_edge("supervisor", "my_new_node")
graph.add_edge("my_new_node", END)

# 4. Update routing in supervisor_node if needed
```

---

## 13. Known Issues (Priority Order)

| Issue | Priority | Fix |
|---|---|---|
| `SECRET_KEY` ephemeral → logout on restart | 🔴 High | Add `SECRET_KEY` as permanent Replit secret |
| 157 GitHub vulnerabilities (15 critical) | 🔴 High | `pip audit` + `npm audit` + update packages |
| `full_name` returns null in login response | 🟡 Medium | Schema mismatch in auth response |
| OpenAPI contract warnings on startup | 🟡 Medium | Missing route definitions |
| Admin credentials using hardcoded defaults | 🟡 Medium | Set ADMIN_EMAIL/ADMIN_PASSWORD env vars |

---

## 14. Microservices (All Dormant in Replit)

These exist in `microservices/` but **never start** in Replit — they need Docker:

| Service | Port | Status |
|---|---|---|
| orchestrator-service | 8006 | DORMANT — ConnectError expected |
| planning-agent | 8001 | DORMANT |
| memory-agent | 8002 | DORMANT |
| user-service | 8003 | DORMANT |
| research-agent | 8007 | DORMANT |
| reasoning-agent | 8008 | DORMANT |
| auditor-service | 8009 | DORMANT |
| conversation-service | 8010 | DORMANT |

To run all microservices locally: `docker-compose up -d`

---

*Last updated: May 2026 — based on forensic analysis v4.1-root*
