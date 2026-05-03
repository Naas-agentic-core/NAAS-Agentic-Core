# تقرير التحليل الجراحي الشامل — CogniForge
## Surgical Forensic Analysis Report
**تاريخ التحليل:** 2 مايو 2026 | **الإصدار:** v4.1-root | **الغرض:** إعداد Claude Code

---

## LAYER 1: PROJECT TOPOLOGY

### الهيكل الكامل (3 مستويات)

```
/workspace/
├── app/                          # CORE: FastAPI monolith (port 8000)
│   ├── main.py                   # Entry point (logic-free bootstrapper)
│   ├── kernel.py                 # RealityKernel (middleware + routers + lifespan)
│   ├── cli.py                    # Typer CLI tool
│   ├── api/
│   │   ├── routers/              # 8 router files (الموجهات النشطة)
│   │   │   ├── admin.py          # Admin WS + endpoints
│   │   │   ├── customer_chat.py  # WebSocket /api/chat/ws
│   │   │   ├── security.py       # /api/security/login, /register
│   │   │   ├── ums.py            # /api/v1/auth/*, /api/v1/users/*
│   │   │   ├── content.py        # /v1/content/*
│   │   │   ├── data_mesh.py      # /api/v1/data-mesh/*
│   │   │   ├── observability.py  # Observability endpoints
│   │   │   └── registry.py       # Router registration (source of truth)
│   │   └── schemas/              # Pydantic request/response schemas
│   ├── core/
│   │   ├── settings/base.py      # AppSettings (Pydantic) — CRITICAL
│   │   ├── database.py           # Async SQLAlchemy engine
│   │   ├── db_schema.py          # Auto-create/fix tables on startup
│   │   ├── db_schema_config.py   # 18 table definitions
│   │   ├── app_blueprint.py      # Kernel spec builder
│   │   ├── config.py             # get_settings() re-export
│   │   ├── ai_gateway.py         # AI client factory
│   │   └── gateway/              # HTTP client utilities
│   ├── services/
│   │   ├── chat/                 # 70 files — LangGraph + history + retrieval
│   │   │   ├── local_graph.py    # NEW: LangGraph engine (ACTIVE)
│   │   │   └── graph/workflow.py # Multi-agent graph (dormant)
│   │   ├── security/
│   │   │   └── auth_persistence.py  # Registration/login persistence
│   │   ├── admin/                # Admin operations
│   │   ├── system/               # System services
│   │   ├── auth/                 # Token encoding/decoding
│   │   ├── users/                # User management
│   │   └── boundaries/           # Chat boundary enforcement
│   ├── infrastructure/
│   │   └── clients/
│   │       └── orchestrator_client.py  # Fallback chain orchestrator — CRITICAL
│   ├── middleware/               # CORS, rate limiter, security headers
│   ├── security/                 # OWASP checks, WAF
│   ├── telemetry/                # Unified observability
│   └── static/                   # Legacy UI (index.html, js/css)
├── frontend/                     # Next.js 16 app (port 5000)
│   ├── app/
│   │   ├── page.jsx              # Entry → ClientOnlyApp → CogniForgeApp
│   │   ├── layout.jsx            # RTL Arabic layout
│   │   ├── ClientOnlyApp.jsx     # Hydration guard
│   │   ├── components/
│   │   │   ├── CogniForgeApp.jsx # MAIN: auth + chat UI (1200+ lines)
│   │   │   ├── ChatInterface.jsx # Chat rendering (math/markdown)
│   │   │   └── AgentTimeline.jsx # Agent status display
│   │   └── hooks/
│   │       └── useAgentSocket.js # WebSocket connection hook
│   └── public/
│       └── js/legacy-app.jsx     # Legacy static UI (served by backend)
├── microservices/                # 10 services — ALL DORMANT in Replit
│   ├── orchestrator_service/     # Port 8006
│   ├── planning_agent/           # Port 8001
│   ├── memory_agent/             # Port 8002
│   ├── user_service/             # Port 8003
│   ├── observability_service/    # Port 8005
│   ├── api_gateway/              # Port 8000 (gateway)
│   ├── research_agent/           # Port 8007
│   ├── reasoning_agent/          # Port 8008
│   ├── auditor_service/          # Port 8009
│   └── conversation_service/     # Port 8010
├── shared/                       # Shared protocol (chat_protocol/)
├── tests/                        # ~100+ test files
├── scripts/                      # Dev scripts, security scan
├── infra/                        # k8s, terraform, postgres
├── config/                       # JSON configs, env examples
├── requirements.txt              # Production deps
├── requirements-ci.txt           # CI-only deps
├── docker-compose.yml            # Full microservices stack
├── Dockerfile                    # Main backend image
└── .github/workflows/            # 5 CI/CD workflows
```

