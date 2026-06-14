import os
import re
from datetime import datetime, UTC
from pathlib import Path

from yt_dlp import YoutubeDL

from . import db
from .logger import logger
from .functions import video_url_from_id, video_id_from_link, nice_timedelta, format_si, spacer

_LINK_SUFFIXES = ("/videos/", "/videos", "/")
_VIDEO_FILENAME_RE = re.compile(r"^\[(?P<video_id>[^\]]+)]")

MAX_ERRORS = 5
CONCURRENT_FRAGMENT_DOWNLOADS = int(os.getenv("CONCURRENT_FRAGMENT_DOWNLOADS", 4))

if CONCURRENT_FRAGMENT_DOWNLOADS < 1:
    raise ValueError("CONCURRENT_FRAGMENT_DOWNLOADS must be >= 1")


class Channel:
    def __init__(
            self,
            db_id: int,
            link: str,
            total_videos: int,
            archived_videos: int,
            added_on: datetime,
            last_queried_at: datetime,
            data_path: Path,
    ):
        self.db_id = db_id
        self.link = link
        self.total_videos = total_videos
        self.archived_videos = archived_videos
        self.added_on = added_on
        self.last_queried_at = last_queried_at
        self.data_path = data_path
        self.name = link.split("/")[-1]
        self.channel_path = data_path / self.name
        self.videos_on_disk: dict[str, bool] = {}
        self.missing_videos: list[str] = []
        self.offline_videos: list[str] = []
        self.archived_this_time: int = 0
        self.error_count: int = 0
        self.size_before: int = 0  # total channel bytes on disk before this run
        self.size_downloaded: int = 0  # bytes added during this run
        self.metadata_yt_dlp_options = self._build_metadata_yt_dlp_options()
        self.download_yt_dlp_options = self._build_download_yt_dlp_options()

    # -------------------------------------------------------------------------
    # Public API
    # -------------------------------------------------------------------------

    def get_name(self) -> str:
        return self.name

    def get_channel_path(self) -> Path:
        return self.channel_path

    def run_report(self) -> dict:
        return {
            "name": self.get_name(),
            "archived_on_disk": len(self.videos_on_disk),
            "missing": len(self.missing_videos),
            "offline": len(self.offline_videos),
            "downloaded_this_run": self.archived_this_time,
            "bytes_added": self.size_downloaded,
            "bytes_added_human": format_si(self.size_downloaded),
        }

    def create_path(self) -> int:
        """Ensure channel directory exists. Returns number of existing files."""
        if not self.channel_path.exists():
            self.channel_path.mkdir(parents=True, exist_ok=True)
            return 0
        return sum(1 for f in self.channel_path.iterdir() if f.is_file())

    def cleanup(self) -> int:
        """Delete incomplete download fragments. Returns number of deleted files."""
        deleted = 0
        for file in self.channel_path.iterdir():
            if file.is_file() and self._is_partial(file):
                file.unlink()
                deleted += 1
        return deleted

    async def get_metadata(self, channel_number: int, total_channels: int) -> list[str]:
        return await self._fetch_missing_videos(channel_number, total_channels)

    async def archive(self, current_channel_number: int, total_channels: int) -> None:
        channel_start = datetime.now(UTC)
        self.archived_this_time = 0
        self.size_before = self._channel_size_on_disk()
        self.size_downloaded = 0
        errors = 0
        total = len(self.missing_videos)
        channel_pct = (current_channel_number / total_channels) * 100

        await logger.info(
            f"\tchannel - {self.name} ({current_channel_number:,}/{total_channels:,} | {channel_pct:,.2f}%) - "
            f"{total:,} video(s) to archive (existing: {format_si(self.size_before)}) | missing videos: [{", ".join(self.missing_videos)}]"
        )

        for i, video_id in enumerate(self.missing_videos):
            success = await self._download_video(
                video_id, i, total, channel_start
            )
            if not success:
                await logger.error(f"\t\tvideo {video_url_from_id(video_id)} errored")
                errors += 1

        total_size_after = self.size_before + self.size_downloaded
        elapsed = nice_timedelta(datetime.now(UTC), channel_start)

        await logger.info(f"\t\t{spacer()} RESULT {spacer()}")
        await logger.info(f"\t\tdownloaded {format_si(self.size_downloaded)} this run")
        await logger.info(f"\t\ttotal on disk: {format_si(total_size_after)} (was {format_si(self.size_before)} + {format_si(self.size_downloaded)} => {format_si(total_size_after)}")
        await logger.info(f"\t\ttook {elapsed} | archived: {self.archived_this_time:,} | errors: {errors:,}")
        await logger.info(f"\t\taverage download speed: {(self.size_downloaded / elapsed.total_seconds())/1024/1024:,.4f} MiB/s")

    # -------------------------------------------------------------------------
    # Class methods
    # -------------------------------------------------------------------------

    @classmethod
    async def get_all_channels(cls, data_path: Path) -> list["Channel"]:
        rows = await db.execute_query(
            "select id, link, added_on, last_queried_at, total_videos, archived_videos "
            "from channels where is_active=1 order by link"
        )
        return [await cls._from_row(row, data_path) for row in rows]

    # -------------------------------------------------------------------------
    # DB helpers
    # -------------------------------------------------------------------------

    async def _update_last_queried(self) -> None:
        await db.execute_query(
            "update channels set last_queried_at=%s where link=%s",
            (datetime.now(UTC), self.link),
        )

    async def _set_total_videos(self, count: int) -> None:
        self.total_videos = count
        await db.execute_query(
            "update channels set total_videos=%s where link=%s",
            (count, self.link),
        )

    async def _set_archived_video_count(self) -> None:
        await db.execute_query(
            "update channels set archived_videos=%s where link=%s",
            (len(self.videos_on_disk), self.link),
        )

    async def _increment_archived_videos(self) -> None:
        self.archived_videos += 1
        self.archived_this_time += 1
        await db.execute_query(
            "update channels set archived_videos=archived_videos+1 where link=%s",
            (self.link,),
        )

    # -------------------------------------------------------------------------
    # Download logic
    # -------------------------------------------------------------------------

    async def _download_video(
            self,
            video_id: str,
            index: int,
            total: int,
            channel_start: datetime,
    ) -> bool:
        url = video_url_from_id(video_id)
        download_start = datetime.now(UTC)

        try:
            with YoutubeDL(self.download_yt_dlp_options) as yt:
                yt.download(url)

            video_size = self._video_size_on_disk(video_id)
            self.size_downloaded += video_size

            video_elapsed = nice_timedelta(datetime.now(UTC), download_start)
            channel_elapsed = nice_timedelta(datetime.now(UTC), channel_start)
            video_pct = ((index + 1) / total) * 100

            await logger.info(
                f"\t\tvideo {video_id} ({index + 1:,}/{total:,} | {video_pct:,.2f}%)"
                f", took {video_elapsed} (channel: {channel_elapsed} so far)"
                f", size: {format_si(video_size)} (+{format_si(self.size_downloaded)} so far)"
            )
            await self._increment_archived_videos()
            return True

        except Exception:
            self.error_count += 1
            return False

    # -------------------------------------------------------------------------
    # Metadata / disk scanning
    # -------------------------------------------------------------------------

    async def _fetch_missing_videos(self, channel_number: int, total_channels: int) -> list[str]:
        self._scan_disk()
        await self._set_archived_video_count()

        channel_videos, error = await self._fetch_channel_video_ids(channel_number, total_channels)

        if not error:
            await self._update_last_queried()
            await self._set_total_videos(len(channel_videos))

        channel_video_set = set(channel_videos)
        self.offline_videos = [v for v in self.videos_on_disk if v not in channel_video_set]
        self.missing_videos = [v for v in channel_videos if v not in self.videos_on_disk]
        return self.missing_videos

    async def _fetch_channel_video_ids(self, current_channel_number: int, total_channels: int) -> tuple[list[str], bool]:
        with YoutubeDL(self.metadata_yt_dlp_options) as yt:
            while self.error_count < MAX_ERRORS:
                try:
                    info = yt.extract_info(f"{self.link}/videos", download=False)
                    return [video_id_from_link(e["url"]) for e in info["entries"]], False
                except Exception:
                        self.error_count += 1
                        await logger.warning(f"\t[{current_channel_number+1}/{total_channels}] {self.name} - {self.error_count:,} errors fetching video list")
            return [], True

    def _scan_disk(self) -> None:
        """Populate `videos_on_disk` from files currently on disk."""
        self.videos_on_disk = {}
        for file in self.channel_path.iterdir():
            if not file.is_file():
                continue

            match = _VIDEO_FILENAME_RE.match(file.name)
            if match is None:
                continue

            self.videos_on_disk[match.group("video_id")] = True

    # -------------------------------------------------------------------------
    # Size helpers
    # -------------------------------------------------------------------------

    def _channel_size_on_disk(self) -> int:
        """Return total bytes of all files in the channel directory."""
        if not self.channel_path.exists():
            return 0
        return sum(
            f.stat().st_size
            for f in self.channel_path.iterdir()
            if f.is_file()
        )

    def get_channel_size(self) -> int:
        return self._channel_size_on_disk()

    def _video_size_on_disk(self, video_id: str) -> int:
        """Return total bytes of all files on disk that belong to this video_id.

        A single video can produce multiple files (video, thumbnail, .info.json, etc.)
        so we sum everything whose filename starts with `[<video_id>]`.
        """
        if not self.channel_path.exists():
            return 0
        prefix = f"[{video_id}]"
        return sum(
            f.stat().st_size
            for f in self.channel_path.iterdir()
            if f.is_file() and f.name.startswith(prefix)
        )

    # -------------------------------------------------------------------------
    # Private helpers
    # -------------------------------------------------------------------------

    @staticmethod
    def _build_common_yt_dlp_options() -> dict:
        return {
            "quiet": True,
            "noprogress": True,
            "no_warnings": True,
            "logtostderr": False,
            "nocheckcertificate": True,
            "retries": 5,
            "socket_timeout": 30,
        }

    def _build_metadata_yt_dlp_options(self) -> dict:
        return self._build_common_yt_dlp_options() | {
            "extract_flat": True,
        }

    def _build_download_yt_dlp_options(self) -> dict:
        return self._build_common_yt_dlp_options() | {
            "outtmpl": f"{self.channel_path}/[%(id)s] %(title)s.%(ext)s",
            "restrictfilenames": True,
            "concurrent_fragment_downloads": CONCURRENT_FRAGMENT_DOWNLOADS,
            "fragment_retries": 10,
            "writethumbnail": True,
            "postprocessors": [
                {"key": "FFmpegMetadata", "add_chapters": True, "add_metadata": True, "add_infojson": "if_exists"},
                {"key": "EmbedThumbnail", "already_have_thumbnail": False},
            ],
        }

    @staticmethod
    def _is_partial(file: Path) -> bool:
        return file.suffix == ".part" or ".part-Frag" in file.name

    @classmethod
    async def _from_row(cls, row: tuple, data_path: Path) -> "Channel":
        db_id, link, added_on, last_queried_at, total_videos, archived_videos = row
        link = await cls._normalize_link(link)
        return cls(db_id, link, total_videos, archived_videos, added_on, last_queried_at, data_path)

    @staticmethod
    async def _normalize_link(link: str) -> str:
        for suffix in _LINK_SUFFIXES:
            if link.endswith(suffix):
                await logger.warning(f"WRONG PATH FORMAT - {link} ends with '{suffix}'")
                return link[: -len(suffix)]
        return link
