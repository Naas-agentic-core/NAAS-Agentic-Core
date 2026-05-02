# CogniForge — Replit Environment

## Overview

CogniForge is an AI-powered enterprise platform featuring a hybrid monolith/microservices architecture. It is built on FastAPI (Python 3.12) for the backend and Next.js 16 (React 18) for the frontend.

## Architecture

- **Backend** — FastAPI app at `app/` served via uvicorn on port 8000
- **Frontend** — Next.js app at `frontend/` served on port 5000 (visible in preview pane)
- **Database** — PostgreSQL (Replit-managed, connected via `DATABASE_URL` secret)
- **Authentication** — Custom JWT-based auth (no external auth provider)

## Workflows

- **Project** — runs both Frontend and Backend in parallel
- **Frontend** — `cd frontend && npm run dev` → port 5000 (webview)
- **Backend** — `uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload` → port 8000 (console)

## Key Files

- `app/main.py` — FastAPI entry point
- `app/kernel.py` — RealityKernel bootstrapper (middleware, routers, lifespan)
- `app/core/settings/base.py` — Pydantic settings (AppSettings)
- `app/core/database.py` — Async SQLAlchemy engine factory
- `app/core/db_schema.py` — Schema validation and auto-fix on startup
- `app/core/db_schema_config.py` — All 18 table definitions and indexes
- `frontend/app/` — Next.js app directory (pages, components, hooks)
- `frontend/next.config.js` — Rewrites `/api/*` and `/health` to backend at port 8000

## Environment Variables (set via Replit Secrets)

| Variable | Required | Purpose |
|---|---|---|
| `DATABASE_URL` | Yes (auto-set by Replit) | PostgreSQL connection string |
| `BACKEND_CORS_ORIGINS` | Yes | JSON array of allowed CORS origins |
| `ALLOWED_HOSTS` | Yes | JSON array of trusted hosts |
| `FRONTEND_URL` | Yes | Frontend base URL |
| `ENVIRONMENT` | Yes | `development` / `production` |
| `OPENAI_API_KEY` | Optional | Enables AI features (LLM calls) |
| `OPENROUTER_API_KEY` | Optional | Alternative LLM provider |

## Database Setup

All 18 tables are auto-created/validated by `app/core/db_schema.py` on startup. The following tables exist:
`users`, `roles`, `permissions`, `user_roles`, `role_permissions`, `refresh_tokens`, `audit_log`, `customer_conversations`, `customer_messages`, `missions`, `mission_plans`, `tasks`, `mission_events`, `admin_conversations`, `prompt_templates`, `generated_prompts`, `knowledge_nodes`, `knowledge_edges`

## Notes

- The `hnsw` vector index on `knowledge_nodes.embedding` requires the `pgvector` PostgreSQL extension. This index is skipped on startup but the rest of the schema is fully operational.
- The app uses pydantic-settings so list env vars (like `BACKEND_CORS_ORIGINS`) must be set as JSON arrays: `["value1","value2"]`
- Microservices in `microservices/` are not started by default — the monolith at `app/` handles all primary functionality.
