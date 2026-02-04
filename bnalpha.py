import zlib
import json
import time
import base64
import requests
from datetime import datetime
from zoneinfo import ZoneInfo


def check_alpha(start_ts):
    print('Checking alpha news...')
    url = "https://api.foresightnews.pro/v2/feed?page=1&size=30"
    response = requests.get(url=url)
    encoded_data = json.loads(response.text)['data']
    compressed_data = base64.b64decode(encoded_data)
    original_text = zlib.decompress(compressed_data).decode('utf-8')
    original_data = json.loads(original_text)
    all_feeds = original_data['list']
    all_news = [each for each in all_feeds if each['source_type'] == 'news']
    max_ts = start_ts
    news_msg = ''
    for each_news in all_news:
        news_ts = each_news['published_at']
        if news_ts > max_ts:
            max_ts = news_ts
        if news_ts > start_ts:
            news_time = datetime.fromtimestamp(news_ts, tz=ZoneInfo('Asia/Shanghai')).strftime("%Y-%m-%d %H:%M:%S")
            news = each_news['news']
            news_id = each_news['source_id']
            news_title = news['title']
            news_text = news['brief']
            news_link = f'https://foresightnews.pro/news/detail/{news_id}'
            if ("alpha" in news_text.lower()) or ("tge" in news_text.lower()):
                if ("binance" in news_text.lower()) or ("币安" in news_text):
                    news_msg = f"{news_time}\n{news_title}\n{news_text}\n原文链接：{news_link}\n" + news_msg
    news_res = {'ts': max_ts, 'msg': news_msg}
    return news_res