### ملفات الإدخال (Entry Points)

| الملف | الوصف |
|---|---|
| `app/main.py` | FastAPI ASGI app — `uvicorn app.main:app` |
| `app/kernel.py` | `RealityKernel` — الـ bootstrap الكامل |
| `frontend/app/page.jsx` | Next.js root page |
| `app/cli.py` | Typer CLI (migrations, admin seeding) |

### ملفات الإعداد

| الملف | الحالة |
|---|---|
| `app/core/settings/base.py` | ✅ ACTIVE — مصدر الحقيقة الكامل |
| `config/breakglass_legacy.env.example` | نموذج طوارئ فقط |
| `.env.docker` | للتطوير بـ Docker |
| `.devcontainer/docker-compose.host.yml` | Codespaces فقط |
| `docker-compose.yml` | الـ microservices stack (لا يُشغَّل في Replit) |
| `pyproject.toml` | ruff + isort config |
| `pytest.ini` | asyncio_mode=auto |

---

## LAYER 2: TECHNOLOGY STACK

### Backend

| التقنية | الإصدار | الغرض |
|---|---|---|
| **Python** | 3.12.12 | Runtime |
| **FastAPI** | 0.109.2 | Web framework |
| **Uvicorn** | 0.27.1 | ASGI server |
| **SQLAlchemy** | 2.0.25 | ORM (async) |
| **Alembic** | 1.13.1 | Migrations (موجود في microservices فقط) |
| **asyncpg** | 0.29.0 | PostgreSQL async driver |
| **Pydantic** | 2.13.3 | Data validation |
| **pydantic-settings** | ≥2.4.0 | Settings from env |
| **LangGraph** | **1.1.10** | Agent graph engine (ACTIVE) |
| **langchain-core** | ≥0.3.0 | LangChain primitives |
| **OpenAI** | 2.33.0 | LLM client |
| **httpx** | 0.27.0 | Async HTTP client |
| **tenacity** | 8.2.3 | Retry logic |
| **PyJWT** | 2.8.0 | JWT tokens |
| **passlib + bcrypt** | 1.7.4 / 3.2.0 | Password hashing |
| **cryptography** | ≥41.0.0 | Encryption |
| **Redis** | ≥5.0.0 | Cache (اختياري — لا يعمل في Replit) |
| **sentence-transformers** | latest | Embeddings |
| **dspy** | latest | DSPy framework |
| **llama-index-core** | 0.14.13 | RAG/retrieval |
| **pandas** | 2.3.3 | Data processing |
| **websockets** | ≥12.0 | WebSocket support |

### Frontend

| التقنية | الإصدار | الغرض |
|---|---|---|
| **Node.js** | 20.x | Runtime |
| **Next.js** | **16.1.5** | Framework |
| **React** | 18.3.1 | UI |
| **react-dom** | 18.3.1 | DOM rendering |
| **axios** | ^1.13.2 | HTTP client |
| **react-markdown** | ^10.1.0 | Markdown rendering |
| **katex** | ^0.16.27 | Math rendering (LaTeX) |
| **rehype-katex + remark-math** | latest | Math في Markdown |
| **ESLint** | ^8.57.0 | Linting |

### DevOps

| المكون | التفاصيل |
|---|---|
| **Docker** | `Dockerfile` (Python 3.12-slim, Node 20, multi-stage) |
| **docker-compose.yml** | 20 service (لا يُشغَّل في Replit) |
| **GitHub Actions** | 5 workflows: `ci.yml`, `structure-validation.yml`, `comprehensive_testing.yml`, `knowledge_ingestion.yml`, `omega_pipeline.yml` |
| **CI trigger** | push/PR على `main` |
| **CI stack** | ruff lint → isort → pytest → structure validation |
| **k8s** | `infra/k8snginx/` (لا يُستخدم) |
| **Terraform** | `infra/terraform/` (لا يُستخدم) |

