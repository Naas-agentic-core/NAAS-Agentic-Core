# Newcomer Codebase Map

This guide is a practical orientation for developers who are opening the repository for the first time.

## 1) What this repository is trying to do

The project is an API-first safety and tutoring platform. It combines a main FastAPI core (`app/`) with a microservices workspace (`microservices/`) and strong governance/testing documentation.

Start with these anchors:
- `README.md` for mission, safety framing, and high-level map.
- `docs/ARCHITECTURE.md` for layer boundaries.
- `docs/architecture/MICROSERVICES_CONSTITUTION.md` for strict microservice laws.

## 2) Top-level structure (mental model)

- `app/`: Main FastAPI runtime and shared core building blocks.
- `microservices/`: Independently scoped services (gateway, memory, user, orchestrator, observability, etc.).
- `tests/`: Cross-cutting test suites (architecture, contracts, integration, security, performance).
- `docs/`: Architecture, governance, contracts, diagnostics, and contributor guides.
- `scripts/`: CI guards, fitness checks, and utilities.
- `infra/`: Infrastructure as code and deployment assets.
- `frontend/`: Web app and static client assets.
- `toolkit/`: Partner-facing operational resources.

## 3) Runtime entry and composition

- `app/main.py` is intentionally thin; it bootstraps settings and builds the app through `RealityKernel`.
- `app/kernel.py` applies middleware/router registries and performs startup checks (schema validation, admin bootstrap, observability, event bridge).

This reflects a "functional core, imperative shell" style: composition and declarations first, side effects in lifecycle boundaries.

## 4) Architecture constraints that matter in daily work

- API-first and contract-aware runtime checks (OpenAPI/AsyncAPI alignment) are part of startup.
- Services are expected to communicate through APIs/events, not shared business-logic internals.
- Keep domain logic separated from transport/framework code.

## 5) New contributor path (recommended)

1. Read: `README.md` → `docs/START_HERE.md` → `docs/ARCHITECTURE.md`.
2. Explore service map: `microservices/README.md`.
3. Run quality gates locally (`ruff`, `pytest`, guardrail scripts) before opening PRs.
4. Trace one feature end-to-end from router to domain logic to tests.

## 6) What to learn next

- Contract-first development (OpenAPI/AsyncAPI files + runtime validation).
- Testing strategy breadth (`tests/architecture`, `tests/contract`, `tests/integration`, `tests/security`).
- Migration status and architecture governance docs in `docs/architecture/` and `docs/diagnostics/`.
- Operational workflows in `.github/workflows/` and `scripts/ci`.

## 7) Quick navigation commands

```bash
# High-level project map
python app/tooling/repository_map.py --max-depth 2

# Find likely entrypoints
rg -n "create_app|RealityKernel|FastAPI\(" app

# Explore tests by concern
find tests -maxdepth 2 -type d | sort
```
