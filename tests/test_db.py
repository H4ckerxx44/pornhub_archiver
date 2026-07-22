import asyncio
import importlib
import sys
import types
import unittest


class FakeCursor:
    def __init__(self) -> None:
        self.executed: list[tuple[str, object]] = []

    async def __aenter__(self) -> "FakeCursor":
        return self

    async def __aexit__(self, *args: object) -> None:
        return None

    async def execute(self, sql: str, val: object) -> None:
        self.executed.append((sql, val))

    async def fetchall(self) -> tuple[tuple[int]]:
        return ((1,),)


class FakeConnection:
    def __init__(self, cursor: FakeCursor) -> None:
        self._cursor = cursor
        self.commits = 0

    async def __aenter__(self) -> "FakeConnection":
        return self

    async def __aexit__(self, *args: object) -> None:
        return None

    def cursor(self) -> FakeCursor:
        return self._cursor

    async def commit(self) -> None:
        self.commits += 1


class FakePool:
    def __init__(self, connection: FakeConnection) -> None:
        self._connection = connection

    async def __aenter__(self) -> "FakePool":
        return self

    async def __aexit__(self, *args: object) -> None:
        return None

    def acquire(self) -> FakeConnection:
        return self._connection

    def close(self) -> None:
        return None

    async def wait_closed(self) -> None:
        return None


class FakeAiomysql:
    def __init__(self) -> None:
        self.cursor = FakeCursor()
        self.connection = FakeConnection(self.cursor)
        self.pool = FakePool(self.connection)
        self.create_pool_kwargs: dict | None = None

    async def create_pool(self, **kwargs: object) -> FakePool:
        self.create_pool_kwargs = kwargs
        return self.pool


def import_db_module(fake_aiomysql: FakeAiomysql) -> types.ModuleType:
    sys.modules.pop("pornhub_archiver.db", None)
    sys.modules["aiomysql"] = fake_aiomysql
    return importlib.import_module("pornhub_archiver.db")


class DbTests(unittest.TestCase):
    def test_execute_query_uses_pool_and_commits(self) -> None:
        fake_aiomysql = FakeAiomysql()
        db = import_db_module(fake_aiomysql)

        rows = asyncio.run(db.execute_query("select %s", (1,)))

        self.assertEqual(rows, ((1,),))
        self.assertEqual(fake_aiomysql.cursor.executed, [("select %s", (1,))])
        self.assertEqual(fake_aiomysql.connection.commits, 1)
        self.assertEqual(fake_aiomysql.create_pool_kwargs["db"], "ph_archiver")
        self.assertEqual(fake_aiomysql.create_pool_kwargs["pool_recycle"], 15)

    def test_execute_query_reuses_pool(self) -> None:
        fake_aiomysql = FakeAiomysql()
        db = import_db_module(fake_aiomysql)

        asyncio.run(db.execute_query("select 1"))
        asyncio.run(db.execute_query("select 2"))

        self.assertEqual(fake_aiomysql.cursor.executed, [("select 1", ()), ("select 2", ())])
        self.assertEqual(fake_aiomysql.create_pool_kwargs["db"], "ph_archiver")

    def test_close_releases_pool(self) -> None:
        fake_aiomysql = FakeAiomysql()
        db = import_db_module(fake_aiomysql)

        asyncio.run(db.execute_query("select 1"))
        asyncio.run(db.close())
        asyncio.run(db.close())

        self.assertIsNone(db._pool)

    def test_create_table_executes_channels_schema(self) -> None:
        fake_aiomysql = FakeAiomysql()
        db = import_db_module(fake_aiomysql)

        asyncio.run(db.create_table())

        sql, val = fake_aiomysql.cursor.executed[0]
        self.assertIn("create table channels", sql)
        self.assertIn("is_active tinyint(1)", sql)
        self.assertEqual(val, ())


if __name__ == "__main__":
    unittest.main()
