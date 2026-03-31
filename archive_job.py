import asyncio
import os
from datetime import datetime, UTC
from pathlib import Path

from channel import Channel

STEP_SLEEP_INTERVAL = int(os.getenv("STEP_SLEEP_INTERVAL", 15))


class ArchiveJob:
    def __init__(self, channels: list[Channel], root_path: Path):
        self.total_archived: int = 0
        self.channels = channels
        self.start = datetime.now(UTC)
        self.root_path = root_path

    # -------------------------------------------------------------------------
    # Public API
    # -------------------------------------------------------------------------

    async def archive_channel(self, channel_name: str) -> None:
        channel = self._find_channel(channel_name)
        if channel:
            await channel.archive(1, 1)

    async def archive_all(self) -> None:
        run_start = datetime.now(UTC)
        print(f"system - archiving {len(self.channels):,} channels")

        total_files = self._create_paths()
        print(f"system - found {total_files:,} files in total")

        total_deleted = self._cleanup_paths()
        print(f"system - deleted {total_deleted:,} files in cleanup")

        channels_to_download = await self._collect_channels_with_missing_videos()

        await self._download_all(channels_to_download)

        elapsed = datetime.now(UTC) - run_start
        print(f"system - total runtime: {elapsed}")
        print(f"system - total archived this run: {self.total_archived:,}")

    # -------------------------------------------------------------------------
    # Steps
    # -------------------------------------------------------------------------

    def _create_paths(self) -> int:
        start = datetime.now(UTC)
        total_files = 0

        for j, channel in enumerate(self.channels):
            step_start = datetime.now(UTC)
            file_count = channel.create_path()
            total_files += file_count
            elapsed = datetime.now(UTC) - step_start
            print(
                f"\t[{j+1}/{len(self.channels):,}] {channel.get_name()} — "
                f"{file_count:,} files (total: {total_files:,}), took: {elapsed}"
            )

        print(f"system - creating/checking paths took {datetime.now(UTC) - start}")
        return total_files

    def _cleanup_paths(self) -> int:
        start = datetime.now(UTC)
        total_deleted = 0

        for j, channel in enumerate(self.channels):
            step_start = datetime.now(UTC)
            deleted = channel.cleanup()
            total_deleted += deleted
            elapsed = datetime.now(UTC) - step_start
            print(
                f"\t[{j+1}/{len(self.channels):,}] {channel.get_name()} — "
                f"deleted {deleted:,} files, took: {elapsed}"
            )

        print(f"system - cleanup took {datetime.now(UTC) - start}")
        return total_deleted

    async def _collect_channels_with_missing_videos(self) -> list[Channel]:
        """Fetch metadata for all channels concurrently, then return those with missing videos."""
        start = datetime.now(UTC)
        total_channels = len(self.channels)

        print(f"system - fetching metadata for {total_channels:,} channels concurrently...")

        # tasks = [self._fetch_channel_metadata(channel) for channel in self.channels]
        # results: list[tuple[Channel, list]] = await asyncio.gather(*tasks)

        results: list[tuple[Channel, list]] = [await self._fetch_channel_metadata(channel) for channel in self.channels]

        print(f"system - metadata fetch done, took {datetime.now(UTC) - start}")

        channels_to_download = []
        total_missing = 0

        for channel, missing_videos in results:
            missing_count = len(missing_videos)
            archived_count = len(channel.videos_on_disk)
            total_count = archived_count + missing_count

            if missing_videos:
                print(
                    f"\t{channel.get_name()} — "
                    f"{missing_count:,} missing / {archived_count:,} archived / {total_count:,} total"
                )
                for p, video in enumerate(missing_videos):
                    print(f"\t\t[{p + 1:,}/{missing_count:,}] {video}")
                channels_to_download.append(channel)
            else:
                print(f"\t{channel.get_name()} — up to date ({archived_count:,} archived)")

            total_missing += missing_count

        print(
            f"system - {total_missing:,} videos missing across {len(channels_to_download):,}/{total_channels:,} channels")
        return channels_to_download

    async def _download_all(self, channels: list[Channel]) -> None:
        start = datetime.now(UTC)
        total = len(channels)

        for k, channel in enumerate(channels):
            await channel.archive(k+1, total)
            self.total_archived += channel.archived_this_time
            if k < total - 1:
                await asyncio.sleep(STEP_SLEEP_INTERVAL)

        print(f"system - downloading {total:,} channels took {datetime.now(UTC) - start}")

    # -------------------------------------------------------------------------
    # Helpers
    # -------------------------------------------------------------------------

    def _find_channel(self, name: str) -> Channel | None:
        return next((c for c in self.channels if c.get_name() == name), None)

    @staticmethod
    async def _fetch_channel_metadata(channel: Channel) -> tuple[Channel, list]:
        start = datetime.now(UTC)
        print(f"\t{channel.get_name()} — fetching metadata...")

        videos_to_download = await channel.get_metadata()

        elapsed = datetime.now(UTC) - start
        print(f"\t{channel.get_name()} — metadata fetched in {elapsed}, sleeping {STEP_SLEEP_INTERVAL:,}s...")

        await asyncio.sleep(STEP_SLEEP_INTERVAL)
        return channel, videos_to_download
