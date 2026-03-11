"""
نظام معرفة المشروع لـ Overmind (Project Knowledge System).

هذا النظام يوفر لـ Overmind معرفة كاملة وشاملة عن المشروع بأكمله:
- قاعدة البيانات: الجداول، الأعمدة، العلاقات، الفهارس
- البنية: الملفات، المجلدات، التبعيات
- الإعدادات: المتغيرات البيئية، الأسرار (من GitHub Secrets)
- التوثيق: جميع الوثائق والتعليقات

المبادئ المطبقة:
- Single Source of Truth: مصدر واحد للحقيقة عن المشروع
- Self-Awareness: النظام يعرف نفسه ويفهم بنيته
- Security: الوصول الآمن للأسرار والبيانات الحساسة
- Intelligence: معلومات ذكية قابلة للاستعلام

الميزات الرئيسية:
1. Database Inspector: فحص قاعدة البيانات بالكامل
2. Schema Analyzer: تحليل البنية والعلاقات
3. Configuration Reader: قراءة جميع الإعدادات
4. Documentation Indexer: فهرسة جميع الوثائق
"""

import asyncio
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession

from microservices.orchestrator_service.src.core.config import get_settings
from microservices.orchestrator_service.src.core.database import async_session_factory
from microservices.orchestrator_service.src.core.logging import get_logger
from microservices.orchestrator_service.src.services.overmind.knowledge_environment import (
    build_environment_info,
)
from microservices.orchestrator_service.src.services.overmind.knowledge_mapping import (
    build_database_map,
)
from microservices.orchestrator_service.src.services.overmind.knowledge_queries import (
    fetch_all_tables,
    fetch_foreign_keys,
    fetch_primary_keys,
    fetch_table_columns,
    fetch_table_count,
)
from microservices.orchestrator_service.src.services.overmind.knowledge_schema import (
    build_schema_object,
    log_schema_info,
)
from microservices.orchestrator_service.src.services.overmind.knowledge_structure import (
    build_microservices_summary,
    build_project_structure,
)
from microservices.orchestrator_service.src.services.overmind.knowledge_timestamp import (
    build_project_timestamp,
)

logger = get_logger(__name__)


class DatabaseKnowledge:
    """
    معرفة قاعدة البيانات (Database Knowledge).

    يوفر معلومات شاملة عن:
    - جميع الجداول الموجودة
    - أعمدة كل جدول مع أنواعها
    - العلاقات بين الجداول (Foreign Keys)
    - الفهارس (Indexes)
    - القيود (Constraints)

    الاستخدام:
        >>> async with DatabaseKnowledge() as db_knowledge:
        >>>     tables = await db_knowledge.get_all_tables()
        >>>     schema = await db_knowledge.get_table_schema("users")
    """

    def __init__(self) -> None:
        """تهيئة نظام معرفة قاعدة البيانات."""
        self.settings = get_settings()
        self._session: AsyncSession | None = None

    async def __aenter__(self) -> "DatabaseKnowledge":
        """فتح جلسة قاعدة بيانات مستقلة عند الدخول للسياق."""
        self._session = async_session_factory()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """إغلاق الجلسة عند الخروج من السياق مع معالجة الأخطاء."""
        if not self._session:
            return
        if exc_type is not None:
            await self._session.rollback()
        await self._session.close()
        self._session = None

    async def get_all_tables(self) -> list[str]:
        """
        الحصول على قائمة جميع الجداول في قاعدة البيانات.

        Returns:
            list[str]: أسماء جميع الجداول

        مثال:
            >>> tables = await db_knowledge.get_all_tables()
            >>> logger.info(tables)
            ['users', 'missions', 'tasks', 'chat_messages', ...]

        ملاحظة:
            - text() تُنشئ SQL query نصي
            - await تنتظر نتيجة العملية غير المتزامنة
            - .scalars() تُرجع قيم عمود واحد
            - .all() تُرجع جميع النتائج كقائمة
        """
        if not self._session:
            logger.error("Database session not initialized")
            return []

        try:
            tables = await fetch_all_tables(self._session)

            logger.info(f"Found {len(tables)} tables in database")
            return list(tables)

        except Exception as e:
            logger.error(f"Error getting tables: {e}")
            return []

    async def get_table_schema(self, table_name: str) -> dict[str, object]:
        """
        الحصول على البنية الكاملة لجدول معين.

        Args:
            table_name: اسم الجدول

        Returns:
            dict: معلومات شاملة عن الجدول تشمل:
                - columns: الأعمدة مع أنواعها
                - primary_keys: المفاتيح الأساسية
                - foreign_keys: المفاتيح الأجنبية
                - indexes: الفهارس

        مثال:
            >>> schema = await db_knowledge.get_table_schema("users")
            >>> logger.info(schema['columns'])
            [
                {'name': 'id', 'type': 'INTEGER', 'nullable': False},
                {'name': 'email', 'type': 'VARCHAR', 'nullable': False},
                ...
            ]

        ملاحظة:
            - {} تُنشئ dictionary فارغ
            - [] تُنشئ list فارغة
            - List comprehension: [expr for item in list]
            - .get() method آمنة للوصول للقيم
        """
        if not self._session:
            logger.error("Database session not initialized")
            return {}

        try:
            # جمع كل مكونات البنية
            columns = await fetch_table_columns(self._session, table_name)
            primary_keys = await fetch_primary_keys(self._session, table_name)
            foreign_keys = await fetch_foreign_keys(self._session, table_name)

            schema = build_schema_object(table_name, columns, primary_keys, foreign_keys)

            log_schema_info(table_name, columns, primary_keys, foreign_keys)

            return schema

        except Exception as e:
            logger.error(f"Error getting schema for '{table_name}': {e}")
            return {}

    async def get_table_count(self, table_name: str) -> int:
        """
        عد السجلات في جدول معين.

        Args:
            table_name: اسم الجدول

        Returns:
            int: عدد السجلات

        مثال:
            >>> count = await db_knowledge.get_table_count("users")
            >>> logger.info("Total users: %s", count)
        """
        if not self._session:
            return 0

        try:
            return await fetch_table_count(self._session, table_name)

        except Exception as e:
            logger.error(f"Error counting rows in '{table_name}': {e}")
            return 0

    async def get_full_database_map(self) -> dict[str, object]:
        """
        الحصول على خريطة كاملة لقاعدة البيانات.

        Returns:
            dict: معلومات شاملة عن جميع الجداول والعلاقات

        مثال:
            >>> db_map = await db_knowledge.get_full_database_map()
            >>> logger.info(json.dumps(db_map, indent=2))

        ملاحظة:
            - هذه دالة مكلفة (expensive) لأنها تستعلم عن كل جدول
            - استخدمها فقط عند الحاجة الحقيقية
        """
        tables = await self.get_all_tables()

        table_details = []
        for table_name in tables:
            schema = await self.get_table_schema(table_name)
            count = await self.get_table_count(table_name)
            table_details.append((table_name, schema, count))

        database_map = build_database_map(table_details)

        logger.info(
            f"Created full database map: {len(tables)} tables, "
            f"{len(database_map['relationships'])} relationships"
        )

        return database_map