---

## LAYER 3: ACTIVE vs DORMANT CODE

### 🟢 ACTIVE — يعمل الآن في Replit

| المكون | الملف الرئيسي | الوصف |
|---|---|---|
| FastAPI monolith | `app/main.py` + `app/kernel.py` | المدخل الرئيسي على port 8000 |
| Router: security | `app/api/routers/security.py` | `/api/security/login`, `/register`, `/health` |
| Router: customer_chat | `app/api/routers/customer_chat.py` | WebSocket `/api/chat/ws` + conversations |
| Router: ums | `app/api/routers/ums.py` | `/api/v1/auth/*`, `/api/v1/users/*`, admin API |
| Router: admin | `app/api/routers/admin.py` | Admin WebSocket + stats |
| Router: content | `app/api/routers/content.py` | `/v1/content/*` |
| Router: system | `app/api/routers/system/` | `/health`, `/system/*`, asyncapi |
| **LangGraph local engine** | `app/services/chat/local_graph.py` | محرك LangGraph نشط (جديد) |
| Fallback orchestrator | `app/infrastructure/clients/orchestrator_client.py` | Fallback chain |
| Auth persistence | `app/services/security/auth_persistence.py` | Registration/login DB ops |
| DB schema auto-init | `app/core/db_schema.py` | 18 tables على startup |
| Settings | `app/core/settings/base.py` | AppSettings singleton |
| AI gateway | `app/core/ai_gateway.py` + `app/core/gateway/` | OpenRouter client |
| Frontend | `frontend/app/components/CogniForgeApp.jsx` | Auth + Chat UI |
| Legacy static UI | `app/static/index.html` | Backend-served fallback |

### 🟡 PARTIAL — موجود ومُستورَد لكن ليس كل مساراته تعمل

| المكون | الوصف |
|---|---|
| `app/services/chat/` (70 files) | local_graph نشط، workflow.py غير نشط |
| `app/services/system/` | 21 ملف، 19 نقطة استيراد — بعضها mock |
| `app/services/admin/` | يعمل لكن بعض endpoints تعتمد على microservices |
| `app/monitoring/` | Metrics + alerts موجودة لكن Redis غائب |
| `app/telemetry/` | Observability يعمل، OpenTelemetry بدون backend |
| `app/caching/` | memory_cache نشط، redis_cache معطوب (لا Redis) |
| `app/services/data_mesh/` | Routes موجودة، بعض العمليات mock |
| `app/security/owasp_*.py` | OWASP checks موجودة، بعضها لا يُطبَّق |

### 🔴 DORMANT — كود موجود لكن لا يُنفَّذ أبداً في Replit

| المكون | السبب |
|---|---|
| `microservices/` (جميع 10 خدمات) | تحتاج Docker — لا تعمل بدون `docker-compose up` |
| `app/services/chat/graph/workflow.py` | MAF Kernel (4 LLM calls) — استُبدل بـ local_graph |
| `app/services/agent_tools/` (37 files) | لا مستورِد نشط |
| `app/services/kagent/` | KAgent driver — لا microservice |
| `app/services/mcp/` | MCP server — يحتاج Claude CLI |
| `app/services/vision/` | Image analysis — لا إدماج |
| `app/services/project_context/` | 17 ملف، 0 استيراد من routers |
| `app/services/ai_security/` | AI security layer — 0 استيراد |
| `app/drivers/` | langgraph/dspy/llamaindex drivers — لا استخدام مباشر |
| `app/services/learning/` | Adaptive learning — لا route |
| `app/services/collaboration/` | Collaboration — لا route |
| `infra/k8s*`, `infra/terraform/` | Production infra — لا تعمل محلياً |

### ⚪ DEPRECATED — يُنصح بالحذف

| الملف | السبب |
|---|---|
| `PROJECT_DIAGNOSTIC_REPORT.md` | **330,569 سطر** — تقرير ضخم بلا فائدة |
| `attached_assets/*.txt` (6 ملفات) | conversation history مُلصقة |
| `api_coverage*.txt` (3 ملفات) | مخرجات قديمة |
| `*.md` (50+ ملف تشخيصي) | DIAGNOSIS, FORENSIC, ULTRA, SUPER — طالت جداً |
| `app/static/` | تُغني عنه `frontend/` |
| `commit_message.txt` | في root مباشرة — غير ضروري |

