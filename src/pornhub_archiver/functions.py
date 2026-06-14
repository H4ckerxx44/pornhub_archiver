from datetime import datetime, timedelta
from urllib.parse import parse_qs, urlparse

import humanize


def video_url_from_id(video_id: str) -> str:
    return f"https://www.pornhub.org/view_video.php?viewkey={video_id}"


def video_id_from_link(video_link: str) -> str:
    video_link = str(video_link).strip()
    if not video_link:
        raise ValueError("video link is empty")

    parsed = urlparse(video_link)
    query = parse_qs(parsed.query)
    for key in ("viewkey", "v", "id"):
        if query.get(key):
            return query[key][0]
    if query:
        return next(iter(query.values()))[0]

    if "=" in video_link:
        query = parse_qs(video_link.split("?", 1)[-1])
        for key in ("viewkey", "v", "id"):
            if query.get(key):
                return query[key][0]
        if query:
            return next(iter(query.values()))[0]
        return video_link.rsplit("=", 1)[-1].split("&", 1)[0]

    if "/" in video_link:
        return video_link.rstrip("/").rsplit("/", 1)[-1]

    return video_link


def nice_timedelta(x1: datetime, x2: datetime) -> timedelta:
    return x1 - x2


def format_si(size_bytes: int | float) -> str:
    """Format a byte count as a human-readable string (e.g. 1.23 GiB)."""
    return humanize.naturalsize(size_bytes, binary=True, format="%.2f")


def spacer(spacer_length: int = 25, spacer_char: str = "=") -> str:
    return spacer_char * spacer_length
