import time
import requests
from xml.etree import ElementTree as ET
from email.utils import parsedate_to_datetime
from datetime import datetime
from zoneinfo import ZoneInfo
from bs4 import BeautifulSoup


def check_alpha(start_ts):
    print('Checking alpha news...')
    url = "https://www.techflowpost.com/api/client/common/rss.xml"
    response = requests.get(url)
    xml_data = response.content

    root = ET.fromstring(xml_data)
    max_ts = 0
    news_msg = ''
    for item in root.findall(".//item"):
        pub_date = item.find('pubDate').text
        pub_ts = parsedate_to_datetime(pub_date).timestamp()
        if pub_ts > max_ts:
            max_ts = pub_ts
        if pub_ts > start_ts:
            news = item.find('description').text
            news_text = BeautifulSoup(news, 'html.parser').get_text()
            if ("alpha" in news_text.lower()) or ("tge" in news_text.lower()):
                if ("binance" in news_text.lower()) or ("币安" in news_text):
                    local_pub_date = datetime.fromtimestamp(pub_ts, tz=ZoneInfo("Asia/Shanghai"))
                    title = item.find("title").text
                    link = item.find("link").text
                    news_msg += f"{local_pub_date}\n{title}\n{news_text}\n原文链接：{link}\n"
    news_res = {'ts': max_ts, 'msg': news_msg}
    return news_res