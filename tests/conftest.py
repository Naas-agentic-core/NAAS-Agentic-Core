"""إعدادات اختبارات مشتركة لمعالجة التحذيرات وضبط مسار الاستيراد."""

from __future__ import annotations

import asyncio
import importlib.util
import os
import sys
import warnings
from collections.abc import Coroutine
from contextlib import asynccontextmanager
from pathlib import Path
from typing import TYPE_CHECKING

os.environ.setdefault("ENVIRONMENT", "testing")
os.environ.setdefault("LLM_MOCK_MODE", "1")
os.environ.setdefault("LOG_LEVEL", "DEBUG")
os.environ.setdefault("PROJECT_NAME", "CogniForgeTest")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")
os.environ.setdefault("PASSLIB_BUILTIN_BCRYPT", "enabled")
# Set a consistent SECRET_KEY for all tests and microservices
os.environ["SECRET_KEY"] = "test-secret-key-for-ci-pipeline-secure-length"
os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///:memory:"

project_root = Path(__file__).resolve().parents[1]
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

warnings.filterwarnings("ignore", category=PendingDeprecationWarning)

# Pre-load Monolith domain models to ensure they claim the Table definitions first.
# This prevents "Table already defined" errors when Microservice models (with extend_existing=True)
# are loaded later in the same process.
from contextlib import suppress

import pytest

with suppress(ImportError):
    from app.core.domain import audit, chat, mission, user  # noqa: F401

if TYPE_CHECKING:
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from httpx import AsyncClient
    from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

    from app.core.domain.user import User
    from tests.factories.base import MissionFactory, UserFactory

_engine: AsyncEngine | None = None
_session_factory: async_sessionmaker[AsyncSession] | None = None
_schema_initialized = False
engine: AsyncEngine | None
TestingSessionLocal: async_sessionmaker[AsyncSession] | None


def _db_dependencies_available() -> bool:
    """يتحقق من توفر اعتمادات قاعدة البيانات قبل تهيئة أي موارد اختبارية."""
    return (
        importlib.util.find_spec("sqlalchemy") is not None
        and importlib.util.find_spec("sqlmodel") is not None
    )


def _should_skip_db_fixtures(request: pytest.FixtureRequest) -> bool:
    """يتحقق من تعطيل تجهيز قاعدة البيانات فقط لنطاقات الاختبارات المعزولة."""
    if os.environ.get("SKIP_DB_FIXTURES") != "1":
        return False

    isolated_paths = (
        "tests/unit/overmind/knowledge_graph/",
        "tests/unit/overmind/langgraph/",
    )
    request_path = str(request.path).replace("\\", "/")
    return any(path in request_path for path in isolated_paths)


def _get_engine() -> AsyncEngine:
    """يبني محرك SQLite داخل الذاكرة عند الحاجة فقط للاختبارات."""
    global _engine
    if _engine is not None:
        return _engine
    from sqlalchemy.ext.asyncio import create_async_engine
    from sqlalchemy.pool import StaticPool

    _engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    return _engine


def _get_session_factory() -> async_sessionmaker[AsyncSession]:
    """يعيد مصنع الجلسات مع ضمان ربطه بنواة قواعد البيانات للاختبارات."""
    global _session_factory
    if _session_factory is not None:
        return _session_factory
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    from app.core import database as core_database

    engine = _get_engine()
    _session_factory = async_sessionmaker(
        engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autocommit=False,
        autoflush=False,
    )
    core_database.engine = engine
    core_database.async_session_factory = _session_factory
    return _session_factory


if _db_dependencies_available():
    engine = _get_engine()
    TestingSessionLocal = _get_session_factory()
else:
    engine = None
    TestingSessionLocal = None


async def _ensure_schema() -> None:
    """تهيئة مخطط قاعدة البيانات داخل الذاكرة لاختبارات SQLite."""
    global _schema_initialized
    if not _db_dependencies_available():
        return
    if _schema_initialized:
        return
    from sqlmodel import SQLModel

    from app.core.db_schema import validate_and_fix_schema

    engine = _get_engine()
    async with engine.begin() as connection:
        await connection.run_sync(SQLModel.metadata.create_all)
    await validate_and_fix_schema(auto_fix=True)
    _schema_initialized = True


