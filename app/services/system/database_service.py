import asyncio
import hashlib
import logging
import re
from typing import Any

import sqlglot
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlglot import exp

from app.core.config import AppSettings, get_settings

logger = logging.getLogger(__name__)

_READ_ONLY_PREFIXES = ("SELECT", "WITH")
_FORBIDDEN_SQL = re.compile(r";|\\b(INSERT|UPDATE|DELETE|DROP|ALTER|TRUNCATE|CREATE)\\b")


def _is_safe_sqlglot_query(sql: str) -> bool:  # noqa: PLR0911
    try:
        if "--" in sql or "/*" in sql:
            return False

        parsed = sqlglot.parse(sql, read="postgres", error_level=sqlglot.ErrorLevel.IMMEDIATE)
        if len(parsed) != 1:
            return False

        ast = parsed[0]
        if not isinstance(ast, (exp.Select, exp.Union)):
            return False

        if ast.args.get("with"):
            with_ = ast.args.get("with")
            for cte in with_.expressions:
                if not isinstance(cte.this, (exp.Select, exp.Union)):
                    return False

        forbidden_funcs = {
            "pg_sleep",
            "pg_read_file",
            "pg_read_binary_file",
            "lo_import",
            "lo_export",
            "dblink",
            "set_config",
            "current_setting",
            "pg_terminate_backend",
            "load_extension",
            "copy",
        }

        for node in ast.find_all(exp.Expression):
            if isinstance(
                node, (exp.Delete, exp.Update, exp.Insert, exp.Drop, exp.Alter, exp.Command)
            ):
                return False
            if isinstance(node, exp.Into):
                return False
            if isinstance(node, exp.Lock):
                return False
            if isinstance(node, (exp.Func, exp.Anonymous)) and node.name.lower() in forbidden_funcs:
                return False
        return True
    except Exception:
        return False


class DatabaseService:
    def __init__(
        self,
        session: AsyncSession | None = None,
        settings: AppSettings | None = None,
        logger: logging.Logger | None = None,
    ):
        self.session = session

        if settings is None:
            try:
                self.settings = get_settings()
            except Exception:
                self.settings = None
        else:
            self.settings = settings

        self.logger = logger or logging.getLogger(__name__)

    async def check_health(self) -> dict[str, object]:
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

    async def execute_query(  # noqa: PLR0912, PLR0915
        self,
        sql: str,
        params: dict[str, Any] | None = None,
        require_admin: bool = True,
        caller_identity: str = "unknown",
    ) -> dict[str, object]:
        if require_admin and (not caller_identity or caller_identity == "unknown"):
            raise ValueError("غير مصرح لك بتنفيذ الاستعلام.")

        params_dict = params or {}
        sql_hash = hashlib.sha256(sql.encode("utf-8")).hexdigest()[:8]
        truncated_sql = sql[:100] + ("..." if len(sql) > 100 else "")
        param_keys = list(params_dict.keys())

        if self.settings:
            db_readonly_url = getattr(self.settings, "DATABASE_READONLY_URL", None)
            main_url = getattr(self.settings, "DATABASE_URL", None)
            if not db_readonly_url or db_readonly_url == main_url:
                self.logger.warning(
                    "AUDIT_LOG: execute_query warning | "
                    "DATABASE_READONLY_URL is missing or same as primary DB. Falling back to primary DB connection."
                )

        self.logger.info(
            f"AUDIT_LOG: execute_query start | caller='{caller_identity}' "
            f"sql_hash={sql_hash} sql='{truncated_sql}' keys={param_keys}"
        )

        try:
            if self.session is None:
                raise RuntimeError("Database session غير متوفر.")

            normalized = " ".join(sql.strip().split())
            if not normalized:
                raise ValueError("الاستعلام فارغ.")
            upper_sql = normalized.upper()
            if not upper_sql.startswith(_READ_ONLY_PREFIXES) or _FORBIDDEN_SQL.search(upper_sql):
                self.logger.warning(
                    f"AUDIT_LOG: execute_query rejected | sql_hash={sql_hash} reason='regex_blocked'"
                )
                raise ValueError("يسمح فقط باستعلامات القراءة بدون أوامر متعددة.")

            if not _is_safe_sqlglot_query(sql):
                self.logger.warning(
                    f"AUDIT_LOG: execute_query rejected | sql_hash={sql_hash} reason='parser_blocked'"
                )
                raise ValueError("الاستعلام مرفوض من قبل المحلل الأمني (يسمح فقط بالقراءة).")

            start_time = asyncio.get_event_loop().time()
            engine_name = self.session.bind.dialect.name if self.session.bind else "unknown"

            if engine_name == "sqlite":
                try:
                    await self.session.execute(text("PRAGMA query_only = 1"))
                    result = await self.session.execute(text(sql), params_dict)
                    max_rows = 1000
                    rows_proxy = result.fetchmany(max_rows)
                    rows = [dict(row._mapping) for row in rows_proxy]
                finally:
                    await self.session.execute(text("PRAGMA query_only = 0"))
            else:
                async with self.session.begin_nested():
                    if engine_name in ("postgresql", "asyncpg", "psycopg2"):
                        await self.session.execute(text("SET LOCAL statement_timeout = '5s'"))
                        await self.session.execute(text("SET LOCAL TRANSACTION READ ONLY"))

                    result = await self.session.execute(text(sql), params_dict)
                    max_rows = 1000
                    rows_proxy = result.fetchmany(max_rows)
                    rows = [dict(row._mapping) for row in rows_proxy]

            end_time = asyncio.get_event_loop().time()
            duration_ms = (end_time - start_time) * 1000

            self.logger.info(
                f"AUDIT_LOG: execute_query success | caller='{caller_identity}' "
                f"sql_hash={sql_hash} rows={len(rows)} duration_ms={duration_ms:.2f}"
            )
            return {"status": "success", "rows": rows, "row_count": len(rows)}

        except ValueError as ve:
            return {"status": "error", "message": str(ve)}
        except Exception as e:
            self.logger.error(f"AUDIT_LOG: execute_query error | sql_hash={sql_hash} error={e!s}")
            return {"status": "error", "message": "حدث خطأ أثناء تنفيذ الاستعلام الأمني."}


database_service = DatabaseService()
