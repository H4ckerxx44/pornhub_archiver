import asyncio
import json
import os
import sys
import tempfile
import types
import unittest
from pathlib import Path


class _Logger:
    def __init__(self) -> None:
        self.messages: list[tuple[str, str]] = []

    async def info(self, msg: str) -> None:
        self.messages.append(("info", msg))

    async def debug(self, msg: str) -> None:
        self.messages.append(("debug", msg))

    async def warning(self, msg: str) -> None:
        self.messages.append(("warning", msg))

    async def error(self, msg: str) -> None:
        self.messages.append(("error", msg))


sys.modules.setdefault("yt_dlp", types.SimpleNamespace(YoutubeDL=object))
sys.modules.setdefault("pornhub_archiver.db", types.SimpleNamespace(execute_query=None))
sys.modules.setdefault("pornhub_archiver.logger", types.SimpleNamespace(logger=_Logger()))

import pornhub_archiver.archive_job as archive_job_module
from pornhub_archiver.archive_job import ArchiveJob


class FakeChannel:
    def __init__(
            self,
            name: str,
            file_count: int = 0,
            size: int = 0,
            deleted: int = 0,
            missing: list[str] | None = None,
            archived_this_time: int = 0,
            size_downloaded: int = 0,
    ) -> None:
        self.name = name
        self.file_count = file_count
        self.size = size
        self.deleted = deleted
        self.missing = missing or []
        self.missing_videos = self.missing
        self.archived_this_time = archived_this_time
        self.size_downloaded = size_downloaded
        self.size_before = 0
        self.error_count = 0
        self.videos_on_disk: dict[str, bool] = {}
        self.offline_videos: list[str] = []
        self.archive_calls: list[tuple[int, int]] = []

    def create_path(self) -> int:
        return self.file_count

    def get_channel_size(self) -> int:
        return self.size

    def cleanup(self) -> int:
        return self.deleted

    def get_name(self) -> str:
        return self.name

    async def get_metadata(self, channel_number: int, total_channels: int) -> list[str]:
        return self.missing

    async def archive(self, current_channel_number: int, total_channels: int) -> None:
        self.archive_calls.append((current_channel_number, total_channels))

    def run_report(self) -> dict:
        return {
            "name": self.name,
            "link": f"https://example.test/{self.name}",
            "path": f"/tmp/archive/{self.name}",
            "archived_on_disk": len(self.videos_on_disk),
            "missing": len(self.missing_videos),
            "missing_video_ids": self.missing_videos,
            "offline": len(self.offline_videos),
            "offline_video_ids": self.offline_videos,
            "downloaded_this_run": self.archived_this_time,
            "download_failures": max(len(self.missing_videos) - self.archived_this_time, 0),
            "errors": self.error_count,
            "bytes_before": self.size_before,
            "bytes_before_human": "fake",
            "bytes_added": self.size_downloaded,
            "bytes_added_human": "fake",
            "bytes_after": self.size_before + self.size_downloaded,
            "bytes_after_human": "fake",
        }


