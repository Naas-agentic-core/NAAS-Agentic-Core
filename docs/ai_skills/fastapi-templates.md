---
name: fastapi-templates
description: Create production-ready FastAPI projects with async patterns, dependency injection, and comprehensive error handling. Use when building new FastAPI applications or setting up backend API projects.
---

# FastAPI Project Templates

> **Project note:** This project uses **PostgreSQL 15+** with `asyncpg` driver
> (`postgresql+asyncpg://`), **SQLAlchemy 2.x** (`DeclarativeBase`), and
> **Pydantic v2** (`model_dump()`, `model_config`). All patterns below reflect
> these versions. Do not use Pydantic v1 (`dict()`) or SQLAlchemy 1.x
> (`declarative_base()`) patterns.

## When to Use This Skill

- Starting new FastAPI projects from scratch
- Implementing async REST APIs with Python
- Building high-performance web services and microservices
- Creating async applications with PostgreSQL
- Setting up API projects with proper structure and testing

## Core Concepts

### 1. Project Structure

**Recommended Layout:**

```
app/
├── api/                    # API routes
│   ├── v1/
│   │   ├── endpoints/
│   │   │   ├── users.py
│   │   │   ├── auth.py
│   │   │   └── items.py
│   │   └── router.py
│   └── dependencies.py     # Shared dependencies
├── core/                   # Core configuration
│   ├── config.py
│   ├── security.py
│   └── database.py
├── models/                 # SQLAlchemy ORM models
│   ├── user.py
│   └── item.py
├── schemas/                # Pydantic schemas
│   ├── user.py
│   └── item.py
├── services/               # Business logic
│   ├── user_service.py
│   └── auth_service.py
├── repositories/           # Data access
│   ├── user_repository.py
│   └── item_repository.py
└── main.py                 # Application entry
```

### 2. Dependency Injection

FastAPI's built-in DI system using `Depends`:

- Database session management
- Authentication/authorization
- Shared business logic
- Configuration injection

### 3. Async Patterns

Proper async/await usage:

- Async route handlers
- Async database operations
- Async background tasks
- Async middleware

## Implementation Patterns

### Pattern 1: Complete FastAPI Application

```python
# main.py
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.database import engine, Base
from app.api.v1.router import api_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    """إدارة دورة حياة التطبيق — الإقلاع والإيقاف."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    await engine.dispose()


app = FastAPI(
    title="API Template",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router, prefix="/api/v1")


# core/config.py
from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """إعدادات التطبيق المحمّلة من متغيرات البيئة."""

    DATABASE_URL: str
    SECRET_KEY: str
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    API_V1_STR: str = "/api/v1"

    model_config = SettingsConfigDict(env_file=".env")


@lru_cache
def get_settings() -> Settings:
    """إرجاع نسخة مخزّنة مؤقتًا من الإعدادات."""
    return Settings()


# core/database.py
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.core.config import get_settings

settings = get_settings()

engine = create_async_engine(settings.DATABASE_URL, echo=False, future=True)

AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


class Base(DeclarativeBase):
    """القاعدة المشتركة لجميع نماذج SQLAlchemy."""
    pass


async def get_db() -> AsyncSession:
    """تبعية FastAPI لجلسة قاعدة البيانات."""
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
```

### Pattern 2: CRUD Repository Pattern

```python
# repositories/base_repository.py
from typing import Generic, TypeVar
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel

ModelType = TypeVar("ModelType")
CreateSchemaType = TypeVar("CreateSchemaType", bound=BaseModel)
UpdateSchemaType = TypeVar("UpdateSchemaType", bound=BaseModel)


class BaseRepository(Generic[ModelType, CreateSchemaType, UpdateSchemaType]):
    """مستودع CRUD الأساسي القابل لإعادة الاستخدام."""

    def __init__(self, model: type[ModelType]) -> None:
        self.model = model

    async def get(self, db: AsyncSession, id: int) -> ModelType | None:
        """جلب سجل بمعرّفه."""
        result = await db.execute(select(self.model).where(self.model.id == id))
        return result.scalars().first()

    async def get_multi(
        self,
        db: AsyncSession,
        skip: int = 0,
        limit: int = 100,
    ) -> list[ModelType]:
        """جلب قائمة من السجلات مع دعم الترقيم."""
        result = await db.execute(select(self.model).offset(skip).limit(limit))
        return list(result.scalars().all())

    async def create(self, db: AsyncSession, obj_in: CreateSchemaType) -> ModelType:
        """إنشاء سجل جديد."""
        db_obj = self.model(**obj_in.model_dump())
        db.add(db_obj)
        await db.flush()
        await db.refresh(db_obj)
        return db_obj

    async def update(
        self,
        db: AsyncSession,
        db_obj: ModelType,
        obj_in: UpdateSchemaType,
    ) -> ModelType:
        """تحديث سجل موجود."""
        update_data = obj_in.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            setattr(db_obj, field, value)
        await db.flush()
        await db.refresh(db_obj)
        return db_obj

    async def delete(self, db: AsyncSession, id: int) -> bool:
        """حذف سجل بمعرّفه."""
        obj = await self.get(db, id)
        if obj:
            await db.delete(obj)
            return True
        return False


# repositories/user_repository.py
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.models.user import User
from app.repositories.base_repository import BaseRepository
from app.schemas.user import UserCreate, UserUpdate


class UserRepository(BaseRepository[User, UserCreate, UserUpdate]):
    """مستودع المستخدمين مع استعلامات مخصصة."""

    async def get_by_email(self, db: AsyncSession, email: str) -> User | None:
        """جلب مستخدم بعنوان بريده الإلكتروني."""
        result = await db.execute(select(User).where(User.email == email))
        return result.scalars().first()

    async def is_active(self, db: AsyncSession, user_id: int) -> bool:
        """التحقق من أن المستخدم نشط."""
        user = await self.get(db, user_id)
        return user.is_active if user else False


user_repository = UserRepository(User)
```

