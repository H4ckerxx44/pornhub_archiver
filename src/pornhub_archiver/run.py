import asyncio
import os
import pathlib
import subprocess
from datetime import datetime, timedelta, UTC

from . import db
from .archive_job import ArchiveJob, STEP_SLEEP_INTERVAL
from .channel import Channel
from .db import DB_HOST, DB_PORT, DB_USER, DB_PASSWORD
from .logger import CONSOLE_COLORS, LOG_PATH, LOKI_APP_LABEL, LOKI_LABELS, LOKI_TIMEOUT, LOKI_URL, logger

DATA_PATH = pathlib.Path(os.getenv("DATA_PATH", "/data"))
SLEEP_INTERVAL = int(os.getenv("SLEEP_INTERVAL", 3600))
OPENSSL_CONF = os.getenv("OPENSSL_CONF")

VERSION = (4, 1, 1)


async def main() -> None:
    await logger.start()
    try:
        await _print_startup_info()
        await _update_yt_dlp()
        await _ensure_db()

        while True:
            channels = await Channel.get_all_channels(DATA_PATH)
            await ArchiveJob(channels, DATA_PATH).archive_all()
            await logger.info(f"system - next run at {datetime.now(UTC) + timedelta(seconds=SLEEP_INTERVAL)}")
            await asyncio.sleep(SLEEP_INTERVAL)
    finally:
        await logger.stop()


# -----------------------------------------------------------------------------
# Startup helpers
# -----------------------------------------------------------------------------

async def _print_startup_info() -> None:
    version_str = ".".join(str(v) for v in VERSION)
    settings = {
        "version":             f"v{version_str}",
        "OPENSSL_CONF":        OPENSSL_CONF,
        "DATA_PATH":           DATA_PATH,
        "DB_HOST":             DB_HOST,
        "DB_PORT":             DB_PORT,
        "DB_USER":             DB_USER,
        "DB_PASSWORD":         DB_PASSWORD,
        "SLEEP_INTERVAL":      SLEEP_INTERVAL,
        "STEP_SLEEP_INTERVAL": STEP_SLEEP_INTERVAL,
        "LOKI_URL":            LOKI_URL,
        "LOKI_APP_LABEL":      LOKI_APP_LABEL,
        "LOKI_LABELS":         LOKI_LABELS,
        "LOKI_TIMEOUT":        LOKI_TIMEOUT,
        "LOG_PATH":            LOG_PATH,
        "CONSOLE_COLORS":      CONSOLE_COLORS,
    }
    for key, value in settings.items():
        await logger.info(f"system - {key}={value}")


async def _update_yt_dlp() -> None:
    old = _yt_dlp_version()
    subprocess.run(
        "pip install --upgrade --pre yt-dlp",
        shell=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    new = _yt_dlp_version()
    await logger.info(f"system - yt-dlp {old} => {new}")


def _yt_dlp_version() -> str:
    result = subprocess.run("yt-dlp --version", shell=True, capture_output=True, text=True)
    return result.stdout.strip()


async def _ensure_db() -> None:
    rows = await db.execute_query(
        "SELECT count(*) FROM information_schema.tables "
        "WHERE table_schema = 'ph_archiver' AND table_name = 'channels'"
    )
    table_exists = bool(rows[0][0])

    if table_exists:
        await logger.info("system - database table exists")
    else:
        await logger.info("system - creating table")
        await db.create_table()


if __name__ == "__main__":
    asyncio.run(main())