def _run_async[TResult](
    loop: asyncio.AbstractEventLoop,
    coroutine: Coroutine[object, object, TResult],
) -> TResult:
    """تشغيل Coroutine داخل الحلقة المستخدمة في الاختبارات."""
    return loop.run_until_complete(coroutine)


@asynccontextmanager
async def managed_test_session() -> AsyncSession:
    """جلسة قاعدة بيانات للاختبارات تعتمد على SQLite داخل الذاكرة."""
    pytest.importorskip("sqlalchemy")
    pytest.importorskip("sqlmodel")
    await _ensure_schema()
    session_factory = _get_session_factory()
    async with session_factory() as session:
        yield session


def pytest_addoption(parser: pytest.Parser) -> None:
    """تسجيل إعدادات ini المطلوبة لمنع تحذيرات PytestConfigWarning."""
    parser.addini("asyncio_mode", "وضع تشغيل asyncio", default="auto")
    parser.addini("env", "بيئة الاختبارات", type="linelist")


def pytest_configure(config: pytest.Config) -> None:
    """تسجيل وسم asyncio لاختبارات غير متزامنة."""
    config.addinivalue_line("markers", "asyncio: تشغيل اختبارات غير متزامنة")


def pytest_collection_modifyitems(
    session: pytest.Session,
    config: pytest.Config,
    items: list[pytest.Item],
) -> None:
    """يعيد ترتيب الاختبارات لضمان تشغيل اختبارات الخدمات المصغرة في نهاية الجلسة."""

    def _priority(item: pytest.Item) -> tuple[int, str]:
        path_text = str(item.fspath)
        is_microservice_test = "/microservices/" in path_text
        return (1 if is_microservice_test else 0, path_text)

    items.sort(key=_priority)


def pytest_sessionfinish(session: pytest.Session, exitstatus: int) -> None:
    """يفرض نجاحًا كاملًا عبر فشل الجلسة عند وجود تخطٍ أو تحذيرات اختبارية."""
    terminal_reporter = session.config.pluginmanager.get_plugin("terminalreporter")
    if terminal_reporter is None:
        return

    forbidden_outcomes = {
        "skipped": "توجد اختبارات مُتخطاة",
        "xfailed": "توجد اختبارات xfailed",
        "xpassed": "توجد اختبارات xpassed",
        "warnings": "توجد تحذيرات أثناء التشغيل",
    }

    violations = [
        message for key, message in forbidden_outcomes.items() if terminal_reporter.stats.get(key)
    ]

    if violations:
        joined_violations = "، ".join(violations)
        terminal_reporter.write_line(f"[tests-policy] فشل سياسة الجودة: {joined_violations}.")
        session.exitstatus = pytest.ExitCode.TESTS_FAILED


def pytest_pyfunc_call(pyfuncitem: pytest.Function) -> bool | None:
    """تشغيل الاختبارات غير المتزامنة بدون الاعتماد على pytest-asyncio."""
    if asyncio.iscoroutinefunction(pyfuncitem.obj):
        loop = pyfuncitem.funcargs.get("event_loop")
        if not isinstance(loop, asyncio.AbstractEventLoop):
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            pyfuncitem.funcargs["event_loop"] = loop
        arg_names = pyfuncitem._fixtureinfo.argnames
        kwargs = {name: pyfuncitem.funcargs[name] for name in arg_names}
        loop.run_until_complete(pyfuncitem.obj(**kwargs))
        return True
    return None


@pytest.fixture
def event_loop() -> asyncio.AbstractEventLoop:
    """حلقة asyncio مخصصة للاختبارات."""
    loop = asyncio.new_event_loop()
    try:
        yield loop
    finally:
        loop.close()


