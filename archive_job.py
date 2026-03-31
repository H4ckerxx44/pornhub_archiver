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

    async def archive_channel(self, channel_name: str):
        for channel in self.channels:
            if channel.get_name() == channel_name:
                await channel.archive(1, 1)

    async def archive_all(self):
        print(f"system - archiving all channels ({len(self.channels):,} channels)")

        start_create_paths = datetime.now(UTC)
        self.total_archived = 0
        total_files = 0
        for j, channel in enumerate(self.channels):
            start_create_path = datetime.now(UTC)
            file_amount = channel.create_path()
            finish_create_path = datetime.now(UTC)
            total_files += file_amount
            print(f"\tchannel ({j+1}/{len(self.channels):,}) - {channel.get_name()} contains {file_amount:,} files (total: {total_files:,}), took: {finish_create_path - start_create_path}")
        print(f"system - found {total_files:,} files in total")

        finish_create_paths = datetime.now(UTC)
        print(f"system - creating/checking paths took {finish_create_paths - start_create_paths}")

        total_deleted = 0
        start_cleanup_paths = datetime.now(UTC)
        for j, channel in enumerate(self.channels):
            start_cleanup_path = datetime.now(UTC)
            deleted = channel.cleanup()
            finish_cleanup_path = datetime.now(UTC)
            print(f"\tchannel {channel.get_name()} ({j+1}/{len(self.channels):,}) - deleted {deleted:,} files, took: {finish_cleanup_path - start_cleanup_path}")
            total_deleted += deleted

        finish_cleanup_paths = datetime.now(UTC)
        print(f"system - cleaning up temp files took {finish_cleanup_paths - start_cleanup_paths}")
        print(f"system - deleted {total_deleted:,} files")

        total_vids_missing = 0
        start_get_metadata = datetime.now(UTC)
        channels_to_download_from = []
        for j, channel in enumerate(self.channels):
            start_channel_get_metadata = datetime.now(UTC)
            videos_to_download = await channel.get_metadata()
            videos_to_download_count = len(videos_to_download)
            finish_channel_get_metadata = datetime.now(UTC)
            print(f"\tchannel {channel.get_name()} ({j+1}/{len(self.channels):,}) - getting metadata: {finish_channel_get_metadata - start_channel_get_metadata}")
            for p, video in enumerate(videos_to_download):
                print(
                    f"\t\tvideo {video} - video {p + 1:,} of {videos_to_download_count:,} videos missing, {len(channel.videos_on_disk.items()) :,} already archived")
            total_vids_missing += videos_to_download_count
            if videos_to_download_count > 0:
                channels_to_download_from.append(channel)
            # print(f"system - now sleeping {STEP_SLEEP_INTERVAL:,} seconds...")
            await asyncio.sleep(STEP_SLEEP_INTERVAL)
            # print(f"system - sleeping done, continuing with {channel.get_name()}")

        finish_get_metadata = datetime.now(UTC)
        print(f"system - getting metadata, took: {finish_get_metadata - start_get_metadata}")
        print(f"system - {total_vids_missing:,} videos missing")

        start_archive_channel = datetime.now(UTC)
        for k, channel in enumerate(channels_to_download_from):
            await channel.archive(k, len(channels_to_download_from))
            self.total_archived += channel.archived_this_time
            await asyncio.sleep(STEP_SLEEP_INTERVAL)
        finish_archive_channel = datetime.now(UTC)
        print(f"system - downloading all {len(self.channels):,} channels, took: {finish_archive_channel - start_archive_channel}")
        print(f"system - total runtime: {finish_archive_channel - start_create_paths}")
        print(f"system - total archived this run: {self.total_archived:,}")
