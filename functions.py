from datetime import datetime, timedelta


def video_url_from_id(video_id: str) -> str:
    return f"https://www.pornhub.org/view_video.php?viewkey={video_id}"

def video_id_from_link(video_link: str) -> str:
    split_link, video_id = video_link.split("=")
    return video_id

def nice_timedelta(x1: datetime, x2: datetime) -> timedelta:
    return x1 - x2
