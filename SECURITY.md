# Security Policy

## Supported Versions

Only the latest release line on `main` is supported for security patches.

| Version line | Supported |
| --- | --- |
| latest on `main` | ✅ |
| older tags/branches | ❌ |

## Reporting a Vulnerability (Private Only)

**Do not open public GitHub issues for vulnerabilities.**

Report via:
- Email: `security@naas-lab.org`
- GitHub Security Advisory (if enabled)

Include:
1. Impacted component and commit/tag.
2. Reproduction steps (minimal PoC).
3. Security impact (confidentiality/integrity/availability).
4. Suggested mitigation (if known).

## Response SLA

- Acknowledgement: within **72 hours**.
- Initial triage: within **5 business days**.
- Critical vulnerability mitigation target: **14 days**.

## Disclosure Process

1. Validate and assign severity.
2. Prepare and test fix in private branch/fork.
3. Publish patched release + advisory.
4. Credit reporter (optional, with consent).

## Scope

In scope:
- `app/`
- `microservices/`
- `scripts/` used in CI/CD or release flow
- authentication/authorization paths
- data handling and safeguarding enforcement

Out of scope:
- vulnerabilities only in third-party dependencies without repository-specific exploitability.

## Safe Harbor

We support good-faith research that:
- avoids privacy violations and service disruption,
- does not exfiltrate real data,
- reports findings privately and responsibly.
