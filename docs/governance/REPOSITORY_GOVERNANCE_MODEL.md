# Repository Governance Operating Model

## Ownership zones

- Platform core: `app/`, `tests/`, `scripts/`
- Service boundaries: `microservices/*`
- Governance and delivery: `.github/`, `docs/`, `infra/`

Code ownership is enforced via `.github/CODEOWNERS`.

## Label taxonomy (minimum enforceable set)

### Type
- `type:bug`
- `type:feature`
- `type:refactor`
- `type:docs`
- `type:security`

### Priority
- `priority:P0`
- `priority:P1`
- `priority:P2`

### Area
- `area:app-core`
- `area:microservices`
- `area:ci-cd`
- `area:contracts`
- `area:governance`

### Status
- `status:needs-triage`
- `status:blocked`
- `status:ready`

## Release & versioning policy

- Versioning: SemVer (`MAJOR.MINOR.PATCH`).
- Cut release tags from `main` only after `required-ci` green.
- Maintain `CHANGELOG.md` with categories:
  - Added
  - Changed
  - Fixed
  - Security
- Security fixes must include advisory reference or internal incident ID.

## Definition of done (DoD)

A PR is done only when:
1. `required-ci` is green.
2. docs/runtime/contracts parity is updated.
3. risk + rollback is documented in PR template.
4. ownership boundaries are not violated.
5. no new duplicated governance controls are introduced.
