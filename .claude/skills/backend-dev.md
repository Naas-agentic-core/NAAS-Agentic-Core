# Backend Development — FastAPI + SQLAlchemy + LangGraph

> CogniForge backend skill. Python 3.12, FastAPI 0.109.2, SQLAlchemy 2.0 async, Pydantic v2.

---

## Async SQLAlchemy 2.0 — Query Patterns

```python
from sqlalchemy import select, update, delete
from sqlalchemy.ext.asyncio import AsyncSession

# GET one record
async def get_user_by_email(db: AsyncSession, email: str):
    result = await db.execute(
        select(User).where(User.email == email.lower())
    )
    return result.scalar_one_or_none()

# GET many records
async def get_all_users(db: AsyncSession) -> list[User]:
    result = await db.execute(select(User).order_by(User.created_at.desc()))
    return list(result.scalars().all())

# CREATE with RETURNING (required for PostgreSQL + asyncpg)
from sqlalchemy import text

async def create_user(db: AsyncSession, email: str, hashed_password: str):
    result = await db.execute(
        text("""
            INSERT INTO users (email, hashed_password, created_at)
            VALUES (:email, :pw, NOW())
            RETURNING id
        """),
        {"email": email, "pw": hashed_password}
    )
    await db.commit()
    return result.scalar()

# UPDATE
async def update_user_name(db: AsyncSession, user_id: int, name: str):
    await db.execute(
        update(User).where(User.id == user_id).values(full_name=name)
    )
    await db.commit()

# DELETE
async def delete_user(db: AsyncSession, user_id: int):
    await db.execute(delete(User).where(User.id == user_id))
    await db.commit()
```

### Getting the DB session in a route

```python
from app.core.database import get_async_session
from fastapi import Depends

@router.post("/users")
async def create_user_endpoint(
    data: UserCreateSchema,
    db: AsyncSession = Depends(get_async_session),
):
    user_id = await create_user(db, data.email, hash_password(data.password))
    return {"id": user_id}
```

---

## Pydantic v2 Schemas

```python
from pydantic import BaseModel, EmailStr, Field, model_validator
from typing import Optional
from datetime import datetime

class UserCreateSchema(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8)
    full_name: Optional[str] = None

    @model_validator(mode="after")
    def normalize_email(self) -> "UserCreateSchema":
        self.email = self.email.lower().strip()
        return self

class UserResponseSchema(BaseModel):
    id: int
    email: str
    full_name: Optional[str]
    created_at: datetime

    model_config = {"from_attributes": True}  # replaces orm_mode=True
```

---

## Settings — Always Use get_settings()

```python
# ✅ Correct — anywhere in app code
from app.core.config import get_settings

settings = get_settings()
db_url = settings.DATABASE_URL
secret = settings.SECRET_KEY
llm_key = settings.OPENROUTER_API_KEY

# ❌ NEVER do this
import os
db_url = os.environ["DATABASE_URL"]  # bypasses validation, breaks tests
```

---

## Logger Convention

```python
import logging

# Module-level logger — use dotted path matching file location
logger = logging.getLogger("cogniforge.services.chat.my_service")

# Usage
logger.info("User logged in: user_id=%s", user_id)
logger.warning("Orchestrator unreachable, falling back to LangGraph")
logger.error("Database error", exc_info=True)
logger.debug("State: %s", state)
```

---

## FastAPI Router Pattern

```python
from fastapi import APIRouter, Depends, HTTPException, status
from app.core.config import get_settings

router = APIRouter(prefix="/api/v1/my-feature", tags=["my-feature"])

@router.get("/")
async def list_items():
    return {"items": []}

@router.post("/", status_code=status.HTTP_201_CREATED)
async def create_item(data: ItemCreateSchema):
    # always async, always typed
    return {"id": 1}

@router.get("/{item_id}")
async def get_item(item_id: int):
    raise HTTPException(status_code=404, detail="Not found")
```

**Registering a new router** — edit `app/api/routers/registry.py`:
```python
from app.api.routers import my_feature  # add import

def base_router_registry() -> list[RouterSpec]:
    return [
        ...existing routers...,
        (my_feature.router, ""),  # add here
    ]
```

---

## Adding a New Table

1. Edit `app/core/db_schema_config.py`:
```python
_ALLOWED_TABLES: Final[frozenset[str]] = frozenset({
    ...existing tables...,
    "my_new_table",  # add here
})

REQUIRED_SCHEMA: Final[dict[str, TableSchemaConfig]] = {
    ...existing tables...,
    "my_new_table": {
        "columns": ["id", "name", "created_at"],
        "auto_fix": {},
        "indexes": {
            "name": 'CREATE INDEX IF NOT EXISTS "ix_my_new_table_name" ON "my_new_table"("name")'
        },
        "create_table": """
            CREATE TABLE IF NOT EXISTS "my_new_table" (
                "id" SERIAL PRIMARY KEY,
                "name" TEXT NOT NULL,
                "created_at" TIMESTAMPTZ DEFAULT NOW()
            )
        """,
    },
}
```
2. Restart the backend — table is created automatically on startup.

---

## LangGraph Node Creation

```python
from typing import TypedDict
from langgraph.graph import StateGraph, END

class MyState(TypedDict):
    input: str
    result: str

async def my_node(state: MyState) -> dict:
    # Access OpenRouter LLM
    from app.core.ai_gateway import get_ai_client
    client = get_ai_client()
    response = await client.chat.completions.create(
        model="anthropic/claude-3-haiku",
        messages=[{"role": "user", "content": state["input"]}]
    )
    return {"result": response.choices[0].message.content}

# Build graph
graph = StateGraph(MyState)
graph.add_node("my_node", my_node)
graph.set_entry_point("my_node")
graph.add_edge("my_node", END)
app = graph.compile()
```

---

## Common Errors & Fixes

| Error | Cause | Fix |
|---|---|---|
| `greenlet_spawn has not been called` | sync SQLAlchemy in async context | Use `await db.execute(...)` |
| `MissingGreenlet` | same as above | Never use `db.query()` |
| `ConnectError: http://orchestrator-service:8006` | Docker DNS in Replit | Expected — LangGraph handles fallback |
| `Table 'X' not in _ALLOWED_TABLES` | Schema whitelist violation | Add table to `_ALLOWED_TABLES` frozenset |
| `pydantic_core.ValidationError` | Settings env var missing | Set env var or use default value |
| `JWT decode error` after restart | SECRET_KEY changed | Set SECRET_KEY as permanent Replit secret |
