import subprocess
from datetime import datetime

import docker
from sqlalchemy import text

from microservices.orchestrator_service.src.core.database import async_session_factory
from microservices.orchestrator_service.src.infrastructure.clients.user_client import user_client
from microservices.orchestrator_service.src.services.overmind.graph.mcp_mock import kagent_tool

class ContractViolationError(Exception):
    pass

class ToolExecutionError(Exception):
    pass

ADMIN_TOOL_CONTRACT = {
    "admin.count_python_files":    "Count all .py files in project",
    "admin.count_database_tables": "Count all DB tables via SQL",
    "admin.get_user_count":        "Get registered user count",
    "admin.list_microservices":    "List all running services",
    "admin.calculate_full_stats":  "Full system statistics",
}

def validate_tool_name(name: str) -> None:
    if name not in ADMIN_TOOL_CONTRACT:
        raise ContractViolationError(
            f"Tool '{name}' not in AdminToolContract. "
            f"Valid tools: {list(ADMIN_TOOL_CONTRACT.keys())}"
        )

@kagent_tool(
    name="admin.count_python_files",
    mcp_server="naas.admin.filesystem",
)
def count_python_files() -> str:
    """Count all .py files in project"""
    validate_tool_name("admin.count_python_files")
    result = subprocess.run(
        ["find", ".", "-type", "f", "-name", "*.py"],
        capture_output=True, text=True, check=False
    )
    files = [f for f in result.stdout.strip().split("\n") if f]
    count = len(files)
    return f"عدد ملفات بايثون في المشروع: {count} ملف"

@kagent_tool(
    name="admin.count_database_tables",
    mcp_server="naas.admin.database",
)
async def count_database_tables() -> str:
    """Count all DB tables via SQL"""
    validate_tool_name("admin.count_database_tables")
    async with async_session_factory() as session:
        result = await session.execute(
            text("SELECT COUNT(*) FROM information_schema.tables "
                 "WHERE table_schema = 'public'")
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
        raise ToolExecutionError(f"ADMIN_TOOL_UNAVAILABLE: {e}")

@kagent_tool(
    name="admin.list_microservices",
    mcp_server="naas.admin.infrastructure",
)
def list_microservices() -> str:
    """List all running services"""
    validate_tool_name("admin.list_microservices")
    try:
        client = docker.from_env()
        containers = client.containers.list()
        names = [c.name for c in containers]
        return (f"الخدمات المصغرة النشطة: {len(names)} خدمة\n"
                + "\n".join(f"• {n}" for n in names))
    except Exception as e:
        raise ToolExecutionError(f"ADMIN_TOOL_UNAVAILABLE: {e}")

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

    return f"""
📊 إحصائيات النظام الكاملة:
{files}
{tables}
{users}
{services}
🕐 وقت الحساب: {datetime.utcnow().isoformat()}
""".strip()


ADMIN_TOOLS = [
    count_python_files,
    count_database_tables,
    get_user_count,
    list_microservices,
    calculate_full_stats,
]
