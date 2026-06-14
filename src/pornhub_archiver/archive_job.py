import asyncio
import json
import os
from datetime import datetime, UTC
from pathlib import Path

from .channel import Channel
from .functions import nice_timedelta, format_si
from .logger import logger

STEP_SLEEP_INTERVAL = int(os.getenv("STEP_SLEEP_INTERVAL", 15))


class ArchiveJob:
    def __init__(self, channels: list[Channel], data_path: Path):
        self.archived_data: int = 0
        self.total_archived: int = 0
        self.channels = channels
        self.start = datetime.now(UTC)
        self.data_path = data_path
        self.total_files: int = 0
        self.total_deleted: int = 0
        self.total_missing: int = 0
        self.channels_with_missing: int = 0
        self.bytes_before: int = 0

    # -------------------------------------------------------------------------
    # Public API
    # -------------------------------------------------------------------------

    async def archive_all(self) -> None:
        run_start = datetime.now(UTC)
        await logger.info(f"system - archiving {len(self.channels):,} channels")

        self.total_files = await self._create_paths()
        await logger.info(f"system - found {self.total_files:,} files in total")

        self.total_deleted = await self._cleanup_paths()
        await logger.info(f"system - deleted {self.total_deleted:,} files in cleanup")

        channels_to_download = await self._collect_channels_with_missing_videos()

        await self._download_all(channels_to_download)

        elapsed = nice_timedelta(datetime.now(UTC), run_start)
        await logger.info(f"system - total runtime: {elapsed}")
        await logger.info(f"system - total archived this run: {self.total_archived:,}")
        await self._write_run_report(run_start, datetime.now(UTC), elapsed)

    # -------------------------------------------------------------------------
    # Steps
    # -------------------------------------------------------------------------

    async def _create_paths(self) -> int:
        start = datetime.now(UTC)
        total_files = 0
        total_size = 0

        for j, channel in enumerate(self.channels):
            file_count = channel.create_path()
            channel_size = channel.get_channel_size()
            channel.size_before = channel_size
            total_files += file_count
            total_size += channel_size
            await logger.debug(
                f"\t[{j+1}/{len(self.channels):,}] {channel.get_name()} - "
                f"{file_count:,} files "
                f"(total: {total_files:,} / {format_si(total_size)})"
            )

        await logger.info(f"system - creating/checking paths took {nice_timedelta(datetime.now(UTC), start)}")
        await logger.info(f"system - total files: {total_files:,}, total size: {format_si(total_size)}")
        return total_files

    async def _cleanup_paths(self) -> int:
        start = datetime.now(UTC)
        total_deleted = 0

        for j, channel in enumerate(self.channels):
            step_start = datetime.now(UTC)
            deleted = channel.cleanup()
            channel.size_before = channel.get_channel_size()
            total_deleted += deleted
            elapsed = datetime.now(UTC) - step_start
            await logger.debug(
                f"\t[{j+1}/{len(self.channels):,}] {channel.get_name()} - "
                f"deleted {deleted:,} files, took: {elapsed}"
            )

        await logger.info(f"system - cleanup took {datetime.now(UTC) - start}")
        self.bytes_before = sum(channel.size_before for channel in self.channels)
        return total_deleted

    async def _collect_channels_with_missing_videos(self) -> list[Channel]:
        """Fetch metadata for all channels concurrently, then return those with missing videos."""
        start = datetime.now(UTC)
        total_channels = len(self.channels)

        await logger.info(f"system - fetching metadata for {total_channels:,} channels")

        # tasks = [self._fetch_channel_metadata(channel) for channel in self.channels]
        # results: list[tuple[Channel, list]] = await asyncio.gather(*tasks)

        results: list[tuple[Channel, list]] = [await self._fetch_channel_metadata(channel, i, total_channels) for i, channel in enumerate(self.channels)]

        await logger.info(f"system - metadata fetch done, took {nice_timedelta(datetime.now(UTC), start)}")

        channels_to_download = []
        total_missing = 0
        total_offline = 0

        for channel, missing_videos in results:
            missing_count = len(missing_videos)
            archived_count = len(channel.videos_on_disk)
            total_count = archived_count + missing_count
            offline_count = len(channel.offline_videos)

            s = f"\t{channel.get_name()} - {missing_count:,} missing / {archived_count:,} archived / {total_count:,} total / {offline_count:,} now offline"

            if offline_count:
                s += f" | {offline_count:,}: [{", ".join(channel.offline_videos)}]"

            if missing_videos:
                channels_to_download.append(channel)

            total_missing += missing_count
            total_offline += offline_count
            await logger.debug(s)

        await logger.info(
            f"system - {total_missing:,} videos missing across {len(channels_to_download):,}/{total_channels:,} channels, {total_offline:,} are offline")
        self.total_missing = total_missing
        self.channels_with_missing = len(channels_to_download)
        return channels_to_download

    async def _download_all(self, channels: list[Channel]) -> None:
        start = datetime.now(UTC)
        total = len(channels)

        for i, channel in enumerate(channels):
            await channel.archive(i+1, total)
            self.total_archived += channel.archived_this_time
            self.archived_data += channel.size_downloaded
            if i < total - 1:
                await asyncio.sleep(STEP_SLEEP_INTERVAL)

        await logger.info(f"system - downloading {total:,} channels took {nice_timedelta(datetime.now(UTC), start)}")
        await logger.info(f"system - downloaded {self.total_archived} videos, size: +{format_si(self.archived_data)}")

    # -------------------------------------------------------------------------
    # Helpers
    # -------------------------------------------------------------------------

    @staticmethod
    async def _fetch_channel_metadata(channel: Channel, channel_number: int, total_channels: int) -> tuple[Channel, list]:
        start = datetime.now(UTC)
        videos_to_download = await channel.get_metadata(channel_number, total_channels)
        msg = f"\t[{channel_number+1}/{total_channels}] {channel.get_name()} - metadata fetched in {nice_timedelta(datetime.now(UTC), start)}"

        if STEP_SLEEP_INTERVAL > 0:
            msg += f", sleeping {STEP_SLEEP_INTERVAL:,} seconds..."

        await logger.info(msg)
        await asyncio.sleep(STEP_SLEEP_INTERVAL)
        return channel, videos_to_download

    async def _write_run_report(self, started_at: datetime, finished_at: datetime, elapsed) -> None:
        report_path = self._run_report_path(finished_at)
        if report_path is None:
            return

        report = {
            "started_at": started_at.isoformat(),
            "finished_at": finished_at.isoformat(),
            "elapsed_seconds": elapsed.total_seconds(),
            "channels_scanned": len(self.channels),
            "channels_with_missing": self.channels_with_missing,
            "channels_skipped": len(self.channels) - self.channels_with_missing,
            "files_on_disk": self.total_files,
            "partial_files_deleted": self.total_deleted,
            "videos_missing": self.total_missing,
            "videos_downloaded": self.total_archived,
            "videos_failed": max(self.total_missing - self.total_archived, 0),
            "download_failures": max(self.total_missing - self.total_archived, 0),
            "bytes_before": self.bytes_before,
            "bytes_before_human": format_si(self.bytes_before),
            "bytes_added": self.archived_data,
            "bytes_added_human": format_si(self.archived_data),
            "bytes_after": self.bytes_before + self.archived_data,
            "bytes_after_human": format_si(self.bytes_before + self.archived_data),
            "channels": [channel.run_report() for channel in self.channels],
        }

        try:
            report_path.parent.mkdir(parents=True, exist_ok=True)
            with report_path.open("w", encoding="utf-8") as file:
                json.dump(report, file, indent=4, sort_keys=True)
            await logger.info(f"system - wrote run report to {report_path}")
        except OSError as exc:
            await logger.warning(f"system - failed to write run report to {report_path}: {exc}")

    @staticmethod
    def _run_report_path(finished_at: datetime) -> Path | None:
        log_path = os.getenv("LOG_PATH", "/logs").strip()
        if not log_path:
            return None
        timestamp = finished_at.astimezone(UTC).strftime("%Y-%m-%d_%H-%M-%S_%fZ")
        return Path(log_path) / f"{timestamp}.json"
