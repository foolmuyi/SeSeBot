import html
import logging
import re
import requests
import xml.etree.ElementTree as ET
from email.utils import parsedate_to_datetime
from zoneinfo import ZoneInfo
from http_utils import fetch_response

PANEWS_RSS_URL = "https://www.panewslab.com/rss.xml?lang=zh&type=NEWS"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
    "Accept": "application/rss+xml, application/xml, text/xml, */*",
}
TIMEOUT = (3, 30)
TIMEZONE = ZoneInfo("Asia/Shanghai")
logger = logging.getLogger(__name__)


def clean_text(raw_text):
    text = html.unescape(str(raw_text or ""))
    text = re.sub(r"<[^>]+>", "", text)
    return " ".join(text.split()).strip()


def item_text(item, tag_name):
    node = item.find(tag_name)
    return clean_text(node.text if node is not None else "")


def parse_pub_time(raw_text):
    parsed_dt = parsedate_to_datetime(str(raw_text or "").strip())
    if parsed_dt.tzinfo is None:
        parsed_dt = parsed_dt.replace(tzinfo=TIMEZONE)
    return parsed_dt.astimezone(TIMEZONE)


def check_alpha(start_ts):
    logger.info("Checking alpha news...")
    response = fetch_response(
        requests.get,
        url=PANEWS_RSS_URL,
        attempts=4,
        timeout=TIMEOUT,
        headers=HEADERS,
        error_message="Failed to fetch alpha news",
    )

    try:
        root = ET.fromstring(response.text)
    except ET.ParseError as exc:
        raise ValueError("Failed to fetch alpha news: invalid RSS response") from exc

    max_ts = start_ts
    news_msg = ""
    for item in root.findall(".//item"):
        try:
            published_dt = parse_pub_time(item_text(item, "pubDate"))
        except (TypeError, ValueError):
            continue

        news_ts = published_dt.timestamp()
        if news_ts > max_ts:
            max_ts = news_ts
        if news_ts <= start_ts:
            continue

        title = item_text(item, "title")
        brief = item_text(item, "description")
        link = item_text(item, "link")
        full_text = f"{title}{brief}"
        full_text_lower = full_text.lower()
        if not ("alpha" in full_text_lower or "tge" in full_text_lower or "空投" in full_text):
            continue
        if not ("binance" in full_text_lower or "币安" in full_text):
            continue

        news_time = published_dt.strftime("%Y-%m-%d %H:%M:%S")
        news_msg = f"{news_time}\n{title}\n{brief}\n原文链接：{link}\n" + news_msg

    return {"ts": max_ts, "msg": news_msg}
