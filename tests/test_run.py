import asyncio
import importlib
import os
import sys
import types
import unittest


class FakeLogger:
    def __init__(self) -> None:
        self.started = False
        self.stopped = False
        self.messages: list[str] = []

    async def start(self) -> None:
        self.started = True

    async def stop(self) -> None:
        self.stopped = True

    async def info(self, msg: str) -> None:
        self.messages.append(msg)


class FakeArchiveJob:
    instances: list["FakeArchiveJob"] = []

    def __init__(self, channels: list[str], data_path: object) -> None:
        self.channels = channels
        self.data_path = data_path
        self.archive_calls = 0
        self.instances.append(self)

    async def archive_all(self) -> None:
        self.archive_calls += 1


class FakeChannel:
    calls = 0

    @staticmethod
    async def get_all_channels(data_path: object) -> list[str]:
        FakeChannel.calls += 1
        return ["channel"]


def import_run_module(run_once: str | None) -> tuple[types.ModuleType, FakeLogger]:
    sys.modules.pop("pornhub_archiver.run", None)

    if run_once is None:
        os.environ.pop("RUN_ONCE", None)
    else:
        os.environ["RUN_ONCE"] = run_once

    logger = FakeLogger()
    FakeArchiveJob.instances = []
    FakeChannel.calls = 0

    sys.modules["pornhub_archiver.db"] = types.SimpleNamespace(
        DB_HOST="localhost",
        DB_PORT=3306,
        DB_USER="root",
        DB_PASSWORD="",
        execute_query=None,
    )
    sys.modules["pornhub_archiver.archive_job"] = types.SimpleNamespace(
        ArchiveJob=FakeArchiveJob,
        STEP_SLEEP_INTERVAL=0,
    )
    sys.modules["pornhub_archiver.channel"] = types.SimpleNamespace(
        Channel=FakeChannel,
        CONCURRENT_FRAGMENT_DOWNLOADS=4,
    )
    sys.modules["pornhub_archiver.logger"] = types.SimpleNamespace(
        CONSOLE_COLORS=True,
        LOG_PATH="/logs",
        LOKI_APP_LABEL="pornhub-archiver",
        LOKI_LABELS="",
        LOKI_TIMEOUT=5,
        LOKI_URL="",
        logger=logger,
    )

    return importlib.import_module("pornhub_archiver.run"), logger


class RunTests(unittest.TestCase):
    def setUp(self) -> None:
        self.old_env = os.environ.copy()

    def tearDown(self) -> None:
        os.environ.clear()
        os.environ.update(self.old_env)
        sys.modules.pop("pornhub_archiver.run", None)

    def test_run_once_env_parses_truthy_value(self) -> None:
        run, _logger = import_run_module("true")

        self.assertTrue(run.RUN_ONCE)

    def test_run_once_env_defaults_false(self) -> None:
        run, _logger = import_run_module(None)

        self.assertFalse(run.RUN_ONCE)

    def test_main_exits_after_one_archive_pass_when_run_once_enabled(self) -> None:
        run, logger = import_run_module("true")

        async def no_op() -> None:
            return None

        run._print_startup_info = no_op
        run._update_yt_dlp = no_op
        run._ensure_db_table_exist = no_op

        asyncio.run(run.main())

        self.assertTrue(logger.started)
        self.assertTrue(logger.stopped)
        self.assertEqual(FakeChannel.calls, 1)
        self.assertEqual(len(FakeArchiveJob.instances), 1)
        self.assertEqual(FakeArchiveJob.instances[0].archive_calls, 1)
        self.assertIn("system - RUN_ONCE enabled; exiting", logger.messages)
        self.assertFalse(any(message.startswith("system - next run at") for message in logger.messages))


if __name__ == "__main__":
    unittest.main()
