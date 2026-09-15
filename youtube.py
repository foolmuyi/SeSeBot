import logging
import xml.etree.ElementTree as ET

import requests

from http_utils import fetch_response


CHANNEL_IDS = [
    # "UCS9FEwX4IWaxcHR4Q5DCMDA",
]
RSS_URL = "https://www.youtube.com/feeds/videos.xml"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
    "Accept": "application/atom+xml",
}
TIMEOUT = (3, 30)
ATOM = {"atom": "http://www.w3.org/2005/Atom"}
logger = logging.getLogger(__name__)


def check_youtube(channel_id):
    logger.info("Checking YouTube channel: %s", channel_id)
    response = fetch_response(
        requests.get,
        url=RSS_URL,
        params={"channel_id": channel_id},
        attempts=4,
        timeout=TIMEOUT,
        headers=HEADERS,
        error_message="Failed to fetch YouTube feed",
    )
    try:
        root = ET.fromstring(response.content)
    except ET.ParseError as exc:
        raise ValueError("Failed to fetch YouTube feed: invalid XML response") from exc
    if root.tag != "{http://www.w3.org/2005/Atom}feed":
        raise ValueError("Failed to fetch YouTube feed: expected an Atom feed")

    videos = []
    for entry in root.findall("atom:entry", ATOM):
        channel_name = entry.findtext("atom:author/atom:name", default="", namespaces=ATOM).strip()
        for link in entry.findall("atom:link", ATOM):
            if link.get("rel", "alternate") != "alternate":
                continue
            url = (link.get("href") or "").strip()
            if channel_name and url:
                videos.append({"url": url, "msg": f"{channel_name}更新啦！\n{url}"})
                break
    # YouTube lists the newest entries first; deliver older updates first.
    return list(reversed(videos))
