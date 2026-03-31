# AGENTS.md Improvement Specification

**Scope:** `AGENTS.md` + `docs/ai_skills/*.md`  
**Status:** Draft — ready for implementation

---

## 1. Audit Summary

### 1.1 What Is Good

| Item | Assessment |
|------|------------|
| Dual-heritage philosophy (CS50 + SICP) | Clear, memorable framing that gives agents a coherent mental model |
| Python 3.12+ type-hint rules | Concrete and unambiguous (`int \| None`, `list[str]`) |
| Arabic docstring mandate | Consistent with project identity; well-exemplified |
| Skill library table | Correct domain-to-file mapping; easy to scan |
| Microservices Constitution reference | Points to the right authoritative document |
| `fastapi-templates.md` | Solid patterns: lifespan, DI, repository, service layer, async sessions |
| `database-schema-designer.md` | Thorough: normalization, indexing, migration, anti-patterns, checklist |
| `python-performance-optimization.md` | Covers profiling, generators, async I/O, memory — actionable checklist |

### 1.2 What Is Missing

| Gap | Impact |
|-----|--------|
| **No workflow trigger rules** — agents are told *what* skills exist but not *when* to load them automatically | Agents skip skill files unless they remember to check |
| **No file-path conventions** — no rule about where new services, schemas, or tests must live | Agents create files in arbitrary locations |
| **No commit / PR standards** — no message format, no branch naming, no PR description template | Inconsistent git history |
| **No environment / tooling section** — no mention of `make`, `pytest`, `ruff`, `mypy`, Docker Compose targets | Agents run wrong commands or invent their own |
| **No error-handling contract** — no rule on how exceptions must be raised, logged, or surfaced across service boundaries | Inconsistent error shapes in API responses |
| **No inter-service communication pattern** — Constitution exists but AGENTS.md does not summarise the HTTP client pattern agents must use | Agents may call services directly or use wrong client |
| **`web-design-guidelines.md` is a stub** — it only fetches a remote URL; no offline content | Fails in air-gapped or offline environments |
| **`crafting-effective-readmes.md` is incomplete** — references `templates/oss.md` that does not exist in the repo | Broken skill reference |
| **No testing conventions** — no mention of `pytest-asyncio`, fixture patterns, or which test database to use | Agents write incompatible tests |
| **No security rules for agents** — no guidance on secrets, `.env` handling, or what must never be committed | Risk of accidental credential exposure |
| **Constitution path is wrong in AGENTS.md** — links to `docs/architecture/MICROSERVICES_CONSTITUTION.md` but the canonical file is also at `docs/ARCH_MICROSERVICES_CONSTITUTION.md`; two copies exist | Confusion about which is authoritative |

### 1.3 What Is Wrong

| Issue | Severity |
|-------|----------|
| **Broken cross-reference:** `AGENTS.md` links `docs/architecture/MICROSERVICES_CONSTITUTION.md` and `docs/architecture/PRINCIPLES.md` — both exist, but `AGENTS.md` is also embedded verbatim in the system prompt (coding-rules), creating a duplicate source of truth | High |
| **`fastapi-templates.md` uses deprecated patterns:** `obj_in.dict()` (Pydantic v1) should be `obj_in.model_dump()`; `declarative_base()` is deprecated in SQLAlchemy 2.x in favour of `DeclarativeBase` | High |
| **`fastapi-templates.md` uses `typing.List`, `typing.Optional`** in several code blocks — contradicts the no-`typing.*` rule in AGENTS.md | Medium |
| **`fastapi-templates.md` references non-existent assets:** `references/fastapi-architecture.md`, `assets/project-template/`, `assets/docker-compose.yml` | Medium |
| **`database-schema-designer.md` uses MySQL-specific syntax** (`AUTO_INCREMENT`, `TINYINT(1)`) without noting PostgreSQL equivalents — the project uses PostgreSQL | Medium |
| **`vercel-react-best-practices.md` is frontend-only** but the skill table in AGENTS.md marks it "Critical for `frontend/` changes" without noting the project's frontend stack (Next.js in `frontend/`) — agents may apply it to the wrong layer | Low |
| **No version pinning on skill files** — skills have `version: "1.0.0"` in frontmatter but AGENTS.md never instructs agents to check or update versions | Low |
| **Emoji overuse in AGENTS.md** — decorative emoji (`🌟`, `🏛️`, `🛠️`, `🧪`, `📚`, `📜`) add noise without semantic value in a technical directive document | Low |

