import subprocess
from datetime import datetime

from sqlalchemy import text

from microservices.orchestrator_service.src.core.database import async_session_factory
from microservices.orchestrator_service.src.infrastructure.clients.user_client import user_client
from microservices.orchestrator_service.src.services.overmind.graph.mcp_mock import kagent_tool


class ContractViolationError(Exception):
    pass


class ToolExecutionError(Exception):
    pass


ADMIN_TOOL_CONTRACT: dict[str, str] = {
    "admin.count_python_files": "Count all .py files recursively",
    "admin.count_database_tables": "Count tables via SQL information_schema",
    "admin.get_user_count": "Get total registered users from user_client",
    "admin.list_microservices": "List all running Docker containers",
    "admin.calculate_full_stats": "Aggregate all system metrics in one call",
}

REQUIRED_AT_STARTUP = list(ADMIN_TOOL_CONTRACT.keys())


def validate_tool_name(name: str) -> None:
    if name not in ADMIN_TOOL_CONTRACT:
        raise ContractViolationError(
            f"[CONTRACT VIOLATION] Tool '{name}' is not in "
            f"AdminToolContract.\n"
            f"Valid canonical names:\n" + "\n".join(f"  • {k}" for k in ADMIN_TOOL_CONTRACT)
        )


@kagent_tool(
    name="admin.count_python_files",
    mcp_server="naas.admin.filesystem",
)
def count_python_files() -> str:
    """Count all .py files in project excluding virtual environments and caches"""
    validate_tool_name("admin.count_python_files")

    cmd = 'find . -type f -name "*.py" -not -path "*/.venv/*" -not -path "*/__pycache__/*" -not -path "*/node_modules/*" -not -path "*/site-packages/*" -not -path "*/.git/*" | wc -l'

    result = subprocess.run(
        cmd, shell=True, capture_output=True, text=True, check=False
    )
    count = int(result.stdout.strip() or 0)
    return f"عدد ملفات بايثون: {count} ملف"


@kagent_tool(
    name="admin.count_database_tables",
    mcp_server="naas.admin.database",
)
async def count_database_tables() -> str:
    """Count all DB tables via SQL"""
    validate_tool_name("admin.count_database_tables")
    async with async_session_factory() as session:
        result = await session.execute(
            text("SELECT COUNT(*) FROM information_schema.tables WHERE table_schema = 'public'")
        )
        count = result.scalar() or 0
    return f"عدد جداول قاعدة البيانات: {count} جدول"


@kagent_tool(
    name="admin.get_user_count",
    mcp_server="naas.admin.users",
)
async def get_user_count() -> str:
    """Get registered user count"""
    validate_tool_name("admin.get_user_count")
    try:
        count = await user_client.get_user_count()
        return f"عدد المستخدمين المسجلين: {count} مستخدم"
    except Exception as e:
        raise ToolExecutionError(f"ADMIN_TOOL_UNAVAILABLE: {e}") from e


@kagent_tool(
    name="admin.list_microservices",
    mcp_server="naas.admin.infrastructure",
)
def list_microservices() -> str:
    """List all running services"""
    validate_tool_name("admin.list_microservices")
    try:
        import docker

        client = docker.from_env()
        containers = client.containers.list()
        names = [c.name for c in containers]
        lines = "\n".join(f"  • {n}" for n in names)
        return f"الخدمات المصغرة النشطة: {len(names)} خدمة\n{lines}"
    except Exception as e:
        raise ToolExecutionError(f"ADMIN_TOOL_UNAVAILABLE: {e}") from e


@kagent_tool(
    name="admin.calculate_full_stats",
    mcp_server="naas.admin.analytics",
)
async def calculate_full_stats() -> str:
    """Full system statistics"""
    validate_tool_name("admin.calculate_full_stats")

    files = count_python_files.invoke({})
    tables = await count_database_tables.ainvoke({})

    try:
        users = await get_user_count.ainvoke({})
    except Exception:
        users = "عدد المستخدمين المسجلين: خطأ في الوصول"

    try:
        services = list_microservices.invoke({})
    except Exception:
        services = "الخدمات المصغرة النشطة: خطأ في الوصول"

    return (
        f"📊 إحصائيات النظام الكاملة\n"
        f"{'─' * 35}\n"
        f"{files}\n{tables}\n{users}\n{services}\n"
        f"{'─' * 35}\n"
        f"🕐 {datetime.utcnow().isoformat()} UTC"
    )


ADMIN_TOOLS = [
    count_python_files,
    count_database_tables,
    get_user_count,
    list_microservices,
    calculate_full_stats,
]
