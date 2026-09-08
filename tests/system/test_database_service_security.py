from unittest.mock import AsyncMock, MagicMock

import pytest

from app.services.system.database_service import DatabaseService, _is_safe_sqlglot_query


class DummyContextManager:
    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        pass


def test_is_safe_sqlglot_query():
    # Allowed
    assert _is_safe_sqlglot_query("SELECT 1") is True
    assert _is_safe_sqlglot_query("WITH cte AS (SELECT 1) SELECT * FROM cte") is True
    assert _is_safe_sqlglot_query("SELECT * FROM users WHERE id = :id") is True
    assert _is_safe_sqlglot_query("SELECT 1 UNION SELECT 2") is True

    # Rejected
    assert _is_safe_sqlglot_query("SELECT 1; DROP TABLE users") is False
    assert (
        _is_safe_sqlglot_query("WITH d AS (DELETE FROM users RETURNING *) SELECT * FROM d") is False
    )
    assert _is_safe_sqlglot_query("SELECT * INTO t2 FROM t1") is False
    assert _is_safe_sqlglot_query("SELECT 1 FROM t FOR UPDATE") is False
    assert _is_safe_sqlglot_query("SELECT pg_sleep(10)") is False
    assert _is_safe_sqlglot_query("SELECT pg_read_file('/etc/passwd')") is False
    assert _is_safe_sqlglot_query("select/**/1;delete from x") is False
    assert _is_safe_sqlglot_query("SELECT 1 -- ;DROP") is False
    assert _is_safe_sqlglot_query("SELECT * FROM users FOR UPDATE") is False
    assert _is_safe_sqlglot_query("SELECT lo_export(1, '/tmp/file')") is False
    assert _is_safe_sqlglot_query("SELECT dblink('dbname=foo', 'SELECT 1')") is False
    assert _is_safe_sqlglot_query("SELECT set_config('role', 'admin', false)") is False


@pytest.mark.asyncio
async def test_execute_query_allow_list():
    mock_session = AsyncMock()
    mock_session.begin_nested = MagicMock(return_value=DummyContextManager())
    mock_session.bind = MagicMock()
    mock_session.bind.dialect.name = "postgresql"
    mock_result = MagicMock()
    mock_row = MagicMock()
    mock_row._mapping = {"col1": "val1"}
    mock_result.fetchmany.return_value = [mock_row]
    mock_session.execute = AsyncMock(return_value=mock_result)

    service = DatabaseService(session=mock_session)

    res = await service.execute_query("SELECT 1", caller_identity="admin")
    assert res["status"] == "success"
    assert res["rows"] == [{"col1": "val1"}]

    res2 = await service.execute_query(
        "SELECT * FROM users WHERE id = :id", params={"id": 1}, caller_identity="admin"
    )
    assert res2["status"] == "success"
    call_args = mock_session.execute.call_args
    assert call_args[0][1] == {"id": 1}
    assert "WHERE id = :id" in str(call_args[0][0])


@pytest.mark.asyncio
async def test_execute_query_deny_list():
    mock_session = AsyncMock()
    service = DatabaseService(session=mock_session)

    res = await service.execute_query("DROP TABLE users", caller_identity="admin")
    assert res["status"] == "error"
    assert "يسمح فقط باستعلامات القراءة" in res["message"]

    res2 = await service.execute_query("SELECT pg_sleep(10)", caller_identity="admin")
    assert res2["status"] == "error"
    assert "مرفوض من قبل المحلل الأمني" in res2["message"]

    res3 = await service.execute_query(
        "SELECT 1; UPDATE users SET role='admin'", caller_identity="admin"
    )
    assert res3["status"] == "error"
    assert "يسمح فقط باستعلامات القراءة" in res3["message"]

    res4 = await service.execute_query(
        "WITH d AS (DELETE FROM users RETURNING *) SELECT * FROM d", caller_identity="admin"
    )
    assert res4["status"] == "error"
    assert (
        "مرفوض من قبل المحلل الأمني" in res4["message"]
        or "يسمح فقط باستعلامات القراءة" in res4["message"]
    )

    res5 = await service.execute_query(
        "SELECT pg_read_file('/etc/passwd')", caller_identity="admin"
    )
    assert res5["status"] == "error"
    assert "مرفوض من قبل المحلل الأمني" in res5["message"]


@pytest.mark.asyncio
async def test_execute_query_row_cap():
    mock_session = AsyncMock()
    mock_session.begin_nested = MagicMock(return_value=DummyContextManager())
    mock_session.bind = MagicMock()
    mock_session.bind.dialect.name = "postgresql"
    mock_result = MagicMock()
    mock_row = MagicMock()
    mock_row._mapping = {"col1": "val1"}
    mock_result.fetchmany.return_value = [mock_row] * 1000
    mock_session.execute = AsyncMock(return_value=mock_result)

    service = DatabaseService(session=mock_session)
    res = await service.execute_query("SELECT * FROM huge_table", caller_identity="admin")

    assert res["status"] == "success"
    assert res["row_count"] == 1000
    mock_result.fetchmany.assert_called_with(1000)


@pytest.mark.asyncio
async def test_sqlite_readonly():
    mock_session = AsyncMock()
    mock_session.bind = MagicMock()
    mock_session.bind.dialect.name = "sqlite"
    mock_result = MagicMock()
    mock_row = MagicMock()
    mock_row._mapping = {"col1": "val1"}
    mock_result.fetchmany.return_value = [mock_row]
    mock_session.execute = AsyncMock(return_value=mock_result)

    service = DatabaseService(session=mock_session)
    await service.execute_query("SELECT 1", caller_identity="admin")

    call_args = mock_session.execute.call_args_list
    assert "PRAGMA query_only = 1" in str(call_args[0][0][0])
    assert "PRAGMA query_only = 0" in str(call_args[2][0][0])


@pytest.mark.asyncio
async def test_execute_query_auth():
    mock_session = AsyncMock()
    service = DatabaseService(session=mock_session)

    with pytest.raises(ValueError, match="غير مصرح لك بتنفيذ الاستعلام"):
        await service.execute_query("SELECT 1", require_admin=True, caller_identity=None)

    with pytest.raises(ValueError, match="غير مصرح لك بتنفيذ الاستعلام"):
        await service.execute_query("SELECT 1", require_admin=True, caller_identity="unknown")


@pytest.mark.asyncio
async def test_execute_query_db_error():
    mock_session = AsyncMock()
    mock_session.begin_nested = MagicMock(return_value=DummyContextManager())
    mock_session.bind = MagicMock()
    mock_session.bind.dialect.name = "postgresql"
    mock_session.execute = AsyncMock(side_effect=Exception("DB connection dropped"))

    service = DatabaseService(session=mock_session)
    res = await service.execute_query("SELECT 1", caller_identity="admin")

    assert res["status"] == "error"
    assert "حدث خطأ أثناء تنفيذ الاستعلام الأمني" in res["message"]