---

## 2. Improvement Specification

### 2.1 `AGENTS.md` — Required Changes

#### 2.1.1 Fix broken/ambiguous references

```
CURRENT:  docs/architecture/MICROSERVICES_CONSTITUTION.md
CURRENT:  docs/architecture/PRINCIPLES.md

ACTION:   Verify which copy is canonical. Delete the duplicate.
          Update AGENTS.md to point to the single authoritative path.
          Add a note: "Do not create a second copy of this file."
```

#### 2.1.2 Add automatic skill-loading triggers

Add a section **"Skill Loading Rules"** immediately after the skill table:

```markdown
## Skill Loading Rules

Load the corresponding skill file **before generating any code** in that domain.
Do not rely on memory — read the file each session.

| Condition | Load |
|-----------|------|
| Any file under `app/api/` or `microservices/*/src/` | `fastapi-templates.md` |
| Any SQLModel / Alembic / migration work | `database-schema-designer.md` |
| Any file under `app/core/` with CPU/memory concern | `python-performance-optimization.md` |
| Any file under `frontend/` | `vercel-react-best-practices.md` |
| Writing or reviewing a README | `crafting-effective-readmes.md` |
| UI component or CSS work | `web-design-guidelines.md` |
```

#### 2.1.3 Add file-path conventions

Add a section **"Repository Layout Contract"**:

```markdown
## Repository Layout Contract

| Artefact | Canonical location |
|----------|--------------------|
| New microservice | `microservices/<service_name>/` |
| Shared gateway logic | `app/` (never `microservices/`) |
| Alembic migrations | `microservices/<service_name>/migrations/` |
| Integration tests | `tests/integration/` |
| Unit tests | `tests/unit/` |
| OpenAPI contracts | `docs/contracts/<service_name>.yaml` |
| ADRs | `docs/architecture/adr/` |

Never place business logic in `app/api/` route handlers — use the service layer.
Never import from `microservices/*` inside `app/*`.
```

#### 2.1.4 Add tooling / environment commands

Add a section **"Development Commands"**:

```markdown
## Development Commands

| Task | Command |
|------|---------|
| Run all tests | `pytest` |
| Run with coverage | `pytest --cov=app --cov=microservices` |
| Lint | `ruff check .` |
| Format | `ruff format .` |
| Type-check | `mypy app/ microservices/` |
| Start full stack | `docker compose up` |
| Start single service | `docker compose up <service_name>` |
| Run migrations | `alembic upgrade head` (inside service directory) |

Always run `ruff check` and `mypy` before committing.
```

#### 2.1.5 Add error-handling contract

Add a section **"Error Handling Contract"**:

```markdown
## Error Handling Contract

- All HTTP errors must use `fastapi.HTTPException` with a structured `detail` dict:
  `{"code": "RESOURCE_NOT_FOUND", "message": "...", "trace_id": "..."}`
- Never let raw Python exceptions propagate to HTTP responses.
- Log exceptions at `ERROR` level with `trace_id` before raising.
- Cross-service errors must be re-raised as `HTTPException(502)` with the upstream
  `trace_id` preserved.
- Use `X-Correlation-ID` header for all outbound `httpx` calls.
```

#### 2.1.6 Add inter-service communication pattern

Add a section **"Inter-Service Communication"**:

```markdown
## Inter-Service Communication

All cross-service calls must use `httpx.AsyncClient` via the shared gateway client
in `app/gateway/`. Never instantiate a service class from another service.

```python
# Correct pattern
async with httpx.AsyncClient(base_url=settings.ORCHESTRATOR_URL) as client:
    response = await client.post(
        "/missions",
        json=payload,
        headers={"X-Correlation-ID": trace_id},
    )
    response.raise_for_status()
```

Direct database access across service boundaries is forbidden (Constitution §5).
```

#### 2.1.7 Add security rules

Add a section **"Security Rules for Agents"**:

```markdown
## Security Rules for Agents

- Never commit `.env` files, secrets, or API keys.
- Never log secret values, even at DEBUG level.
- Never print or expose environment variable values in responses.
- All new endpoints must require authentication unless explicitly marked public.
- Use `settings` (Pydantic `BaseSettings`) for all configuration — no hard-coded values.
```

#### 2.1.8 Add testing conventions

Expand the Testing section:

```markdown
## Testing Conventions

- Use `pytest-asyncio` with `asyncio_mode = "auto"` (set in `pytest.ini`).
- Use `sqlite+aiosqlite:///:memory:` for unit tests; never connect to production DB.
- Override `get_db` dependency in `app.dependency_overrides` for route tests.
- Test file naming: `test_<module_name>.py` mirroring the source tree.
- Each test must assert behaviour, not implementation — test the HTTP response,
  not internal function calls.
- Minimum: one happy-path test + one error-path test per endpoint.
```

#### 2.1.9 Remove decorative emoji

Replace section headers that use emoji with plain text headers. Emoji in headings
break some markdown renderers and add no semantic value in a technical directive.

---

### 2.2 `docs/ai_skills/fastapi-templates.md` — Required Changes

| # | Change |
|---|--------|
| 1 | Replace all `obj_in.dict()` with `obj_in.model_dump()` (Pydantic v2) |
| 2 | Replace `declarative_base()` with `class Base(DeclarativeBase): pass` (SQLAlchemy 2.x) |
| 3 | Replace `typing.List`, `typing.Optional` with `list[...]`, `... \| None` throughout |
| 4 | Remove references to non-existent assets (`references/`, `assets/`) or replace with actual repo paths |
| 5 | Add a note at the top: "This project uses PostgreSQL. Use `asyncpg` driver: `postgresql+asyncpg://`" |
| 6 | Add `model_config = ConfigDict(from_attributes=True)` to Pydantic schema examples |

---

### 2.3 `docs/ai_skills/database-schema-designer.md` — Required Changes

| # | Change |
|---|--------|
| 1 | Add a project-specific note at the top: "This project uses PostgreSQL 15+. Prefer `BIGSERIAL` over `AUTO_INCREMENT`, `BOOLEAN` over `TINYINT(1)`." |
| 2 | Add SQLModel/SQLAlchemy 2.x ORM examples alongside raw SQL (the project uses SQLModel) |
| 3 | Add Alembic migration template matching the project's `alembic.ini` structure |

---

### 2.4 `docs/ai_skills/web-design-guidelines.md` — Required Changes

| # | Change |
|---|--------|
| 1 | Add offline fallback content — the current skill only fetches a remote URL; if the network is unavailable the skill is useless |
| 2 | Add the project's design tokens / Tailwind config path so agents know where to find colours and spacing |
| 3 | Add accessibility baseline: WCAG 2.1 AA minimum, `aria-label` on all interactive elements |

---

### 2.5 `docs/ai_skills/crafting-effective-readmes.md` — Required Changes

| # | Change |
|---|--------|
| 1 | Remove references to `templates/oss.md`, `templates/personal.md` — these files do not exist |
| 2 | Inline a minimal README template directly in the skill file |
| 3 | Add a project-specific note: "This repo uses Arabic docstrings; README files must be in English" |

---

## 3. Priority Order

| Priority | Item | Effort |
|----------|------|--------|
| P0 | Fix broken Constitution path (single source of truth) | 5 min |
| P0 | Fix Pydantic v2 / SQLAlchemy 2.x patterns in `fastapi-templates.md` | 30 min |
| P1 | Add skill-loading trigger rules to `AGENTS.md` | 15 min |
| P1 | Add file-path conventions to `AGENTS.md` | 15 min |
| P1 | Add development commands to `AGENTS.md` | 10 min |
| P2 | Add error-handling contract to `AGENTS.md` | 15 min |
| P2 | Add inter-service communication pattern to `AGENTS.md` | 15 min |
| P2 | Add security rules to `AGENTS.md` | 10 min |
| P2 | Add testing conventions to `AGENTS.md` | 15 min |
| P3 | Fix `typing.*` usage in `fastapi-templates.md` | 20 min |
| P3 | Add PostgreSQL notes to `database-schema-designer.md` | 20 min |
| P3 | Add offline content to `web-design-guidelines.md` | 30 min |
| P3 | Fix broken template references in `crafting-effective-readmes.md` | 15 min |
| P4 | Remove decorative emoji from `AGENTS.md` headings | 5 min |

---

*Generated by audit of `AGENTS.md`, `docs/ai_skills/*.md`, `docs/architecture/MICROSERVICES_CONSTITUTION.md`, `docs/architecture/PRINCIPLES.md`, and the live repository structure.*