### Microservices Port Map (جميعها DORMANT في Replit)

| الخدمة | Port داخلي | Port خارجي |
|---|---|---|
| api-gateway | 8000 | 8000 |
| planning-agent | 8001 | 8001 |
| memory-agent | 8002 | 8002 |
| user-service | 8003 | 8003 |
| observability-service | 8005 | 8005 |
| **orchestrator-service** | **8006** | **8006** |
| research-agent | 8007 | 8007 |
| reasoning-agent | 8008 | 8008 |
| auditor-service | 8009 | 8009 |
| conversation-service | 8010 | 8010 |

---

## LAYER 4: ENVIRONMENT VARIABLES MAP

### Database

| المتغير | الحالة | الوصف |
|---|---|---|
| `APP_DATABASE_URL` | ✅ SET | Supabase PostgreSQL (يأخذ أولوية على DATABASE_URL) |
| `DATABASE_URL` | ✅ SET (auto) | يُعاد ضبطه تلقائياً من APP_DATABASE_URL |

### Authentication

| المتغير | الحالة | الوصف |
|---|---|---|
| `SECRET_KEY` | ✅ SET (in-memory) | ⚠️ ephemeral — يتغير عند كل restart |
| `ADMIN_EMAIL` | ❌ MISSING | يُستخدم default `admin@cogniforge.com` |
| `ADMIN_PASSWORD` | ❌ MISSING | يُستخدم default `change_me_please_123!` |
| `ADMIN_NAME` | ❌ MISSING | يُستخدم default `Supreme Administrator` |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | 🟡 default=11520 | 8 أيام |

### AI Services

| المتغير | الحالة | الوصف |
|---|---|---|
| `OPENROUTER_API_KEY` | ✅ SET | Primary AI provider (OpenRouter) |
| `OPENAI_API_KEY` | ✅ SET | Secondary AI provider |

### Microservice URLs (جميعها غائبة — تُحل تلقائياً إلى Docker DNS)

| المتغير | الحالة | القيمة الافتراضية |
|---|---|---|
| `ORCHESTRATOR_SERVICE_URL` | ❌ MISSING | → `http://orchestrator-service:8006` |
| `USER_SERVICE_URL` | ❌ MISSING | → `http://user-service:8000` |
| `RESEARCH_AGENT_URL` | ❌ MISSING | → `http://research-agent:8007` |
| `PLANNING_AGENT_URL` | ❌ MISSING | → `http://planning-agent:8000` |
| `REASONING_AGENT_URL` | ❌ MISSING | → `http://reasoning-agent:8008` |

### Infrastructure

| المتغير | الحالة | الوصف |
|---|---|---|
| `REDIS_URL` | ❌ MISSING | Redis غير متاح في Replit |
| `ENVIRONMENT` | ✅ SET=`development` | بيئة التطوير |
| `CODESPACES` | ❌ MISSING | false بشكل صحيح |
| `GITHUB_PERSONAL_ACCESS_TOKEN` | ✅ SET | للـ git push |

### Feature Flags (من الكود — لا env var مطلوب)

| المتغير | القيمة الافتراضية | الوصف |
|---|---|---|
| `ENABLE_STATIC_FILES` | true | يخدم `app/static/` |
| `API_STRICT_MODE` | true | صارم على الأمان |
| `LLM_MOCK_MODE` | (CI only) | Mock LLM في testing |

---

## LAYER 5: DEVELOPMENT WORKFLOWS

### تشغيل Backend محلياً

```bash
# Replit (الطريقة الرسمية — workflow: Backend)
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

# يدوياً
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

# عبر script
bash scripts/setup_dev.sh
```

### تشغيل Frontend محلياً

```bash
# Replit (workflow: Frontend)
cd frontend && npm run dev
# → http://localhost:5000 (Next.js مع RTL عربي)
```

### تشغيل Database Migrations