@pytest.fixture(scope="session")
def static_dir(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """بناء بنية ملفات ثابتة افتراضية لاختبارات الواجهة."""
    base_dir = tmp_path_factory.mktemp("static")
    (base_dir / "index.html").write_text(
        '<!DOCTYPE html><html><body><div id="root"></div></body></html>',
        encoding="utf-8",
    )
    (base_dir / "css").mkdir()
    (base_dir / "js").mkdir()
    (base_dir / "css" / "superhuman-ui.css").write_text("body{}", encoding="utf-8")
    (base_dir / "js" / "script.js").write_text("console.log('ok');", encoding="utf-8")
    return base_dir


@pytest.fixture(autouse=True)
def db_lifecycle(event_loop: asyncio.AbstractEventLoop, request: pytest.FixtureRequest) -> None:
    """إدارة دورة حياة قاعدة البيانات (تنظيف + تهيئة) قبل كل اختبار."""
    if _should_skip_db_fixtures(request):
        yield
        return
    if not _db_dependencies_available():
        yield
        return

    async def _reset_db() -> None:
        from sqlmodel import SQLModel

        from app.core.db_schema import validate_and_fix_schema

        # Detect if we are running microservice tests
        # This helps in loading the correct models for the context
        is_microservice_test = "microservices" in str(request.path) or "microservices" in str(
            request.node.fspath
        )

        if is_microservice_test:
            from contextlib import suppress

            with suppress(ImportError):
                # Import microservice models explicitly to ensure schema is correct
                # This ensures that even if Monolith models aren't loaded, these are.
                import microservices.user_service.models  # noqa: F401

        # Deduplicate indexes to handle potential accumulation from multiple test runs
        # or conflicts between Monolith and Microservice models extending the same table
        for table in SQLModel.metadata.tables.values():
            if not hasattr(table, "indexes"):
                continue
            unique_indexes: dict[str | None, object] = {}
            duplicate_indexes = []
            for index in list(table.indexes):
                index_name = getattr(index, "name", None)
                if index_name in unique_indexes:
                    duplicate_indexes.append(index)
                else:
                    unique_indexes[index_name] = index
            for duplicate_index in duplicate_indexes:
                table.indexes.remove(duplicate_index)

        engine = _get_engine()

        # 1. Drop all tables to ensure clean slate (avoids FK issues)
        async with engine.begin() as connection:
            await connection.run_sync(SQLModel.metadata.drop_all)

        # 2. Recreate schema
        async with engine.begin() as connection:
            await connection.run_sync(SQLModel.metadata.create_all)

        # 3. Validate and fix (adds default data or structural adjustments if needed)
        await validate_and_fix_schema(auto_fix=True)

    _run_async(event_loop, _reset_db())

    yield


@pytest.fixture
def db_session(event_loop: asyncio.AbstractEventLoop) -> AsyncSession:
    """إرجاع جلسة قاعدة بيانات للاختبار الحالي."""
    pytest.importorskip("sqlalchemy")
    pytest.importorskip("sqlmodel")
    _run_async(event_loop, _ensure_schema())

    async def _open_session() -> AsyncSession:
        session_factory = _get_session_factory()
        return session_factory()

    session = _run_async(event_loop, _open_session())
    try:
        yield session
    finally:
        _run_async(event_loop, session.close())


@pytest.fixture
def test_app(static_dir: Path) -> FastAPI:
    """تهيئة تطبيق الاختبار مع تجاوز اتصال قاعدة البيانات."""
    pytest.importorskip("fastapi")
    pytest.importorskip("sqlalchemy")
    pytest.importorskip("sqlmodel")
    os.environ.setdefault(
        "SECRET_KEY",
        "test-secret-key-that-is-very-long-and-secure-enough-for-tests-v4",
    )
    session_factory = _get_session_factory()
    from app.api.routers.admin import get_session_factory as get_admin_session_factory
    from app.api.routers.customer_chat import get_session_factory
    from app.core.database import get_db
    from app.core.settings.base import get_settings
    from app.main import create_app

    get_settings.cache_clear()
    settings = get_settings()
    app = create_app(
        settings_override=settings,
        static_dir=str(static_dir),
        enable_static_files=True,
    )

    async def override_get_db():
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_session_factory] = lambda: session_factory
    app.dependency_overrides[get_admin_session_factory] = lambda: session_factory
    return app


