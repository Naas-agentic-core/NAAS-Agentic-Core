"""
اختبارات أدوات قاعدة البيانات الخارقة (Super Database Tools Tests).

اختبارات شاملة للوحدات المنفصلة الجديدة.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from microservices.orchestrator_service.src.services.overmind.database_tools.column_manager import ColumnManager
from microservices.orchestrator_service.src.services.overmind.database_tools.data_manager import DataManager
from microservices.orchestrator_service.src.services.overmind.database_tools.facade import SuperDatabaseTools
from microservices.orchestrator_service.src.services.overmind.database_tools.index_manager import IndexManager
from microservices.orchestrator_service.src.services.overmind.database_tools.operations_logger import OperationsLogger
from microservices.orchestrator_service.src.services.overmind.database_tools.query_executor import QueryExecutor
from microservices.orchestrator_service.src.services.overmind.database_tools.table_manager import TableManager


class TestOperationsLogger:
    """اختبارات مسجل العمليات."""

    def test_log_operation_success(self):
        """اختبار تسجيل عملية ناجحة."""
        logger = OperationsLogger()

        logger.log_operation("test_op", {"key": "value"}, success=True)

        assert len(logger.get_operations_log()) == 1
        assert logger.get_operations_log()[0]["operation"] == "test_op"
        assert logger.get_operations_log()[0]["success"] is True

    def test_log_operation_failure(self):
        """اختبار تسجيل عملية فاشلة."""
        logger = OperationsLogger()

        logger.log_operation("test_op", {"error": "test"}, success=False)

        assert len(logger.get_operations_log()) == 1
        assert logger.get_operations_log()[0]["success"] is False

    def test_clear_operations_log(self):
        """اختبار مسح سجل العمليات."""
        logger = OperationsLogger()

        logger.log_operation("test_op", {})
        assert len(logger.get_operations_log()) == 1

        logger.clear_operations_log()
        assert len(logger.get_operations_log()) == 0


class TestTableManager:
    """اختبارات مدير الجداول."""

    @pytest.mark.asyncio
    async def test_list_all_tables_success(self):
        """اختبار عرض جميع الجداول."""
        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.__iter__ = MagicMock(return_value=iter([["table1"], ["table2"]]))
        mock_session.execute.return_value = mock_result

        operations_logger = OperationsLogger()
        manager = TableManager(mock_session, MagicMock(), operations_logger)

        tables = await manager.list_all_tables()

        assert tables == ["table1", "table2"]
        assert len(operations_logger.get_operations_log()) == 1

    @pytest.mark.asyncio
    async def test_create_table_success(self):
        """اختبار إنشاء جدول."""
        mock_session = AsyncMock()
        operations_logger = OperationsLogger()
        manager = TableManager(mock_session, MagicMock(), operations_logger)

        result = await manager.create_table(
            "test_table", {"id": "INTEGER PRIMARY KEY", "name": "VARCHAR(255)"}
        )

        assert result["success"] is True
        assert result["table_name"] == "test_table"
        assert mock_session.execute.called
        assert mock_session.commit.called

    @pytest.mark.asyncio
    async def test_drop_table_success(self):
        """اختبار حذف جدول."""
        mock_session = AsyncMock()
        operations_logger = OperationsLogger()
        manager = TableManager(mock_session, MagicMock(), operations_logger)

        result = await manager.drop_table("test_table")

        assert result["success"] is True
        assert result["table_name"] == "test_table"
        assert mock_session.execute.called
        assert mock_session.commit.called


class TestColumnManager:
    """اختبارات مدير الأعمدة."""

    @pytest.mark.asyncio
    async def test_add_column_success(self):
        """اختبار إضافة عمود."""
        mock_session = AsyncMock()
        operations_logger = OperationsLogger()
        manager = ColumnManager(mock_session, operations_logger)

        result = await manager.add_column("test_table", "new_col", "VARCHAR(100)")

        assert result["success"] is True
        assert result["column_name"] == "new_col"
        assert mock_session.execute.called
        assert mock_session.commit.called

    @pytest.mark.asyncio
    async def test_drop_column_success(self):
        """اختبار حذف عمود."""
        mock_session = AsyncMock()
        operations_logger = OperationsLogger()
        manager = ColumnManager(mock_session, operations_logger)

        result = await manager.drop_column("test_table", "old_col")

        assert result["success"] is True
        assert result["column_name"] == "old_col"
        assert mock_session.execute.called
        assert mock_session.commit.called


class TestDataManager:
    """اختبارات مدير البيانات."""

    @pytest.mark.asyncio
    async def test_insert_data_success(self):
        """اختبار إدخال بيانات."""
        mock_session = AsyncMock()
        operations_logger = OperationsLogger()
        manager = DataManager(mock_session, operations_logger)

        result = await manager.insert_data("test_table", {"name": "test", "value": 123})

        assert result["success"] is True
        assert result["table_name"] == "test_table"
        assert mock_session.execute.called
        assert mock_session.commit.called

    @pytest.mark.asyncio
    async def test_query_table_success(self):
        """اختبار استعلام بيانات."""
        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_row = MagicMock()
        mock_row._mapping = {"id": 1, "name": "test"}
        mock_result.__iter__ = MagicMock(return_value=iter([mock_row]))
        mock_session.execute.return_value = mock_result

        operations_logger = OperationsLogger()
        manager = DataManager(mock_session, operations_logger)

        result = await manager.query_table("test_table")

        assert result["success"] is True
        assert result["count"] == 1
        assert len(result["rows"]) == 1


class TestIndexManager:
    """اختبارات مدير الفهارس."""

    @pytest.mark.asyncio
    async def test_create_index_success(self):
        """اختبار إنشاء فهرس."""
        mock_session = AsyncMock()
        operations_logger = OperationsLogger()
        manager = IndexManager(mock_session, operations_logger)

        result = await manager.create_index("test_idx", "test_table", ["col1", "col2"])

        assert result["success"] is True
        assert result["index_name"] == "test_idx"
        assert mock_session.execute.called
        assert mock_session.commit.called

    @pytest.mark.asyncio
    async def test_drop_index_success(self):
        """اختبار حذف فهرس."""
        mock_session = AsyncMock()
        operations_logger = OperationsLogger()
        manager = IndexManager(mock_session, operations_logger)

        result = await manager.drop_index("test_idx")

        assert result["success"] is True
        assert result["index_name"] == "test_idx"
        assert mock_session.execute.called
        assert mock_session.commit.called


class TestQueryExecutor:
    """اختبارات منفذ الاستعلامات."""

    @pytest.mark.asyncio
    async def test_execute_select_query(self):
        """اختبار تنفيذ استعلام SELECT."""
        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_row = MagicMock()
        mock_row._mapping = {"id": 1}
        mock_result.__iter__ = MagicMock(return_value=iter([mock_row]))
        mock_session.execute.return_value = mock_result

        operations_logger = OperationsLogger()
        executor = QueryExecutor(mock_session, operations_logger)

        result = await executor.execute_sql("SELECT * FROM test_table")

        assert result["success"] is True
        assert "rows" in result
        assert len(result["rows"]) == 1

    @pytest.mark.asyncio
    async def test_execute_update_query(self):
        """اختبار تنفيذ استعلام UPDATE."""
        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.rowcount = 5
        mock_session.execute.return_value = mock_result

        operations_logger = OperationsLogger()
        executor = QueryExecutor(mock_session, operations_logger)

        result = await executor.execute_sql("UPDATE test_table SET col = 'value'")

        assert result["success"] is True
        assert result["affected_rows"] == 5
        assert mock_session.commit.called


class TestSuperDatabaseToolsFacade:
    """اختبارات واجهة الأدوات الخارقة."""

    @pytest.mark.asyncio
    async def test_facade_initialization(self):
        """اختبار تهيئة الواجهة."""
        tools = SuperDatabaseTools()

        assert tools._operations_logger is None
        assert tools._table_manager is None
        assert tools._column_manager is None
        assert tools._data_manager is None
        assert tools._index_manager is None
        assert tools._query_executor is None

    @pytest.mark.asyncio
    async def test_facade_context_manager(self):
        """اختبار استخدام الواجهة كـ Context Manager."""
        with patch("microservices.orchestrator_service.src.services.overmind.database_tools.facade.get_db") as mock_get_db:
            mock_session = AsyncMock()

            async def mock_db_generator():
                yield mock_session

            mock_get_db.return_value = mock_db_generator()

            tools = SuperDatabaseTools()
            async with tools as db_tools:
                assert db_tools._session is not None
                assert db_tools._operations_logger is not None
                assert db_tools._table_manager is not None
                assert db_tools._column_manager is not None
                assert db_tools._data_manager is not None
                assert db_tools._index_manager is not None
                assert db_tools._query_executor is not None
