import asyncio
import os
import pathlib

import db
from archive_job import ArchiveJob, STEP_SLEEP_INTERVAL
from channel import Channel
from db import DB_HOST, DB_PORT

ROOT_PATH = pathlib.Path("/data")
SLEEP_INTERVAL = int(os.getenv("SLEEP_INTERVAL", 3600))


MAJOR = 1
MINOR = 4
PATCH = 0

# ROOT_PATH = pathlib.Path("F:/auto_dl")
# SLEEP_INTERVAL = 3600

async def main():
    await asyncio.sleep(0)
    print(f"system - running version v{MAJOR}.{MINOR}.{PATCH}")
    print(f"system - ROOT_PATH={ROOT_PATH}")
    print(f"system - SLEEP_INTERVAL={SLEEP_INTERVAL}")
    print(f"system - DB_HOST={DB_HOST}")
    print(f"system - DB_PORT={DB_PORT}")
    print(f"system - STEP_SLEEP_INTERVAL={STEP_SLEEP_INTERVAL}")

    db_exists = await db.execute_query("SELECT count(*) FROM information_schema.tables WHERE table_schema = 'ph_archiver' AND table_name = 'channels'")
    result = db_exists[0][0]
    if result:
        print("system - database table exists")

    if not result:
        print("system - creating table")
        await db.create_table()

    while True:
        channels: list[Channel] = await Channel.get_all_channels(ROOT_PATH)
        archive_job = ArchiveJob(channels, ROOT_PATH)

        await archive_job.archive_all()
        await asyncio.sleep(SLEEP_INTERVAL)


if __name__ == "__main__":
    asyncio.run(main())