class ProjectKnowledge:
    """
    معرفة المشروع الشاملة (Comprehensive Project Knowledge).

    يجمع معلومات من مصادر متعددة:
    - قاعدة البيانات (عبر DatabaseKnowledge)
    - نظام الملفات (الملفات والمجلدات)
    - المتغيرات البيئية (من .env أو GitHub Secrets)
    - التوثيق (ملفات MD)

    هذا هو "الدماغ" الذي يستخدمه Overmind لفهم المشروع.
    """

    def __init__(self) -> None:
        """تهيئة نظام معرفة المشروع."""
        self.settings = get_settings()
        self.project_root = Path.cwd()

    async def get_database_info(self) -> dict[str, object]:
        """
        الحصول على معلومات قاعدة البيانات.

        Returns:
            dict: معلومات شاملة عن قاعدة البيانات
        """
        async with DatabaseKnowledge() as db_knowledge:
            return await db_knowledge.get_full_database_map()

    def get_environment_info(self) -> dict[str, object]:
        """
        الحصول على معلومات البيئة والإعدادات.

        Returns:
            dict: معلومات البيئة (بدون الأسرار الحساسة في اللوج)

        ملاحظة:
            - لا نُرجع القيم الفعلية للأسرار
            - فقط نُشير إلى وجودها أو عدمها
        """
        return build_environment_info(self.settings)

    async def get_project_structure(self) -> dict[str, object]:
        """
        الحصول على بنية المشروع (الملفات والمجلدات).

        Returns:
            dict: معلومات عن بنية المشروع
        """
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, build_project_structure, self.project_root)

    async def get_microservices_info(self) -> dict[str, object]:
        """
        الحصول على ملخص الخدمات المصغرة (Microservices).

        Returns:
            dict: معلومات عن عدد الخدمات وأسمائها
        """
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, build_microservices_summary, self.project_root)

    async def get_complete_knowledge(self) -> dict[str, object]:
        """
        الحصول على المعرفة الكاملة والشاملة عن المشروع.

        Returns:
            dict: معلومات شاملة من جميع المصادر

        مثال:
            >>> knowledge = await project_knowledge.get_complete_knowledge()
            >>> logger.info("Tables: %s", knowledge['database']['total_tables'])
            >>> logger.info("Files: %s", knowledge['structure']['python_files'])
        """
        structure = await self.get_project_structure()
        microservices = await self.get_microservices_info()
        database = await self.get_database_info()

        knowledge = {
            "project_name": "CogniForge",
            "version": "1.0.0",
            "database": database,
            "environment": self.get_environment_info(),
            "structure": structure,
            "microservices": microservices,
            "timestamp": build_project_timestamp(self.project_root),
        }

        logger.info(
            f"Generated complete project knowledge: "
            f"{knowledge['database'].get('total_tables', 0)} tables, "
            f"{knowledge['structure'].get('python_files', 0)} Python files"
        )

        return knowledge
