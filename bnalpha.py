import requests
import base64
import zlib
import json
import time
from datetime import datetime
from zoneinfo import ZoneInfo


def check_alpha():
    url = 'https://api.foresightnews.pro/v1/event/250?page=1&size=20&sort_by=desc'
    res = requests.get(url=url)
    encoded_data = json.loads(res.text)['data']
    compressed_data = base64.b64decode(encoded_data)
    original_text = zlib.decompress(compressed_data).decode('utf-8')
    original_data = json.loads(original_text)
    all_news = original_data['items']
    news_msg = ''
    for each_news in all_news:
        news_ts = each_news['published_at']
        if (time.time() - news_ts) < (11 * 60):
            news_time = datetime.fromtimestamp(news_ts, tz=ZoneInfo('Asia/Shanghai')).strftime("%Y-%m-%d %H:%M:%S")
            news = each_news['news']
            news_title = news['title']
            new_content = news['content']
            news_msg += f"{news_time}\n{news_title}\n{new_content}\n"
    if news_msg:
        return news_msg
    else:
        return None