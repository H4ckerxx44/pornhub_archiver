import os
from typing import Any

import aiomysql

DB_HOST = os.getenv('DB_HOST', 'localhost')
DB_PORT = int(os.getenv('DB_PORT', '3306'))
DB_USER = os.getenv('DB_USER', 'root')
DB_PASSWORD = os.getenv('DB_PASSWORD', '')

# DB_HOST = "192.168.0.100"
# DB_PORT = 3306

async def execute_query(sql: str, val: Any = ()):
    async with aiomysql.create_pool(
            host=DB_HOST,
            port=DB_PORT,
            user=DB_USER,
            password=DB_PASSWORD,
            db="ph_archiver"
    ) as pool:
        async with pool.acquire() as conn:
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
