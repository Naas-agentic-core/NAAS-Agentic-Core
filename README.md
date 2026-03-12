# 🛡️ North African AI Safety Lab (NAAS Lab)
## Project: EL-NUKHBA (The Elite) | NAAS-Agentic-Core

![Status](https://img.shields.io/badge/Status-Active_Research-success?style=for-the-badge) ![License](https://img.shields.io/badge/License-MIT-blue.svg?style=for-the-badge) ![Python](https://img.shields.io/badge/Python-3.12-blue?style=for-the-badge) ![CI](https://img.shields.io/badge/Required_Check-required--ci-brightgreen?style=for-the-badge) ![Governance](https://img.shields.io/badge/Governance-Safeguarding_%2B_Data_Policy-red?style=for-the-badge) ![Cite](https://img.shields.io/badge/Cite-CITATION.cff-lightgrey?style=for-the-badge)

> **The "Elite" Verify-then-Reply Framework:** A safeguarding-first agentic tutoring framework for North African education that reduces AI-related harm in Arabic/French/Darija code-switching contexts through verification, risk screening, and measurable outcomes.

---

## 🚨 Governance & Safeguarding (Strict Protocol)

> **Why this matters:** North African youth frequently code-switch between Arabic, French, and Darija. Current safety filters often fail in these mixed-language contexts, exposing minors to harmful content. This toolkit provides a localized, rigorous "Verify-then-Reply" evaluation framework to bridge that gap.

This repository is governed by strict ethical protocols for youth safety. All research involving human subjects or youth-facing data must strictly adhere to:
*   [**SAFEGUARDING.md**](./SAFEGUARDING.md) (Youth safety, supervision, and escalation protocols)
*   [**DATA_POLICY.md**](./DATA_POLICY.md) (Privacy-by-design and data handling rules)

> **Note:** "Verify-then-Reply" reduces risk but does not eliminate it. Adult supervision is mandatory for youth-facing deployments.

---

## 🌟 Core Project Goals

Safety is the absolute core of our mission. We prioritize **measurement before protection** through a rigorous, transparent, and data-driven approach:

*   📊 **Robust Benchmarking:** Build a powerful benchmark to proactively discover and quantify risks across **Arabic, French, Darija, and Arabizi**.
*   🗄️ **Unique Dataset Creation:** Curate an exclusive dataset focused specifically on complex linguistic evasion and jailbreak attempts.
*   🧠 **Intent-Driven Reasoning:** Utilize advanced **Reasoning** to analyze true user intent, moving beyond simple keyword matching.
*   🛡️ **Verify-then-Reply Architecture:** Enforce a strict **Verify-then-Reply** layer backed by detailed **Audit Logs** and **Reasoning Traces** to justify and prove every decision.
*   🚫 **Evasion Resistance:** Fortify the system against evasion tactics through intelligent language unification and code-switching detection.
*   📡 **Telemetry & Compliance:** Provide deep **Telemetry** and absolute transparency to align with strict regulatory standards like the **EU AI Act**.
*   🌐 **Decentralized Resilience:** Architect the system to avoid any **Single Point of Failure** in centralized control mechanisms.
*   🚀 **Enterprise Safety API:** Evolve the project into a comprehensive **Benchmark + Safety API** designed to serve and protect enterprise institutions.

> **💎 The True Value:** Exceptional Data, Rigorous Measurement, and Fully Auditable Transparency.

---

## 🏛️ Executive Summary & Architecture

### The Mission
A safeguarding-first agentic tutoring toolkit and evaluation framework that helps youth-serving organisations and educators reduce AI-related educational harm and improve wellbeing and AI literacy outcomes in North Africa.

### Architecture: The Verify-then-Reply Engine
Our approach intercepts Model interactions to ensure safety before any content reaches the user.

```mermaid
graph LR
    Input[User Input] --> PreChecks[Pre-Checks (PII/Toxicity)]
    PreChecks -->|Pass| Verification[Verification Loop]
    PreChecks -->|Block| Refusal[Immediate Refusal]
    Verification -->|Analyze| SafetyPolicy{Policy Decision}
    SafetyPolicy -->|Safe| Output[Final Output]
    SafetyPolicy -->|Unsafe| Refusal
    Output --> Telemetry[Telemetry & Audit Logs]
    Refusal --> Telemetry
```

**How it works (Step-by-Step):**
1.  **Retrieve:** Relevant context from curated sources (no general web retrieval by default).
2.  **Draft:** A response using structured reasoning.
3.  **Critique:** With a safety/quality check (accuracy, tone, age-appropriateness, misuse risks).
4.  **Respond:** Only if the output meets defined thresholds; otherwise revise or abstain.

---

## 🎯 Impact & Metrics

### Key Safety Metrics (Empirical)
We empirically evaluate GenAI systems against four key safety metrics:

| Metric | Definition | Target |
| :--- | :--- | :--- |
| **Bypass Success Rate** | Percentage of adversarial prompts in mixed Arabic/French/Darija that successfully trigger unsafe generation. | 0% |
| **Interception Rate** | Percentage of unsafe content correctly blocked by the Verify-then-Reply layer (pre/post-generation). | >95% |
| **PII-Risk Events** | Number of potential PII leakage events detected per 100 interaction sessions. | 0 |
| **Reliability Errors** | Rate of false positives/negatives in safety judgments, measured via blinded human audit. | <5% |

### Broader Impact Indicators
We also track simple, auditable indicators (definitions in `docs/IMPACT_MEASUREMENT_PLAN.md`):
- **Curriculum alignment:** Agreement rate with curated curriculum sources.
- **Wellbeing (non-clinical):** Learner confidence and help-seeking pathways.
- **AI literacy:** Scenario-based judgement improvements.
- **Adoption:** Uptake of “safe mode” workflows by partner sites.

---

## 📦 Deliverables & Toolkit

### 1) Practical Toolkit (Usable by Partners)
- **Risk screening checklist:** For youth-facing AI use (privacy, misuse, harmful content).
- **Safeguarding playbook:** Consent/assent guidance, escalation, incident response.
- **AI literacy modules:** For youth, parents, and educators.
- **Implementation templates:** Policies, training agendas, briefing notes.

### 2) Independent Evidence
- **Evaluation protocol:** For real-world deployments (pre/post + incident logging).
- **Impact measurement plan:** Clear indicators and collection schedule.
- **Stakeholder outputs:** Templates for policymakers/regulators, NGOs, and product teams.

---

## 🗺️ Repository Map (Current)

```text
.
├── app/                        # Main FastAPI application + domain/core modules
├── microservices/              # Service-island implementations (gateway, user, planning, etc.)
├── tests/                      # Contract, architecture, guardrail, API, integration, security tests
├── scripts/                    # CI guardrails, fitness checks, operational tooling
├── docs/                       # Architecture constitution, ADRs, governance, contracts, guides
├── infra/                      # Kubernetes, Terraform, ArgoCD, monitoring assets
├── toolkit/                    # Partner-facing operational resources
├── knowledge_base/             # Ingestion source documents
├── frontend/                   # Frontend application modules
└── .github/                    # Workflows, templates, governance automation
```

---

## 🚀 Quick Start

### 👨‍💻 For Developers & Researchers

```bash
git clone https://github.com/HOUSSAM16ai/NAAS-Agentic-Core.git
cd NAAS-Agentic-Core
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements-dev.txt
pip install -r requirements-test.txt

# Required local gates (mirror required-ci jobs)
ruff check .
ruff format --check .
python scripts/ci_guardrails.py
pytest -v --cov=app --cov-report=term-missing --tb=short
```

### ✅ Mergeability Rule

For `main`, branch protection should require **only** `required-ci`.
This check aggregates lint, contracts, guardrails, and tests.

### 🤝 For Partners & Educators
1.  Read `toolkit/START_HERE.md`
2.  Run `toolkit/RISK_SCREENING_CHECKLIST.md`
3.  Adopt `SAFEGUARDING.md` and `DATA_PROTECTION.md` requirements
4.  Use `docs/EVALUATION_PROTOCOL.md` and `docs/IMPACT_MEASUREMENT_PLAN.md` for measurement and reporting

---

## ⚖️ Independence, Scope & Legal

### Independence & Transparency
The North African AI Safety Lab (NAAS Lab) operates with academic and operational independence. We reserve the right to publish our methods, findings, and critical safety evaluations independently of any model providers or partners. Open Science principles apply.

### Scope Boundaries
*   **Not Legal Advice:** This toolkit and its documentation do not constitute legal compliance advice (e.g., GDPR, local laws). Consult your organization's legal counsel.
*   **Not a Replacement for Human Oversight:** "Verify-then-Reply" reduces risk but does not eliminate it. Adult supervision is mandatory for youth-facing deployments as per [SAFEGUARDING.md](./SAFEGUARDING.md).

### Legal Host & Contact (EMEA)
**Registered Entity:** Interactive Training Courses Platform (trading as NAAS AI Safety Lab)
**Jurisdiction:** Algeria (EMEA)
**Project Lead:** Houssam Benmerah (h.benmerah@univ-eltarf.dz)
**Repository:** https://github.com/HOUSSAM16ai/NAAS-Agentic-Core

> This repository is maintained by the project team. References to third-party organisations, platforms, or products do not imply endorsement or affiliation.