class ArchiveJobTests(unittest.TestCase):
    def setUp(self) -> None:
        self.old_env = os.environ.copy()
        self.logger = _Logger()
        self.original_logger = archive_job_module.logger
        self.original_sleep = archive_job_module.asyncio.sleep
        self.original_step_sleep_interval = archive_job_module.STEP_SLEEP_INTERVAL
        archive_job_module.logger = self.logger
        archive_job_module.STEP_SLEEP_INTERVAL = 0

        async def no_sleep(seconds: float) -> None:
            return None

        archive_job_module.asyncio.sleep = no_sleep

    def tearDown(self) -> None:
        os.environ.clear()
        os.environ.update(self.old_env)
        archive_job_module.logger = self.original_logger
        archive_job_module.asyncio.sleep = self.original_sleep
        archive_job_module.STEP_SLEEP_INTERVAL = self.original_step_sleep_interval

    def test_create_paths_returns_total_file_count(self) -> None:
        channels = [FakeChannel("a", file_count=2, size=100), FakeChannel("b", file_count=3, size=200)]
        job = ArchiveJob(channels, Path("/tmp/archive"))

        self.assertEqual(asyncio.run(job._create_paths()), 5)

    def test_cleanup_paths_returns_total_deleted_count(self) -> None:
        channels = [FakeChannel("a", deleted=1), FakeChannel("b", deleted=4)]
        job = ArchiveJob(channels, Path("/tmp/archive"))

        self.assertEqual(asyncio.run(job._cleanup_paths()), 5)

    def test_collect_channels_with_missing_videos_filters_empty_channels(self) -> None:
        missing = FakeChannel("missing", missing=["ph1"])
        current = FakeChannel("current")
        job = ArchiveJob([missing, current], Path("/tmp/archive"))

        self.assertEqual(asyncio.run(job._collect_channels_with_missing_videos()), [missing])

    def test_download_all_tracks_archived_count_and_size(self) -> None:
        channels = [
            FakeChannel("a", archived_this_time=2, size_downloaded=1024),
            FakeChannel("b", archived_this_time=1, size_downloaded=2048),
        ]
        job = ArchiveJob(channels, Path("/tmp/archive"))

        asyncio.run(job._download_all(channels))

        self.assertEqual(job.total_archived, 3)
        self.assertEqual(job.archived_data, 3072)
        self.assertEqual(channels[0].archive_calls, [(1, 2)])
        self.assertEqual(channels[1].archive_calls, [(2, 2)])

    def test_archive_all_writes_timestamped_run_report(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            os.environ["LOG_PATH"] = tmp
            channel = FakeChannel("a", file_count=2, deleted=1, missing=["ph1"], archived_this_time=1, size_downloaded=1024)
            channel.videos_on_disk = {"ph0": True}
            channel.offline_videos = ["ph-old"]
            job = ArchiveJob([channel], Path("/tmp/archive"))

            asyncio.run(job.archive_all())

            report_files = list(Path(tmp).glob("*.json"))
            self.assertEqual(len(report_files), 1)
            self.assertRegex(report_files[0].name, r"^\d{4}-\d{2}-\d{2}_\d{2}-\d{2}-\d{2}_\d{6}Z\.json$")

            report_path = report_files[0]
            report = json.loads(report_path.read_text(encoding="utf-8"))

        self.assertEqual(report["channels_scanned"], 1)
        self.assertEqual(report["channels_with_missing"], 1)
        self.assertEqual(report["channels_skipped"], 0)
        self.assertEqual(report["files_on_disk"], 2)
        self.assertEqual(report["partial_files_deleted"], 1)
        self.assertEqual(report["videos_missing"], 1)
        self.assertEqual(report["videos_downloaded"], 1)
        self.assertEqual(report["videos_failed"], 0)
        self.assertEqual(report["download_failures"], 0)
        self.assertEqual(report["bytes_before"], 0)
        self.assertEqual(report["bytes_added"], 1024)
        self.assertEqual(report["bytes_after"], 1024)
        self.assertEqual(report["channels"][0]["name"], "a")
        self.assertEqual(report["channels"][0]["path"], "/tmp/archive/a")
        self.assertEqual(report["channels"][0]["missing"], 1)
        self.assertEqual(report["channels"][0]["missing_video_ids"], ["ph1"])
        self.assertEqual(report["channels"][0]["offline"], 1)
        self.assertEqual(report["channels"][0]["offline_video_ids"], ["ph-old"])
        self.assertEqual(report["channels"][0]["download_failures"], 0)

    def test_run_reports_do_not_overwrite_older_runs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            os.environ["LOG_PATH"] = tmp
            job = ArchiveJob([FakeChannel("a")], Path("/tmp/archive"))

            asyncio.run(job.archive_all())
            asyncio.run(job.archive_all())

            report_files = list(Path(tmp).glob("*.json"))

        self.assertEqual(len(report_files), 2)


if __name__ == "__main__":
    unittest.main()