```bash
# الـ schema يُنشأ تلقائياً عند startup (db_schema.py)
# لا يوجد alembic في المسار الرئيسي (app/)
# alembic موجود فقط في microservices/*/

# إنشاء admin يدوياً
python app/cli.py db seed-admin
```

### تشغيل Tests

```bash
# كل الاختبارات
pytest tests/

# اختبارات محددة
pytest tests/api/ -v
pytest tests/architecture/ -v
pytest -m security
pytest -m architecture

# مع coverage
pytest --cov=app --cov-report=term-missing

# متغيرات بيئة مطلوبة في CI
export DATABASE_URL="sqlite+aiosqlite:///:memory:"
export SECRET_KEY="test-secret-key-for-ci-pipeline-secure-length"
export ENVIRONMENT="testing"
export LLM_MOCK_MODE="1"
```

### Linting / Formatting

```bash
ruff check .            # فحص الكود (pyproject.toml: line-length=100)
ruff check . --fix      # إصلاح تلقائي
isort --check-only .    # فحص ترتيب imports
black .                 # تنسيق (dev only)
bash scripts/format_code.sh  # تنسيق شامل
```

### Security Scan

```bash
bash scripts/security_scan.sh          # كامل (OWASP + Bandit + Semgrep)
bash scripts/security_scan.sh --fast   # سريع
bash scripts/security_scan.sh --code   # Bandit فقط
bash scripts/security_scan.sh --deps   # Dependency audit
```

### Docker — Microservices الكاملة

```bash
docker-compose up -d                    # جميع الخدمات
docker-compose up orchestrator-service  # خدمة واحدة
```

### Git Push إلى GitHub

```bash
# يحتاج GITHUB_PERSONAL_ACCESS_TOKEN (Replit secret)
git push "https://${GITHUB_PERSONAL_ACCESS_TOKEN}@github.com/HOUSSAM16ai/NAAS-Agentic-Core.git" main

# ملاحظة: git commit محظور في Replit main agent
# يُنجز عبر project task منفصل
```

---

## LAYER 6: KEY KNOWLEDGE FOR CLAUDE CODE

### 1. Project Conventions (الاصطلاحات)

- **اللغة:** كود Python بالإنجليزية، تعليقات ووثائق بالعربية الفصحى
- **Formatting:** `ruff` (line-length=100) + `isort` — `pyproject.toml` هو المرجع
- **Types:** Pydantic v2 صارم، TypedDict للـ LangGraph state
- **Imports:** absolute imports دائماً (`from app.core...`، لا relative)
- **Async:** كل شيء async/await — لا synchronous DB calls
- **Logging:** `logging.getLogger("cogniforge.module_name")` — structured JSON logs
- **Settings:** دائماً عبر `get_settings()` — لا `os.environ` مباشرة في الكود
- **Naming:** PascalCase للـ classes، snake_case للـ functions/variables
- **Context:** المنصة لخدمة الطلاب الجزائريين — العربية والدارجة والفرنسية

### 2. Critical Files — يجب عدم كسرها أبداً

| الملف | السبب |
|---|---|
| `app/core/settings/base.py` | كل شيء يعتمد عليه — كسره يوقف الـ backend |
| `app/kernel.py` | bootstrap كامل — router registration + lifespan |
| `app/core/database.py` | الاتصال بـ PostgreSQL |
| `app/core/db_schema.py` + `db_schema_config.py` | 18 جدول — تعديل دون دراية يُفسد DB |
| `app/infrastructure/clients/orchestrator_client.py` | fallback chain — أي خطأ = صمت كامل في الشات |
| `app/services/chat/local_graph.py` | محرك LangGraph — مثبَّت ومختبر |
| `app/services/security/auth_persistence.py` | `RETURNING id` PostgreSQL fix — لا تعكسه |
| `app/api/routers/registry.py` | مصدر الحقيقة للـ routes |
| `frontend/app/components/CogniForgeApp.jsx` | الواجهة الكاملة في ملف واحد |
| `frontend/next.config.js` | rewrites `/api/*` → backend:8000 |

### 3. Areas Safe to Modify

