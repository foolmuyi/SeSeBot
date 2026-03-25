import os
import time
import random
import requests
from dotenv import load_dotenv
from http_utils import fetch_json, fetch_response


load_dotenv()
COOKIE = os.getenv('PIXIV_COOKIE')
CF_PIXIV_URL = os.getenv('CF_PIXIV_URL')
CF_PIXIV_KEY = os.getenv('CF_PIXIV_KEY')

headers = {'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36',
           'Cookie': str(COOKIE)}
timeout = (3, 30)


def require_pixiv_proxy_config():
    if not CF_PIXIV_URL or not CF_PIXIV_KEY:
        raise ValueError('Missing CF_PIXIV_URL or CF_PIXIV_KEY')

def download_pixiv_img(url, referer):
    print('downloading....')
    require_pixiv_proxy_config()
    headers_download = headers.copy()
    headers_download["referer"] = str(referer)
    headers_download["CF-Auth-Key"] = CF_PIXIV_KEY
    name = url.split("/")[-1]
    response = fetch_response(
        requests.get,
        url=url,
        headers=headers_download,
        timeout=timeout,
        attempts=4,
        error_message=f'Failed to download image {name}',
    )
    return response.content

def get_pixiv_ranking(mode, filtered, pages=2):
    require_pixiv_proxy_config()
    url = 'https://www.pixiv.net/'
    image_list = []
    for i in range(pages):
        url = url + f"ranking.php?mode={mode}&p={i+1}&format=json"
        ranking_data = fetch_json(
            requests.get,
            url=url,
            headers=headers,
            timeout=timeout,
            attempts=4,
            error_message='Failed to fetch Pixiv ranking',
        )
        datas = ranking_data.get("contents")
        if not isinstance(datas, list):
            raise ValueError('Failed to fetch Pixiv ranking: missing contents')
        for data in datas:
            if str(data["illust_id"]) not in filtered:
                image = {
                    "title": data["title"],
                    "user_name": data["user_name"],
                    "p_id": data["illust_id"],
                    "referer": f"https://www.pixiv.net/artworks/{data['illust_id']}"
                }
                image_list.append(image)
            else:
                pass

    msg = {}
    rand_art = random.choice(range(len(image_list)))
    artworks = image_list[rand_art]
    msg['artworks_url'] = artworks['referer']
    msg['imgs_url'] = []
    artworks_url = f"https://www.pixiv.net/ajax/illust/{artworks['p_id']}/pages?lang=zh"
    artworks_res = fetch_json(
        requests.get,
        url=artworks_url,
        headers=headers,
        timeout=timeout,
        attempts=4,
        error_message='Failed to fetch Pixiv artwork pages',
    )
    artworks_data = artworks_res.get("body")
    if not isinstance(artworks_data, list):
        raise ValueError('Failed to fetch Pixiv artwork pages: missing body')
    for artwork in artworks_data:
        img_url = artwork['urls']['original']
        img_url_proxied = img_url.replace("i.pximg.net", CF_PIXIV_URL, 1)  # 将原url替换为代理url
        msg['imgs_url'].append(img_url_proxied)
    return msg
