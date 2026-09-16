import logging
import re

from yt_dlp import YoutubeDL


CHANNEL_IDS = [
    "UCS9FEwX4IWaxcHR4Q5DCMDA",
    "UCQVFsceiJZ3bs-SzE3YXCnw",
    "UC1QxOK5YpyAyFCN_xiPfgHw"
]
MAX_VIDEOS = 15
logger = logging.getLogger(__name__)


def check_youtube(channel_id):
    logger.info("Checking YouTube channel: %s", channel_id)
    channel_id = channel_id.strip()
    if not re.fullmatch(r"UC[A-Za-z0-9_-]{22}", channel_id):
        raise ValueError(f"Invalid YouTube channel ID: {channel_id}")
    # A channel's UU playlist contains its uploads, including Shorts.
    playlist_url = f"https://www.youtube.com/playlist?list=UU{channel_id[2:]}"
    options = {
        "extract_flat": "in_playlist",
        "skip_download": True,
        "playlistend": MAX_VIDEOS,
        "socket_timeout": 30,
        "retries": 3,
        "extractor_retries": 3,
        "ignoreerrors": False,
        "quiet": True,
        "logger": logger,
    }
    with YoutubeDL(options) as ydl:
        info = ydl.extract_info(playlist_url, download=False)
    if not info or "entries" not in info:
        raise ValueError("Failed to fetch YouTube uploads")

    videos = []
    for entry in info["entries"]:
        if not entry:
            continue
        video_id = entry.get("id") or ""
        channel_name = (
            entry.get("channel") or entry.get("uploader")
            or info.get("channel") or info.get("uploader") or ""
        ).strip()
        if not re.fullmatch(r"[A-Za-z0-9_-]{11}", video_id) or not channel_name:
            raise ValueError("YouTube upload is missing a video ID or channel name")
        url = f"https://www.youtube.com/watch?v={video_id}"
        videos.append({"url": url, "msg": f"{channel_name}更新啦！\n{url}"})
    # YouTube lists the newest entries first; deliver older updates first.
    return list(reversed(videos))
