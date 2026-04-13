import os
import zlib
import json
import time
import base64
import logging
import requests
from datetime import datetime
from zoneinfo import ZoneInfo
from urllib.parse import urlencode
from dotenv import load_dotenv
from http_utils import fetch_json

load_dotenv()

CF_BNALPHA_URL = os.getenv('CF_BNALPHA_URL')
CF_BNALPHA_KEY = os.getenv('CF_BNALPHA_KEY')
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36',
    'Accept': 'application/json, text/plain, */*',
    'Referer': 'https://foresightnews.pro/',
}
TIMEOUT = (3, 30)
logger = logging.getLogger(__name__)


def build_bnalpha_proxy_url(url):
    if not CF_BNALPHA_URL or not CF_BNALPHA_KEY:
        raise ValueError('Missing CF_BNALPHA_URL or CF_BNALPHA_KEY')
    return f"{CF_BNALPHA_URL}?{urlencode({'url': url})}"


def check_alpha(start_ts):
    logger.info("Checking alpha news...")
    url = build_bnalpha_proxy_url("https://api.foresightnews.pro/v2/feed?page=1&size=30")
    headers = HEADERS.copy()
    headers['CF-Alpha-Key'] = CF_BNALPHA_KEY
    response_data = fetch_json(
        requests.get,
        url=url,
        attempts=4,
        timeout=TIMEOUT,
        headers=headers,
        error_message='Failed to fetch alpha news',
    )
    encoded_data = response_data.get('data')
    if not encoded_data:
        raise ValueError('Failed to fetch alpha news: missing data')
    compressed_data = base64.b64decode(encoded_data)
    original_text = zlib.decompress(compressed_data).decode('utf-8')
    original_data = json.loads(original_text)
    all_feeds = original_data.get('list')
    if not isinstance(all_feeds, list):
        raise ValueError('Failed to fetch alpha news: invalid payload list')
    all_news = [each for each in all_feeds if each.get('source_type') == 'news']
    max_ts = start_ts
    news_msg = ''
    for each_news in all_news:
        news_ts = each_news.get('published_at')
        if not isinstance(news_ts, (int, float)):
            continue
        if news_ts > max_ts:
            max_ts = news_ts
        if news_ts > start_ts:
            news_time = datetime.fromtimestamp(news_ts, tz=ZoneInfo('Asia/Shanghai')).strftime("%Y-%m-%d %H:%M:%S")
            news = each_news.get('news') or {}
            news_id = each_news.get('source_id')
            if not news_id:
                continue
            news_title = str(news.get('title') or '')
            news_text = str(news.get('brief') or '')
            news_link = f'https://foresightnews.pro/news/detail/{news_id}'
            news_full_text = news_title + news_text
            if ("alpha" in news_full_text.lower()) or ("tge" in news_full_text.lower()):
                if ("binance" in news_full_text.lower()) or ("币安" in news_full_text):
                    news_msg = f"{news_time}\n{news_title}\n{news_text}\n原文链接：{news_link}\n" + news_msg
    news_res = {'ts': max_ts, 'msg': news_msg}
    return news_res