from datetime import UTC, datetime, timedelta

import jwt


@pytest.fixture
def register_and_login_test_user():
    """ينشئ مستخدم اختبار مباشرةً ويعيد رمز JWT صالحًا دون الاعتماد على خدمات خارجية."""

    async def _register(db_session, email: str = "test-user@example.com") -> str:
        from sqlalchemy import text

        from app.core.config import get_settings

        insert_statement = text(
            """
            INSERT INTO users (
                external_id,
                full_name,
                email,
                password_hash,
                is_admin,
                is_active,
                status
            )
            VALUES (:external_id, :full_name, :email, :password_hash, :is_admin, :is_active, :status)
            """
        )
        result = await db_session.execute(
            insert_statement,
            {
                "external_id": email,
                "full_name": "Student User",
                "email": email,
                "password_hash": "dummy_hash",
                "is_admin": False,
                "is_active": True,
                "status": "active",
            },
        )
        await db_session.commit()
        user_id = result.lastrowid

        payload = {
            "sub": str(user_id),
            "type": "access",
            "exp": datetime.now(UTC) + timedelta(hours=1),
        }
        return jwt.encode(payload, get_settings().SECRET_KEY, algorithm="HS256")

    return _register


@pytest.fixture
def client(test_app) -> TestClient:
    """عميل HTTP متزامن للاختبارات السريعة."""
    from fastapi.testclient import TestClient

    with TestClient(test_app) as test_client:
        yield test_client


@pytest.fixture
def async_client(test_app, event_loop: asyncio.AbstractEventLoop) -> AsyncClient:
    """عميل HTTP غير متزامن للاختبارات التكاملية."""
    from httpx import ASGITransport, AsyncClient

    client_instance = AsyncClient(
        transport=ASGITransport(app=test_app),
        base_url="http://test",
    )
    try:
        yield client_instance
    finally:
        _run_async(event_loop, client_instance.aclose())


@pytest.fixture
def admin_user(db_session: AsyncSession, event_loop: asyncio.AbstractEventLoop) -> User:
    """إنشاء مستخدم إداري للاختبارات."""
    pytest.importorskip("sqlalchemy")
    pytest.importorskip("sqlmodel")
    from app.core.domain.user import User

    async def _create_user() -> User:
        from sqlalchemy import select

        stmt = select(User).where(User.email == "admin@example.com")
        existing = (await db_session.execute(stmt)).scalar_one_or_none()
        if existing:
            return existing

        user = User(full_name="Admin", email="admin@example.com", is_admin=True)
        user.set_password("AdminPass123!")
        db_session.add(user)
        await db_session.commit()
        await db_session.refresh(user)
        return user

    return _run_async(event_loop, _create_user())


@pytest.fixture
def admin_auth_headers(
    db_session: AsyncSession,
    admin_user: User,
    event_loop: asyncio.AbstractEventLoop,
) -> dict[str, str]:
    """إنشاء ترويسات مصادقة لمستخدم إداري."""
    pytest.importorskip("sqlalchemy")
    pytest.importorskip("sqlmodel")
    from app.services.auth import AuthService

    async def _issue_tokens() -> dict[str, str]:
        auth = AuthService(db_session)
        await auth.rbac.ensure_seed()
        tokens = await auth.issue_tokens(admin_user)
        return {"Authorization": f"Bearer {tokens['access_token']}"}

    return _run_async(event_loop, _issue_tokens())


@pytest.fixture
def user_factory() -> UserFactory:
    """مصنع مستخدمين للاختبارات."""
    pytest.importorskip("sqlmodel")
    from tests.factories.base import UserFactory

    return UserFactory()


@pytest.fixture
def mission_factory() -> MissionFactory:
    """مصنع مهام للاختبارات."""
    pytest.importorskip("sqlmodel")
    from tests.factories.base import MissionFactory

    return MissionFactory()
