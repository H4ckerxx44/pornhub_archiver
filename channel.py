from datetime import datetime, UTC

from yt_dlp import YoutubeDL

import db
from pathlib import Path

from functions import video_url_from_id, video_id_from_link, nice_timedelta


class Channel:
    def __init__(self, db_id: int, link: str, total_videos: int, archived_videos: int, added_on: datetime, last_queried_at: datetime, root_path: Path):
        self.archived_this_time: int = 0
        self.missing_videos = []
        self.db_id: int = db_id
        self.link: str = link
        self.total_videos: int = total_videos
        self.archived_videos: int = archived_videos
        self.name: str = self.link.split('/')[-1]
        self.added_on: datetime = added_on
        self.last_queried_at: datetime = last_queried_at
        self.root_path: Path = root_path
        self.channel_path: Path = self.root_path / self.name
        self.videos_on_disk: dict[str, bool] = {}
        self.error_count: int = 0
        self.yt_dlp_options = {
            "quiet": True,
            "noprogress": True,
            # "verbose": True,
            "no_warnings": True,
            "extract_flat": True,
            "outtmpl": f"{self.channel_path}/[%(id)s] %(title)s.%(ext)s",
            "restrictfilenames": True,
            "concurrent_fragment_downloads": 1,
            # "source_address": "0.0.0.0",
            # "debug_printtraffic": False,
            "nocheckcertificate": True,
            "retries": 5,
            "fragment_retries": 10,
            "socket_timeout": 30,
            "writethumbnail": True,
            'postprocessors': [
                {
                    "key": "FFmpegMetadata",
                    "add_chapters": True,
                    "add_metadata": True,
                    "add_infojson": "if_exists"
                },
                {
                    "key": "EmbedThumbnail",
                    "already_have_thumbnail": False
                }
            ]
        }

    def get_name(self):
        return self.name

    def get_channel_path(self):
        return self.channel_path

    async def update_channel(self) -> None:
        await db.execute_query('update channels set last_queried_at=%s where link=%s', (datetime.now(UTC), self.link))

    async def set_total_videos(self, videos: int) -> None:
        self.total_videos = videos
        await db.execute_query('update channels set total_videos=%s where link=%s', (videos, self.link))

    async def increment_archived_videos(self) -> None:
        self.archived_videos += 1
        self.archived_this_time += 1
        await db.execute_query('update channels set archived_videos=archived_videos+1 where link=%s', (self.link))

    @staticmethod
    async def get_all_channels(root_path: Path) -> list["Channel"]:
        channels = await db.execute_query('select id, link, added_on, last_queried_at, total_videos, archived_videos from channels where is_active=1 order by link')
        all_channels = []
        for channel in channels:
            db_id: int = channel[0]
            link: str = channel[1]
            added_on: datetime = channel[2]
            total_videos: int = channel[3]
            archived_videos: int = channel[4]
            last_queried_at: datetime = channel[5]
            if link.endswith("/videos"):
                link = link[: -len("/videos")]
                print(f"WRONG PATH FORMAT - {link} ends with /videos")
            elif link.endswith("/videos/"):
                link = link[: -len("/videos/")]
                print(f"WRONG PATH FORMAT - {link} ends with /videos/")
            elif link.endswith("/"):
                link = link[:-len("/")]
                print(f"WRONG PATH FORMAT - {link} ends with /")
            all_channels.append(Channel(db_id, link, total_videos, archived_videos, added_on, last_queried_at, root_path))
        return all_channels

    async def archive(self, current_channel_number: int, total_channels: int) -> None:
        # scan for existing videos
        channel_start = datetime.now(UTC)
        self.archived_this_time = 0
        missing_vids_of_channel = len(self.missing_videos)
        errors = 0

        for i, video_id in enumerate(self.missing_videos):
            with YoutubeDL(self.yt_dlp_options) as yt:
                url = video_url_from_id(video_id)
                download_start = datetime.now(UTC)
                try:
                    yt.download(url)
                    video_time_taken = nice_timedelta(datetime.now(UTC), download_start)
                    video_perc = ((i+1)/missing_vids_of_channel)*100
                    channel_progress_string = f"{i+1}/{missing_vids_of_channel:,} ({video_perc:,.4f} %)"

                    channel_perc = (current_channel_number/total_channels)*100
                    total_progress_string = f"{current_channel_number:,}/{total_channels:,} ({channel_perc:,.4f} %)"
                    print(f"\t\tvideo - {self.get_name()} ({total_progress_string}) - download {video_id} ({channel_progress_string}) took {video_time_taken} (channel: {nice_timedelta(datetime.now(UTC), channel_start)} so far)")
                    await self.increment_archived_videos()
                except Exception as e:
                    # print(f"\tchannel - {e}")
                    errors += 1
        x1 = datetime.now(UTC)
        channel_time_taken = nice_timedelta(x1, channel_start)
        print(f"\tchannel - {self.get_name()} ({current_channel_number:,}/{total_channels:,}) - channel took {channel_time_taken} | archived this run: {self.archived_this_time:,} | errors: {errors:,}")

    def get_already_downloaded_videos(self):
        for file in Path(self.get_channel_path()).iterdir():
            if file.is_file():
                video_id = file.name
                video_id = video_id.split(" ")[0]
                video_id = video_id.replace("[", "")
                video_id = video_id.replace("]", "")
                self.videos_on_disk[video_id] = True
        return self.videos_on_disk

    async def get_missing_videos(self) -> list[str]:
        already_downloaded_videos = self.get_already_downloaded_videos()
        await self.set_archived_video_count()

        with YoutubeDL(self.yt_dlp_options) as yt:
            error_encountered = False
            try:
                info = yt.extract_info(f"{self.link}/videos", download=False)
                await self.update_channel()
            except Exception:
                self.error_count += 1
                print(f"\tchannel - {self.get_name()} - encountered error {self.error_count:,}")
                info = {"entries": []}
                error_encountered = True
        all_videos_on_channel = [video_id_from_link(entry["url"]) for entry in info["entries"]]
        if not error_encountered:
            await self.set_total_videos(len(all_videos_on_channel))

        # print(f"{self.get_name()} - all videos ({len(all_videos_on_channel):,}): {all_videos_on_channel}")
        # print(f"{self.get_name()} - present on disk ({len(already_downloaded_videos):,}): {already_downloaded_videos}")
        missing_videos = []
        for video in all_videos_on_channel:
            if video not in already_downloaded_videos.keys():
                missing_videos.append(video)
        # print(f"{self.get_name()} - missing videos ({len(missing_videos):,}): {missing_videos}")
        self.missing_videos = missing_videos

        return missing_videos

    def create_path(self):
        file_amount = 0
        if not self.get_channel_path().exists():
            self.channel_path.mkdir(parents=True, exist_ok=True)
            # print(f"{self.get_name()} - created path {self.get_channel_path()}")
        else:
            files = [x for x in self.get_channel_path().iterdir() if x.is_file()]
            file_amount = len(files)
            # print(f"{self.get_name()} - path already exists, contains {file_amount:,} files")
        return file_amount

    def cleanup(self):
        files_deleted = 0
        for file in self.channel_path.iterdir():
            if file.is_file():
                if ".part-Frag" in file.name or file.name.endswith(".part"):
                    # print(f"\t\t{self.get_name()} - deleting {file.name}")
                    file.unlink()
                    files_deleted += 1
        # print(f"{self.get_name()} - {files_deleted:,} files deleted")
        return files_deleted

    async def get_metadata(self):
        return await self.get_missing_videos()

    async def set_archived_video_count(self):
        archived_video_count = len(self.videos_on_disk)
        await db.execute_query('update channels set archived_videos=%s where link=%s', (archived_video_count, self.link))