### Pattern 3: Service Layer

```python
# services/user_service.py
from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.user_repository import user_repository
from app.schemas.user import UserCreate, UserUpdate, UserRead
from app.core.security import get_password_hash, verify_password


class UserService:
    """طبقة منطق الأعمال للمستخدمين."""

    def __init__(self) -> None:
        self.repository = user_repository

    async def create_user(self, db: AsyncSession, user_in: UserCreate) -> UserRead:
        """إنشاء مستخدم جديد مع تشفير كلمة المرور."""
        existing = await self.repository.get_by_email(db, user_in.email)
        if existing:
            raise ValueError("Email already registered")

        data = user_in.model_dump()
        data["hashed_password"] = get_password_hash(data.pop("password"))
        user = await self.repository.create(db, UserCreate(**data))
        return user

    async def authenticate(
        self,
        db: AsyncSession,
        email: str,
        password: str,
    ) -> UserRead | None:
        """مصادقة المستخدم بالبريد الإلكتروني وكلمة المرور."""
        user = await self.repository.get_by_email(db, email)
        if not user:
            return None
        if not verify_password(password, user.hashed_password):
            return None
        return user

    async def update_user(
        self,
        db: AsyncSession,
        user_id: int,
        user_in: UserUpdate,
    ) -> UserRead | None:
        """تحديث بيانات مستخدم موجود."""
        user = await self.repository.get(db, user_id)
        if not user:
            return None

        if user_in.password:
            data = user_in.model_dump(exclude_unset=True)
            data["hashed_password"] = get_password_hash(data.pop("password"))
            user_in = UserUpdate(**data)

        return await self.repository.update(db, user, user_in)


user_service = UserService()
```

### Pattern 4: Pydantic v2 Schemas

```python
# schemas/user.py
from pydantic import BaseModel, EmailStr, ConfigDict


class UserBase(BaseModel):
    """الحقول المشتركة بين جميع مخططات المستخدم."""
    email: EmailStr
    name: str


class UserCreate(UserBase):
    """مخطط إنشاء مستخدم جديد."""
    password: str


class UserUpdate(BaseModel):
    """مخطط تحديث مستخدم — جميع الحقول اختيارية."""
    email: EmailStr | None = None
    name: str | None = None
    password: str | None = None


class UserRead(UserBase):
    """مخطط القراءة — يُعاد في استجابات API."""
    id: int
    is_active: bool

    model_config = ConfigDict(from_attributes=True)
```

### Pattern 5: API Endpoints with Dependencies

```python
# api/v1/endpoints/users.py
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.schemas.user import UserRead, UserCreate, UserUpdate
from app.services.user_service import user_service
from app.api.dependencies import get_current_user

router = APIRouter()


@router.post("/", response_model=UserRead, status_code=status.HTTP_201_CREATED)
async def create_user(user_in: UserCreate, db: AsyncSession = Depends(get_db)):
    """إنشاء مستخدم جديد."""
    try:
        return await user_service.create_user(db, user_in)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/me", response_model=UserRead)
async def read_current_user(current_user: UserRead = Depends(get_current_user)):
    """جلب بيانات المستخدم الحالي."""
    return current_user


@router.get("/{user_id}", response_model=UserRead)
async def read_user(
    user_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: UserRead = Depends(get_current_user),
):
    """جلب مستخدم بمعرّفه."""
    user = await user_service.repository.get(db, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user


@router.patch("/{user_id}", response_model=UserRead)
async def update_user(
    user_id: int,
    user_in: UserUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: UserRead = Depends(get_current_user),
):
    """تحديث بيانات مستخدم."""
    if current_user.id != user_id:
        raise HTTPException(status_code=403, detail="Not authorized")
    user = await user_service.update_user(db, user_id, user_in)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user


@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_user(
    user_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: UserRead = Depends(get_current_user),
):
    """حذف مستخدم."""
    if current_user.id != user_id:
        raise HTTPException(status_code=403, detail="Not authorized")
    deleted = await user_service.repository.delete(db, user_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="User not found")
```