- `app/services/chat/local_graph.py` — إضافة nodes/edges جديدة للـ LangGraph
- `frontend/app/components/ChatInterface.jsx` — تحسين عرض الرسائل
- `frontend/app/components/AgentTimeline.jsx` — تحسين UI
- `app/api/routers/content.py` — content endpoints
- `app/core/prompts.py` — system prompts
- `app/services/system/` — system utilities
- `tests/` — إضافة اختبارات جديدة
- `scripts/` — scripts مساعدة

### 4. Areas Requiring Extreme Care ⚠️

| المنطقة | السبب |
|---|---|
| `app/core/settings/base.py` | validators معقدة — تعديل validator واحد قد يكسر startup |
| `app/core/db_schema_config.py` | 18 جدول — إضافة/حذف جدول = migration يدوي مطلوب |
| `app/services/security/auth_persistence.py` | `RETURNING id` fix لـ PostgreSQL — لا تستبدل بـ `lastrowid` |
| `app/infrastructure/clients/orchestrator_client.py` | fallback chain — الترتيب مهم جداً |
| JWT tokens + SECRET_KEY | SECRET_KEY ephemeral → restart = logout كل المستخدمين |
| `frontend/next.config.js` | rewrites `/api/*` → backend:8000 — كسره = 404 |
| `app/api/routers/registry.py` | إزالة router = endpoints مختفية بصمت |

### 5. Common Pitfalls

```python
# ❌ خاطئ — استخدام os.environ مباشرة
import os
db_url = os.environ["DATABASE_URL"]

# ✅ صحيح
from app.core.config import get_settings
db_url = get_settings().DATABASE_URL

# ❌ خاطئ — synchronous DB query
result = db.query(User).filter_by(email=email).first()

# ✅ صحيح
result = await db.execute(select(User).where(User.email == email))
user = result.scalar_one_or_none()

# ❌ خاطئ — افتراض أن microservices تعمل
# ORCHESTRATOR_SERVICE_URL → http://orchestrator-service:8006 → ConnectError دائماً

# ✅ صحيح — LangGraph هو الـ primary handler
# HTTP → ConnectError → LangGraph(local_graph.py) → OpenRouter → رد

# ❌ خاطئ — git commit مباشرة من main agent
# ✅ صحيح — create project task للـ git push

# ❌ خاطئ — تغيير DATABASE_URL مباشرة
# ✅ صحيح — استخدم APP_DATABASE_URL (يأخذ أولوية)

# ❌ خاطئ — port 6543 (PgBouncer)
# ✅ صحيح — settings تحوله تلقائياً إلى 5432
```

### 6. Testing Strategy

- **Framework:** pytest + pytest-asyncio (`asyncio_mode = auto`)
- **DB في Tests:** `sqlite+aiosqlite:///:memory:` (لا Postgres)
- **LLM في Tests:** `LLM_MOCK_MODE=1` يمنع calls حقيقية
- **Fixtures:** `tests/conftest.py` — `async_client`, `db_session`
- **Markers:** `security`, `architecture`
- **Coverage target:** `app/` directory
- **Structure:** `tests/api/`, `tests/architecture/`, `tests/integration/`, `tests/unit/`

### 7. Fallback Chain Architecture

```
WebSocket Request
      ↓
customer_chat.py router
      ↓
OrchestratorClient.chat_with_agent()
      ↓
[1] file_count detection      → إذا كان سؤالاً عن الملفات
      ↓
[2] exercise retrieval        → إذا كان تمرين BAC
      ↓
[3] HTTP → orchestrator-service:8006 → ConnectError (دائماً في Replit)
      ↓
[4] LangGraph local_graph.py  ← PRIMARY HANDLER (supervisor → chat → END)
      ↓
[5] _build_local_general_chat_response()  ← Safety net فقط
      ↓
Response streamed via WebSocket
```

### 8. LangGraph Architecture (local_graph.py)

```python
# State
class LocalChatState(TypedDict):
    question: str
    intent: str          # "educational" | "general" | "chat"
    history_messages: list[dict]
    final_response: str

# Graph Flow
supervisor_node → chat_node → END

# Memory
MemorySaver with thread_id = conversation_id
→ كل محادثة لها ذاكرة مستقلة

# Intent Classification
"educational": physics, math, BAC keywords
"general":     default
"chat":        greetings, short phrases

# System Prompts
Educational: متخصص للطلاب الجزائريين
General:     مساعد ذكي مع context
Chat:        ودود ومختصر
```

