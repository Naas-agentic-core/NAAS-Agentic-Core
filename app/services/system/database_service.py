import asyncio
import logging
import re

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import AppSettings

logger = logging.getLogger(__name__)

_READ_ONLY_PREFIXES = ("SELECT", "WITH")
_FORBIDDEN_SQL = re.compile(r";|\\b(INSERT|UPDATE|DELETE|DROP|ALTER|TRUNCATE|CREATE)\\b")


class DatabaseService:
    def __init__(
        self,
        session: AsyncSession | None = None,
        settings: AppSettings | None = None,
        logger: logging.Logger | None = None,
    ):
        self.session = session
        self.settings = settings
        self.logger = logger or logging.getLogger(__name__)

    async def check_health(self) -> dict[str, object]:
        """
        Checks database health.
        """
        try:
            if self.session is None:
                raise RuntimeError("Database session غير متوفر.")
            start = asyncio.get_event_loop().time()
            await self.session.execute(text("SELECT 1"))
            end = asyncio.get_event_loop().time()
            return {"status": "healthy", "latency_ms": (end - start) * 1000}
        except Exception as e:
            self.logger.error(f"Health check failed: {e}")
            return {"status": "unhealthy", "error": str(e)}

    async def get_database_health(self) -> dict[str, object]:
        return await self.check_health()

    async def get_all_tables(self) -> list[dict[str, object]]:
        raise NotImplementedError("خدمة الجداول غير مفعلة حتى يتم تنفيذها بالكامل.")

    async def get_table_schema(self, table_name: str) -> dict[str, object]:
        raise NotImplementedError("خدمة مخطط الجداول غير مفعلة حتى يتم تنفيذها بالكامل.")

    async def get_table_data(
        self,
        table_name: str,
        page: int = 1,
        per_page: int = 50,
        search: str | None = None,
        order_by: str | None = None,
        order_dir: str = "asc",
    ) -> dict[str, object]:
        raise NotImplementedError("خدمة بيانات الجداول غير مفعلة حتى يتم تنفيذها بالكامل.")

    async def get_record(self, table_name: str, record_id: int) -> dict[str, object]:
        raise NotImplementedError("خدمة استرجاع السجل غير مفعلة حتى يتم تنفيذها بالكامل.")

    async def create_record(self, table_name: str, data: dict[str, object]) -> dict[str, object]:
        raise NotImplementedError("خدمة إنشاء السجل غير مفعلة حتى يتم تنفيذها بالكامل.")

    async def update_record(
        self, table_name: str, record_id: int, data: dict[str, object]
    ) -> dict[str, object]:
        raise NotImplementedError("خدمة تحديث السجل غير مفعلة حتى يتم تنفيذها بالكامل.")

    async def delete_record(self, table_name: str, record_id: int) -> dict[str, object]:
        raise NotImplementedError("خدمة حذف السجل غير مفعلة حتى يتم تنفيذها بالكامل.")

    async def execute_query(self, sql: str) -> dict[str, object]:
        try:
            if self.session is None:
                raise RuntimeError("Database session غير متوفر.")
            normalized = " ".join(sql.strip().split())
            if not normalized:
                raise ValueError("الاستعلام فارغ.")
            upper_sql = normalized.upper()
            if not upper_sql.startswith(_READ_ONLY_PREFIXES) or _FORBIDDEN_SQL.search(upper_sql):
                raise ValueError("يسمح فقط باستعلامات القراءة بدون أوامر متعددة.")
            result = await self.session.execute(text(sql))
            rows = [dict(row._mapping) for row in result]
            return {"status": "success", "rows": rows, "row_count": len(rows)}
        except Exception as e:
            return {"status": "error", "message": str(e)}


database_service = DatabaseService()
