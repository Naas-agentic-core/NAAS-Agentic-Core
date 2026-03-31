# CogniForge Agents & Architecture Directives

## Philosophy: The Dual Heritage

This project adopts a fusion of two computer science methodologies. All code and architectural decisions must reflect this synthesis.

### 1. The Harvard Standard (CS50 2025)

*   **Strictest Typing:** No `Any`. Use `type | None` instead of `Optional`. Use generic collections (`list[str]`) not `List[str]`.
*   **Clarity:** Code must be understandable by a beginner but robust enough for an enterprise.
*   **Documentation:** Professional Arabic Docstrings are mandatory for all core components.
*   **Explicit is Better than Implicit:** Fail fast. Import explicitly.

### 2. The Berkeley Standard (SICP / CS61A)

*   **Abstraction Barriers:** Strictly separate implementation details from usage. A change in a lower-level library should not force a rewrite of high-level logic.
*   **Functional Core, Imperative Shell:** Prefer pure functions. Push side effects (I/O, DB) to the boundaries.
*   **Composition over Inheritance:** Build complex behaviors by composing simple functions or objects, not by deep class hierarchies.
*   **Data as Code:** Configuration should be declarative (data structures), interpreted by the system, rather than hard-coded logic steps.

---

## API-First Microservice Architecture (The Constitution)

The system is mandated to be **100% API First Microservice**.
All agents and developers must strictly adhere to the **100 Laws of Microservices** defined in the Constitution.

**[READ THE CONSTITUTION HERE](docs/architecture/MICROSERVICES_CONSTITUTION.md)** *(canonical — 100 laws, Arabic)*
*Quick English summary: [docs/ARCH_MICROSERVICES_CONSTITUTION.md](docs/ARCH_MICROSERVICES_CONSTITUTION.md)*

### Critical Laws Summary

1.  **Independence:** Each service is an island. Own DB, own deployment, own codebase.
2.  **API Communication:** Services speak ONLY via HTTP/gRPC or Async Events. No direct DB access to another service's data.
3.  **Polyglot & Containerized:** Use the best tool for the job, isolated in Docker.
4.  **Zero Trust:** Authenticate everything.
5.  **No Shared Libraries (Logic):** Do not share business logic libraries. Duplicate code if necessary to preserve independence (Rule 97/98).

---

## Coding Rules

### A. The Reality Kernel (System Root)

The `app/kernel.py` and `app/core` must act as the **Evaluator** of the system.
*   **Initialization:** Treat application startup as a functional pipeline: `Config -> AppState -> WeavedApp`.
*   **Middleware & Routes:** Define them as data (lists/registries) and "apply" them using higher-order functions.

### B. The Overmind (Cognitive Engine)

*   **State:** Use explicit State passing (like the `CollaborationContext` protocol) rather than global variables or singletons.
*   **Recursion:** Use tree recursion for planning and task decomposition where appropriate.

### C. Language & Style

*   **Docstrings:** Must be in **Professional Arabic**.
    *   *Example:* `"""يقوم هذا التابع بحساب المجموع التراكمي..."""`
*   **Type Hints:** Python 3.12+ Syntax.
    *   Use `def fn(x: int | float) -> list[str]:`
    *   Do NOT use `typing.Union`, `typing.List`.
*   **Imports:** Clean, sorted, and explicit.

---

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

Rules:
- Never place business logic in `app/api/` route handlers — use the service layer.
- Never import from `microservices/*` inside `app/*`.
- Never import from one microservice into another microservice.

---

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
| Run migrations | `alembic upgrade head` (run inside the service directory) |

Always run `ruff check .` and `mypy` before committing. CI will fail if either reports errors.

---

## Inter-Service Communication

All cross-service calls must use `httpx.AsyncClient`. Never instantiate a service class from another service's codebase.

```python
# Correct pattern — always pass X-Correlation-ID
async with httpx.AsyncClient(base_url=settings.ORCHESTRATOR_URL) as client:
    response = await client.post(
        "/missions",
        json=payload,
        headers={"X-Correlation-ID": trace_id},
        timeout=10.0,
    )
    response.raise_for_status()
```

Direct database access across service boundaries is forbidden (Constitution §5).
Use `X-Correlation-ID` on every outbound request for distributed tracing.

---

## Error Handling Contract

*   All HTTP errors must use `fastapi.HTTPException` with a structured `detail` dict:
    ```python
    raise HTTPException(
        status_code=404,
        detail={"code": "RESOURCE_NOT_FOUND", "message": "...", "trace_id": trace_id},
    )
    ```
*   Never let raw Python exceptions propagate to HTTP responses.
*   Log exceptions at `ERROR` level with `trace_id` before raising.
*   Cross-service errors must be re-raised as `HTTPException(502)` with the upstream `trace_id` preserved.

---

## Security Rules

*   Never commit `.env` files, secrets, or API keys.
*   Never log secret values, even at `DEBUG` level.
*   Never print or expose environment variable values in responses or logs.
*   All new endpoints must require authentication unless explicitly marked public in code review.
*   Use `settings` (Pydantic `BaseSettings`) for all configuration — no hard-coded values.
*   Secrets are injected at runtime via environment variables or a secrets manager, never stored in the repository.

---

## Testing

*   **Tests are Specifications:** Write tests that describe *behavior* (what it does), not implementation (how it does it).
*   **Coverage:** 100% ambition. Every branch must be checked.
*   Use `pytest-asyncio` with `asyncio_mode = "auto"` (configured in `pytest.ini`).
*   Use `sqlite+aiosqlite:///:memory:` for unit tests; never connect to a real database in unit tests.
*   Override `get_db` via `app.dependency_overrides` for route-level tests.
*   Test file naming: `test_<module_name>.py` mirroring the source tree.
*   Minimum per endpoint: one happy-path test + one error-path test.

---

## Skill Library

To empower agents with specialized expertise, the system includes verified skill modules in `docs/ai_skills/`.

### Skill Trigger Rules

Load the corresponding skill file **before generating any code** in that domain. Read the file each session — do not rely on memory.

| Condition | Load |
|-----------|------|
| Any file under `app/api/` or `microservices/*/src/` | `fastapi-templates.md` |
| Any SQLModel / Alembic / migration work | `database-schema-designer.md` |
| Any file under `app/core/` with CPU/memory concern | `python-performance-optimization.md` |
| Any file under `frontend/` | `vercel-react-best-practices.md` |
| Writing or reviewing a README | `crafting-effective-readmes.md` |
| UI component or CSS work | `web-design-guidelines.md` |

### Skill Index

| Skill file | Domain | Covers |
|------------|--------|--------|
| `vercel-react-best-practices.md` | Frontend (Next.js/React) | Waterfalls, bundle size, re-renders |
| `web-design-guidelines.md` | UI/UX Design | Styling, layout, accessibility |
| `fastapi-templates.md` | Backend (FastAPI) | Scaffolding and patterns for `app/api/` |
| `python-performance-optimization.md` | Python Core | Profiling, generators, async I/O |
| `database-schema-designer.md` | Database | SQLModel/SQLAlchemy schemas, migrations |
| `crafting-effective-readmes.md` | Documentation | README standards |

---

## Advanced Software Design Principles

See [PRINCIPLES.md](docs/architecture/PRINCIPLES.md) for the Arabic breakdown of SOLID, Architecture, and Quality standards.

---
*Verified by the Council of Wisdom.*