### 9. Database Schema (18 tables)

```
Authentication:   users, roles, permissions, user_roles, role_permissions, refresh_tokens
Audit:            audit_log
Chat:             customer_conversations, customer_messages
                  admin_conversations
Missions:         missions, mission_plans, tasks, mission_events
AI/Learning:      prompt_templates, generated_prompts, knowledge_nodes, knowledge_edges
```

**ملاحظة:** `knowledge_nodes.embedding` يحتاج `pgvector` extension — الـ index يُتخطى تلقائياً.

### 10. Known Issues & Pending Fixes

| المشكلة | الأولوية | الحل |
|---|---|---|
| SECRET_KEY ephemeral → logout عند restart | 🔴 عالية | إضافة `SECRET_KEY` كـ Replit secret ثابت |
| 157 GitHub vulnerability (15 critical) | 🔴 عالية | `pip audit` + `npm audit` + تحديث packages |
| OpenAPI contract warnings عند startup | 🟡 متوسطة | إضافة missing routes أو تحديث contract |
| `full_name` يرجع null في login response | 🟢 منخفضة | schema mismatch بسيط |
| ADMIN credentials hardcoded defaults | 🟡 متوسطة | تعيين env vars في Replit secrets |

---

## LAYER 7: FUTURE-READY ARCHITECTURE

### ما يجب إنشاؤه لـ Claude Code

#### `CLAUDE.md` — يجب أن يحتوي على:

```markdown
# CogniForge — Claude Code Context

## Project
AI educational platform for Algerian students.
FastAPI backend (port 8000) + Next.js 16 frontend (port 5000).
LangGraph activated for chat. All microservices DORMANT in Replit.

## Start Commands
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
cd frontend && npm run dev

## Critical Files (never break)
- app/core/settings/base.py
- app/kernel.py
- app/infrastructure/clients/orchestrator_client.py
- app/services/chat/local_graph.py
- app/core/db_schema_config.py

## Test Command
DATABASE_URL="sqlite+aiosqlite:///:memory:" SECRET_KEY="test-key" LLM_MOCK_MODE=1 pytest tests/

## Key Rules
- Always async/await for DB operations
- Use get_settings() never os.environ
- All microservices are unreachable — LangGraph handles chat
- Arabic comments in code are intentional
- git push requires project task (blocked in main agent)
```

#### `.claude/settings.json` — الإعدادات المقترحة:

```json
{
  "permissions": {
    "allow": [
      "Bash(uvicorn:*)",
      "Bash(pytest:*)",
      "Bash(ruff:*)",
      "Bash(npm run*)",
      "Bash(python -m*)",
      "Bash(curl:*)",
      "Read(**)",
      "Write(app/**)",
      "Write(frontend/**)",
      "Write(tests/**)",
      "Write(scripts/**)"
    ],
    "deny": [
      "Bash(git commit*)",
      "Bash(git push*)",
      "Bash(pip install*)",
      "Bash(npm install*)",
      "Write(app/core/db_schema_config.py)",
      "Write(app/core/settings/base.py)"
    ]
  },
  "env": {
    "APP_DATABASE_URL": "${APP_DATABASE_URL}",
    "DATABASE_URL": "${DATABASE_URL}",
    "OPENROUTER_API_KEY": "${OPENROUTER_API_KEY}",
    "ENVIRONMENT": "development",
    "PYTHONPATH": "/home/runner/workspace"
  }
}
```

#### `.devcontainer/devcontainer.json` — للعمل في Replit + Codespaces + VS Code:

