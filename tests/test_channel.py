import asyncio
import sys
import tempfile
import types
import unittest
from datetime import UTC, datetime
from pathlib import Path


class _Logger:
    async def info(self, msg: str) -> None:
        return None

    async def warning(self, msg: str) -> None:
        return None

    async def error(self, msg: str) -> None:
        return None


async def _execute_query(sql: str, val: object = ()) -> tuple:
    return ()


class _YoutubeDL:
    def __init__(self, options: dict) -> None:
        self.options = options

    def __enter__(self) -> "_YoutubeDL":
        return self

    def __exit__(self, *args: object) -> None:
        return None


sys.modules.setdefault("pornhub_archiver.db", types.SimpleNamespace(execute_query=_execute_query))
sys.modules.setdefault("pornhub_archiver.logger", types.SimpleNamespace(logger=_Logger()))
sys.modules.setdefault("yt_dlp", types.SimpleNamespace(YoutubeDL=_YoutubeDL))

import pornhub_archiver.channel as channel_module
from pornhub_archiver.channel import MAX_ERRORS, Channel
from pornhub_archiver.functions import video_id_from_link


def make_channel(data_path: Path) -> Channel:
    return Channel(
        db_id=1,
        link="https://www.pornhub.com/model/example",
        total_videos=0,
        archived_videos=0,
        added_on=datetime.now(UTC),
        last_queried_at=datetime.now(UTC),
        data_path=data_path,
    )


class ChannelNormalizationTests(unittest.TestCase):
    def test_normalize_link_removes_video_suffix_and_trailing_slash(self) -> None:
        cases = {
            "https://www.pornhub.com/model/example/videos": "https://www.pornhub.com/model/example",
            "https://www.pornhub.com/model/example/videos/": "https://www.pornhub.com/model/example",
            "https://www.pornhub.com/model/example/": "https://www.pornhub.com/model/example",
        }

        for raw, expected in cases.items():
            with self.subTest(raw=raw):
                self.assertEqual(asyncio.run(Channel._normalize_link(raw)), expected)


class VideoIdParsingTests(unittest.TestCase):
    def test_video_id_from_link_accepts_supported_shapes(self) -> None:
        cases = {
            "https://www.pornhub.org/view_video.php?viewkey=ph123&foo=bar": "ph123",
            "https://example.test/watch?id=ph456&x=1": "ph456",
            "https://example.test/videos/ph789/": "ph789",
            "ph000": "ph000",
        }

        for raw, expected in cases.items():
            with self.subTest(raw=raw):
                self.assertEqual(video_id_from_link(raw), expected)

    def test_video_id_from_link_rejects_empty_input(self) -> None:
        with self.assertRaises(ValueError):
            video_id_from_link("")


