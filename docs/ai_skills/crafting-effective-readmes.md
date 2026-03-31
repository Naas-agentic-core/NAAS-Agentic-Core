---
name: crafting-effective-readmes
description: Use when writing or improving README files. Not all READMEs are the same — provides templates and guidance matched to your audience and project type.
---

# Crafting Effective READMEs

## Overview

READMEs answer questions your audience will have. Different audiences need different information — a contributor to an OSS project needs different context than a new hire reading an internal service README.

**Always ask:** Who will read this, and what do they need to know?

> **Project note:** README files in this repository must be written in **English**.
> Arabic is reserved for code docstrings and internal architecture documents.

---

## Process

### Step 1: Identify the Task

| Task | When |
|------|------|
| **Creating** | New project, no README yet |
| **Adding** | Need to document something new |
| **Updating** | Capabilities changed, content is stale |
| **Reviewing** | Checking if README is still accurate |

### Step 2: Task-Specific Questions

**Creating initial README:**
1. What type of project? (see Project Types below)
2. What problem does this solve in one sentence?
3. What's the quickest path to "it works"?
4. Anything notable to highlight?

**Adding a section:**
1. What needs documenting?
2. Where should it go in the existing structure?
3. Who needs this info most?

**Updating existing content:**
1. What changed?
2. Read current README, identify stale sections
3. Propose specific edits

**Reviewing/refreshing:**
1. Read current README
2. Check against actual project state (`package.json`, `requirements.txt`, main files)
3. Flag outdated sections

### Step 3: Always Ask

After drafting: **"Anything else to highlight or include that I might have missed?"**

---

## Project Types

| Type | Audience | Key Sections |
|------|----------|--------------|
| **Open Source** | Contributors, users worldwide | Install, Usage, Contributing, License |
| **Internal service** | Teammates, new hires | Setup, Architecture, API, Runbooks |
| **Personal / portfolio** | Future you, portfolio viewers | What it does, Tech stack, Learnings |
| **Config / tooling** | Future you (confused) | What's here, Why, How to extend, Gotchas |

---

## Templates

### Open Source / Internal Service (use for microservices in `microservices/`)

```markdown
# Service Name

One sentence: what this service does and why it exists.

## Requirements

- Python 3.12+
- PostgreSQL 15+
- Docker

## Setup

```bash
cp .env.example .env
docker compose up service_name
```

## API

Base URL: `http://localhost:<port>`

| Method | Path | Description |
|--------|------|-------------|
| GET | `/health` | Health check |
| POST | `/resource` | Create resource |

Full OpenAPI spec: `docs/contracts/<service_name>.yaml`

## Development

```bash
# Install dependencies
pip install -r requirements-dev.txt

# Run tests
pytest

# Lint
ruff check .
```

## Architecture

Brief description of the service's responsibility and its place in the system.
Link to relevant ADR: `docs/architecture/adr/`.
```

### Config / Tooling Folder

```markdown
# Folder Name

What lives here and why.

## Contents

| File | Purpose |
|------|---------|
| `file.py` | What it does |

## How to extend

Steps to add a new item.

## Gotchas

Known quirks or non-obvious behaviour.
```

---

## Essential Sections (All Types)

Every README needs at minimum:

1. **Name** — self-explanatory title
2. **Description** — what + why in 1–2 sentences
3. **Setup** — how to get it running (commands, not prose)
4. **Usage** — how to use it (examples help)

## What to Avoid

- Filler phrases: "This is a comprehensive...", "powerful", "robust"
- Repeating what the code already says
- Screenshots that go stale — prefer code examples
- Sections with no content ("Coming soon")
- Documenting the obvious (`cd into directory`)
