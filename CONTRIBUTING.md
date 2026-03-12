# Contributing to NAAS-Agentic-Core

This repository enforces **deterministic CI, architectural guardrails, and safeguarding-first governance**.
If your PR passes locally with the commands below, it should be merge-ready for `required-ci`.

## 1) Local setup (source of truth)

```bash
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements-dev.txt
pip install -r requirements-test.txt
```

## 2) Required local checks before opening a PR

```bash
ruff check .
ruff format --check .
python scripts/ci_guardrails.py
python scripts/fitness/check_no_app_imports_in_microservices.py --strict
python scripts/fitness/check_routes_registry_parity.py
python scripts/fitness/check_tracing_gate.py
pytest -v --cov=app --cov-report=term-missing --tb=short
```

## 3) CI mergeability model

Branch protection should require only one status check:
- `required-ci`

`required-ci` aggregates and blocks on:
- `lint`
- `contracts`
- `guardrails`
- `test`

Do not add extra merge-blocking checks without updating:
1. `.github/workflows/ci.yml`
2. `.github/BRANCH_PROTECTION_GUIDE.md`
3. this `CONTRIBUTING.md`

## 4) Architectural contribution rules

- No direct imports from `app/` inside `microservices/` modules.
- Keep route registries and runtime routes in parity.
- Keep tracing gate checks passing.
- Keep docs/runtime/contracts in sync when behavior changes.

## 5) Dependency policy

- Runtime dependencies: `requirements-prod.txt`.
- Test dependencies: `requirements-test.txt` (extends prod).
- Dev tooling: `requirements-dev.txt` (extends prod).
- Do not add duplicated packages across files with conflicting pins.

## 6) PR quality bar

Every PR must include:
- scope + risk statement
- rollback plan
- exact validation commands executed
- linked issue or rationale for untracked work

Use `.github/PULL_REQUEST_TEMPLATE.md` exactly; do not remove governance sections.

## 7) Security and safeguarding

- Never commit real user data, PII, or secrets.
- For vulnerabilities, use `SECURITY.md` private disclosure channel.
- Youth-safeguarding changes must reference `SAFEGUARDING.md` and `DATA_POLICY.md`.
