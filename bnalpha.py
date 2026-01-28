import time
import requests
from xml.etree import ElementTree as ET
from email.utils import parsedate_to_datetime
from datetime import datetime
from zoneinfo import ZoneInfo
from bs4 import BeautifulSoup


def check_alpha():
    print('Checking alpha news...')
    url = "https://www.techflowpost.com/api/client/common/rss.xml"
    response = requests.get(url)
    xml_data = response.content

    root = ET.fromstring(xml_data)
    news_msg = ''
    for item in root.findall(".//item"):
        pub_date = item.find('pubDate').text
        pub_ts = parsedate_to_datetime(pub_date).timestamp()
        title = item.find("title").text
        if (time.time() - pub_ts) < (5 * 60):
            if ("alpha" in title.lower()) or ("tge" in title.lower()):
                if ("binance" in title.lower()) or ("币安" in title):
                    local_pub_date = datetime.fromtimestamp(pub_ts, tz=ZoneInfo("Asia/Shanghai"))
                    news = item.find('description').text
                    news_text = BeautifulSoup(news, 'html.parser').get_text()
                    link = item.find("link").text
                    news_msg += f"{local_pub_date}\n{title}\n{news_text}\n原文链接：{link}\n"
    if news_msg:
        return news_msg
    else:
        print('No more news...')
        return None