class ChannelDiskTests(unittest.TestCase):
    def test_scan_disk_only_tracks_bracketed_video_ids(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            channel = make_channel(Path(tmp))
            channel.create_path()

            (channel.channel_path / "[ph123] title.mp4").touch()
            (channel.channel_path / "[ph123] title.info.json").touch()
            (channel.channel_path / "[ph456] title.mp4").touch()
            (channel.channel_path / "notes.txt").touch()
            (channel.channel_path / "ph999 title.mp4").touch()

            channel._scan_disk()

            self.assertEqual(channel.videos_on_disk, {"ph123": True, "ph456": True})

    def test_cleanup_removes_partial_files_only(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            channel = make_channel(Path(tmp))
            channel.create_path()

            keep = channel.channel_path / "[ph123] title.mp4"
            part = channel.channel_path / "[ph123] title.mp4.part"
            fragment = channel.channel_path / "[ph123] title.mp4.part-Frag1"
            keep.touch()
            part.touch()
            fragment.touch()

            self.assertEqual(channel.cleanup(), 2)
            self.assertTrue(keep.exists())
            self.assertFalse(part.exists())
            self.assertFalse(fragment.exists())


class ChannelReportTests(unittest.TestCase):
    def test_run_report_returns_channel_summary(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            channel = make_channel(Path(tmp))
            channel.create_path()
            (channel.channel_path / "[ph0] title.mp4").write_bytes(b"x" * 3072)
            channel.videos_on_disk = {"ph0": True, "ph1": True}
            channel.missing_videos = ["ph2"]
            channel.offline_videos = ["ph-old"]
            channel.archived_this_time = 1
            channel.error_count = 2
            channel.size_before = 2048
            channel.size_downloaded = 1024

            self.assertEqual(
                channel.run_report(),
                {
                    "name": "example",
                    "link": "https://www.pornhub.com/model/example",
                    "path": str(channel.channel_path),
                    "archived_on_disk": 2,
                    "missing": 1,
                    "missing_video_ids": ["ph2"],
                    "offline": 1,
                    "offline_video_ids": ["ph-old"],
                    "metadata_fetch_failed": False,
                    "downloaded_this_run": 1,
                    "download_failures": 0,
                    "errors": 2,
                    "bytes_before": 2048,
                    "bytes_before_human": "2.00 KiB",
                    "bytes_added": 1024,
                    "bytes_added_human": "1.00 KiB",
                    "bytes_after": 3072,
                    "bytes_after_human": "3.00 KiB",
                },
            )


class MetadataRetryTests(unittest.TestCase):
    def tearDown(self) -> None:
        channel_module.YoutubeDL = _YoutubeDL

    def test_fetch_channel_video_ids_retries_and_then_returns_ids(self) -> None:
        attempts = 0

        class RetryingYoutubeDL(_YoutubeDL):
            def extract_info(self, url: str, download: bool) -> dict:
                nonlocal attempts
                attempts += 1
                if attempts < 3:
                    raise RuntimeError("temporary failure")
                return {
                    "entries": [
                        {"url": "https://www.pornhub.org/view_video.php?viewkey=ph123&x=1"},
                        {"url": "ph456"},
                    ]
                }

        channel_module.YoutubeDL = RetryingYoutubeDL

        with tempfile.TemporaryDirectory() as tmp:
            channel = make_channel(Path(tmp))
            ids, error = asyncio.run(channel._fetch_channel_video_ids(0, 1))

        self.assertFalse(error)
        self.assertEqual(ids, ["ph123", "ph456"])
        self.assertEqual(attempts, 3)

    def test_fetch_channel_video_ids_stops_after_max_errors(self) -> None:
        attempts = 0

        class FailingYoutubeDL(_YoutubeDL):
            def extract_info(self, url: str, download: bool) -> dict:
                nonlocal attempts
                attempts += 1
                raise RuntimeError("permanent failure")

        channel_module.YoutubeDL = FailingYoutubeDL

        with tempfile.TemporaryDirectory() as tmp:
            channel = make_channel(Path(tmp))
            ids, error = asyncio.run(channel._fetch_channel_video_ids(0, 1))

        self.assertTrue(error)
        self.assertEqual(ids, [])
        self.assertEqual(attempts, MAX_ERRORS)

    def test_fetch_missing_videos_does_not_mark_local_videos_offline_on_error(self) -> None:
        async def failed_metadata_fetch(
            channel_number: int,
            total_channels: int,
        ) -> tuple[list[str], bool]:
            return [], True

        with tempfile.TemporaryDirectory() as tmp:
            channel = make_channel(Path(tmp))
            channel.create_path()
            (channel.channel_path / "[ph123] title.mp4").touch()
            channel._fetch_channel_video_ids = failed_metadata_fetch

            missing, error = asyncio.run(channel._fetch_missing_videos(0, 1))

        self.assertTrue(error)
        self.assertTrue(channel.metadata_fetch_failed)
        self.assertEqual(missing, [])
        self.assertEqual(channel.missing_videos, [])
        self.assertEqual(channel.offline_videos, [])


if __name__ == "__main__":
    unittest.main()
