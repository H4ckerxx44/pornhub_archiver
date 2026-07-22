from __future__ import annotations

from typing import Any

import aiomysql

from .config import DB_HOST, DB_NAME, DB_PASSWORD, DB_PORT, DB_USER

_pool: aiomysql.Pool | None = None


async def start() -> None:
    """Create the shared database connection pool."""
    global _pool
    if _pool is None:
        _pool = await aiomysql.create_pool(
            host=DB_HOST,
            port=DB_PORT,
            user=DB_USER,
            password=DB_PASSWORD,
            db=DB_NAME,
            maxsize=100,
            pool_recycle=15,
        )


async def close() -> None:
    """Close the shared database connection pool, if it exists."""
    global _pool
    if _pool is None:
        return

    _pool.close()
    await _pool.wait_closed()
    _pool = None


async def execute_query(sql: str, val: Any = ()):
    await start()
    assert _pool is not None
    async with _pool.acquire() as conn:
        async with conn.cursor() as cursor:
            await cursor.execute(sql, val)
            res = await cursor.fetchall()
        await conn.commit()

    return res


async def create_table():
    await execute_query("""
                        create table channels(
                        id int auto_increment primary key,
                        link text not null,
                        comment text null,
                        total_videos int default 0 not null,
                        archived_videos int default 0 not null,
                        added_on datetime default current_timestamp() not null,
                        last_queried_at datetime default current_timestamp() not null,
                        is_active tinyint(1) default 1 not null,
                        constraint channels_link_uindex unique (link) using hash
                        );""", ())