### Pattern 6: Authentication & Authorization

```python
# core/security.py
from datetime import datetime, timedelta, timezone
from jose import JWTError, jwt
from passlib.context import CryptContext
from app.core.config import get_settings

settings = get_settings()
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
ALGORITHM = "HS256"


def create_access_token(data: dict, expires_delta: timedelta | None = None) -> str:
    """إنشاء رمز JWT للوصول."""
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + (expires_delta or timedelta(minutes=15))
    to_encode["exp"] = expire
    return jwt.encode(to_encode, settings.SECRET_KEY, algorithm=ALGORITHM)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """التحقق من كلمة المرور مقابل تجزئتها."""
    return pwd_context.verify(plain_password, hashed_password)


def get_password_hash(password: str) -> str:
    """تجزئة كلمة المرور."""
    return pwd_context.hash(password)


# api/dependencies.py
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import ALGORITHM
from app.core.config import get_settings
from app.repositories.user_repository import user_repository

settings = get_settings()
oauth2_scheme = OAuth2PasswordBearer(tokenUrl=f"{settings.API_V1_STR}/auth/login")


async def get_current_user(
    db: AsyncSession = Depends(get_db),
    token: str = Depends(oauth2_scheme),
):
    """جلب المستخدم الحالي من رمز JWT."""
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[ALGORITHM])
        user_id: int | None = payload.get("sub")
        if user_id is None:
            raise credentials_exception
    except JWTError as exc:
        raise credentials_exception from exc

    user = await user_repository.get(db, user_id)
    if user is None:
        raise credentials_exception
    return user
```

## Testing

```python
# tests/conftest.py
import pytest
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.main import app
from app.core.database import get_db, Base

TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"


@pytest.fixture
async def db_session():
    """جلسة قاعدة بيانات معزولة لكل اختبار."""
    engine = create_async_engine(TEST_DATABASE_URL, echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with session_factory() as session:
        yield session

    await engine.dispose()


@pytest.fixture
async def client(db_session: AsyncSession):
    """عميل HTTP للاختبار مع تجاوز تبعية قاعدة البيانات."""
    async def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()


# tests/test_users.py
import pytest


@pytest.mark.asyncio
async def test_create_user(client: AsyncClient):
    response = await client.post(
        "/api/v1/users/",
        json={"email": "test@example.com", "password": "testpass123", "name": "Test User"},
    )
    assert response.status_code == 201
    data = response.json()
    assert data["email"] == "test@example.com"
    assert "id" in data


@pytest.mark.asyncio
async def test_create_user_duplicate_email(client: AsyncClient):
    payload = {"email": "dup@example.com", "password": "pass", "name": "User"}
    await client.post("/api/v1/users/", json=payload)
    response = await client.post("/api/v1/users/", json=payload)
    assert response.status_code == 400
```

## Best Practices

1. **Async all the way** — use async for database and external API calls
2. **Dependency injection** — leverage FastAPI's `Depends` system
3. **Repository pattern** — separate data access from business logic
4. **Service layer** — keep business logic out of route handlers
5. **Pydantic v2 schemas** — use `model_dump()`, `model_config = ConfigDict(...)`
6. **SQLAlchemy 2.x** — use `DeclarativeBase`, `async_sessionmaker`, `create_async_engine`
7. **Consistent error responses** — always raise `HTTPException` with structured `detail`
8. **Test all layers** — unit-test services, integration-test routes

## Common Pitfalls

- **`obj_in.dict()`** — Pydantic v1 API; use `obj_in.model_dump()` instead
- **`declarative_base()`** — SQLAlchemy 1.x; use `class Base(DeclarativeBase): pass`
- **`typing.List` / `typing.Optional`** — use `list[...]` and `... | None` (Python 3.10+)
- **Blocking code in async handlers** — use `asyncio.to_thread()` for CPU-bound work
- **Business logic in routes** — always delegate to the service layer
- **Missing `from_attributes=True`** — required in `model_config` for ORM to Pydantic conversion
- **`datetime.utcnow()`** — deprecated; use `datetime.now(timezone.utc)`
