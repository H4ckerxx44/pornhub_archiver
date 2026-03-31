import asyncio
import os
import pathlib
import subprocess

import db
from archive_job import ArchiveJob, STEP_SLEEP_INTERVAL
from channel import Channel
from db import DB_HOST, DB_PORT, DB_USER, DB_PASSWORD

# os.environ["OPENSSL_CONF"] = "/dev/null"

ROOT_PATH = pathlib.Path("/data")
SLEEP_INTERVAL = int(os.getenv("SLEEP_INTERVAL", 3600))
OPENSSL_CONF = os.getenv("OPENSSL_CONF")


MAJOR = 2
MINOR = 1
PATCH = 0

async def main():
    print(f"system - running version v{MAJOR}.{MINOR}.{PATCH}")
    print(f"system - OPENSSL_CONF={OPENSSL_CONF}")
    print(f"system - ROOT_PATH={ROOT_PATH}")
    print(f"system - DB_HOST={DB_HOST}")
    print(f"system - DB_PORT={DB_PORT}")
    print(f"system - DB_USER={DB_USER}")
    print(f"system - DB_PASSWORD={DB_PASSWORD}")
    print(f"system - SLEEP_INTERVAL={SLEEP_INTERVAL}")
    print(f"system - STEP_SLEEP_INTERVAL={STEP_SLEEP_INTERVAL}")

    print(f"system - old yt-dlp version: ", end="")
    subprocess.run("yt-dlp --version", shell=True)

    print(f"system - updating yt-dlp...", end="")
    subprocess.run("pip install --upgrade --pre yt-dlp", shell=True, stdout=subprocess.DEVNULL)

    print(f"system - new yt-dlp version: ", end="")
    subprocess.run("yt-dlp --version", shell=True)

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
