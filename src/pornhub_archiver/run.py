import asyncio
import subprocess
import sys
from datetime import datetime, timedelta, UTC

from . import db
from .archive_job import ArchiveJob, STEP_SLEEP_INTERVAL
from .channel import Channel, CONCURRENT_FRAGMENT_DOWNLOADS
from .config import (
    CONFIG_WARNINGS,
    DATA_PATH,
    DB_HOST,
    DB_PASSWORD,
    DB_PORT,
    DB_USER,
    OPENSSL_CONF,
    RUN_ONCE,
    SLEEP_INTERVAL,
)
from .logger import CONSOLE_COLORS, LOG_PATH, LOKI_APP_LABEL, LOKI_LABELS, LOKI_TIMEOUT, LOKI_URL, logger

VERSION = (4, 7, 2)


async def main() -> None:
    await logger.start()
    try:
        await db.start()
        await _print_startup_info()
        await _update_yt_dlp()
        await _ensure_db_table_exist()

        while True:
            await _run_archive_once()
            if RUN_ONCE:
                await logger.info("system - RUN_ONCE enabled; exiting")
                break
            await logger.info(f"system - next run at {datetime.now(UTC) + timedelta(seconds=SLEEP_INTERVAL)}")
            await asyncio.sleep(SLEEP_INTERVAL)
    finally:
        await db.close()
        await logger.stop()


# -----------------------------------------------------------------------------
# Startup helpers
# -----------------------------------------------------------------------------

async def _run_archive_once() -> None:
    channels = await Channel.get_all_channels(DATA_PATH)
    await ArchiveJob(channels, DATA_PATH).archive_all()


async def _print_startup_info() -> None:
    for warning in CONFIG_WARNINGS:
        await logger.warning(f"system - configuration fallback: {warning}")

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
        "RUN_ONCE":            RUN_ONCE,
        "STEP_SLEEP_INTERVAL": STEP_SLEEP_INTERVAL,
        "LOKI_URL":            LOKI_URL,
        "LOKI_APP_LABEL":      LOKI_APP_LABEL,
        "LOKI_LABELS":         LOKI_LABELS,
        "LOKI_TIMEOUT":        LOKI_TIMEOUT,
        "LOG_PATH":            LOG_PATH,
        "CONSOLE_COLORS":      CONSOLE_COLORS,
        "CONCURRENT_FRAGMENT_DOWNLOADS": CONCURRENT_FRAGMENT_DOWNLOADS,
    }
    for key, value in settings.items():
        await logger.info(f"system - {key}={value}")


async def _update_yt_dlp() -> None:
    old = _yt_dlp_version()
    subprocess.run(
        [sys.executable, "-m", "pip", "install", "--upgrade", "--pre", "yt-dlp"],
        check=False,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    new = _yt_dlp_version()
    await logger.info(f"system - yt-dlp {old} => {new}")


def _yt_dlp_version() -> str:
    result = subprocess.run(["yt-dlp", "--version"], check=False, capture_output=True, text=True)
    return result.stdout.strip()


async def _ensure_db_table_exist() -> None:
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