```json
{
  "name": "CogniForge Dev",
  "dockerComposeFile": ".devcontainer/docker-compose.host.yml",
  "service": "web",
  "workspaceFolder": "/app",
  "features": {
    "ghcr.io/devcontainers/features/python:1": {"version": "3.12"},
    "ghcr.io/devcontainers/features/node:1": {"version": "20"}
  },
  "postCreateCommand": "pip install -r requirements.txt && cd frontend && npm install",
  "postStartCommand": "bash scripts/launch_stack.sh",
  "forwardPorts": [8000, 5000, 5432],
  "portsAttributes": {
    "8000": {"label": "Backend API", "onAutoForward": "notify"},
    "5000": {"label": "Frontend", "onAutoForward": "openBrowser"},
    "5432": {"label": "PostgreSQL", "onAutoForward": "silent"}
  },
  "remoteEnv": {
    "PYTHONPATH": "/app",
    "APP_DATABASE_URL": "${localEnv:APP_DATABASE_URL}",
    "OPENROUTER_API_KEY": "${localEnv:OPENROUTER_API_KEY}",
    "SECRET_KEY": "${localEnv:SECRET_KEY}"
  },
  "customizations": {
    "vscode": {
      "extensions": [
        "ms-python.python",
        "ms-python.pylance",
        "charliermarsh.ruff",
        "bradlc.vscode-tailwindcss",
        "dsznajder.es7-react-js-snippets"
      ],
      "settings": {
        "python.defaultInterpreterPath": "/usr/local/bin/python",
        "editor.formatOnSave": true,
        "python.linting.ruffEnabled": true
      }
    }
  }
}
```

#### Skills Directory Structure المقترح:

```
.claude/
├── settings.json
└── skills/
    ├── backend-dev.md        # FastAPI patterns, async DB, LangGraph
    ├── frontend-dev.md       # Next.js, WebSocket, Arabic RTL
    ├── langgraph-extend.md   # كيف تضيف node/edge جديد لـ local_graph.py
    ├── testing.md            # pytest patterns, fixtures, mock LLM
    ├── db-migration.md       # كيف تضيف جدول أو عمود بأمان
    └── git-workflow.md       # Push عبر project task
```

#### Custom Commands المقترحة لـ Claude Code:

```bash
# في .claude/commands/
/project:start-backend    → uvicorn app.main:app --reload
/project:start-frontend   → cd frontend && npm run dev
/project:test             → pytest tests/ -x -v
/project:test-fast        → pytest tests/smoke/ -v
/project:lint             → ruff check . && isort --check .
/project:lint-fix         → ruff check . --fix && isort .
/project:health-check     → curl -s localhost:8000/health | python -m json.tool
/project:langgraph-test   → python3 -c "import asyncio; from app.services.chat.local_graph import run_local_graph; ..."
/project:db-check         → python3 -c "from app.core.settings.base import get_settings; print(get_settings().DATABASE_URL)"
```

---

## ملخص تنفيذي

| الجانب | التفاصيل |
|---|---|
| **الحالة الراهنة** | Monolith FastAPI نشط 100% على Replit |
| **Microservices** | 10 خدمات موجودة — جميعها dormant — تحتاج Docker |
| **LangGraph** | مُفعَّل ومختبر (`local_graph.py`) — يعمل بـ MemorySaver |
| **Auth** | JWT custom — SECRET_KEY ephemeral (**⚠️ يجب إصلاحه بـ Replit secret**) |
| **Database** | PostgreSQL (Supabase) — 18 جدول تُنشأ تلقائياً |
| **أكبر خطر** | 157 vulnerability على GitHub — 15 critical |
| **أكبر هدر** | 50+ ملف تشخيصي + `PROJECT_DIAGNOSTIC_REPORT.md` بـ 330K سطر |
| **الخطوة الحرجة التالية** | تثبيت `SECRET_KEY` كـ Replit secret ثابت |

### خريطة المسار التقني الموصى به

```
المرحلة 1 — أمان فوري
  → إضافة SECRET_KEY كـ Replit secret ثابت
  → تعيين ADMIN_EMAIL + ADMIN_PASSWORD من env vars

المرحلة 2 — تنظيف الكود
  → حذف أو أرشفة 50+ ملف تشخيصي
  → حذف PROJECT_DIAGNOSTIC_REPORT.md (330K سطر)
  → تحديث الـ packages الحرجة (15 critical vulnerabilities)

المرحلة 3 — توسيع LangGraph
  → إضافة retrieval node (BAC exercises)
  → إضافة memory persistence (PostgreSQL بدلاً من MemorySaver)
  → إضافة streaming support للـ LangGraph responses

المرحلة 4 — تفعيل Microservices (اختياري)
  → تشغيل orchestrator-service محلياً
  → ربط LangGraph بالـ orchestrator الحقيقي
```

---

*تم إنشاء هذا التقرير بتحليل جراحي كامل للمشروع — 2 مايو 2026*
