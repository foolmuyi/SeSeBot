import os
import time
import random
import requests
import traceback
from dotenv import load_dotenv


load_dotenv()
COOKIE = os.getenv('PIXIV_COOKIE')
CF_WORKER_URL = os.getenv('CF_WORKER_URL')
CF_AUTH_KEY = os.getenv('CF_AUTH_KEY')

headers = {'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36',
           'Cookie': str(COOKIE)}
timeout = (3, 30)

def download_img(url, referer):
    print('downloading....')
    headers_download = headers.copy()
    headers_download["referer"] = str(referer)
    headers_download["CF-Auth-Key"] = CF_AUTH_KEY
    name = url.split("/")[-1]

    try_count = 1
    while try_count < 5:
        try:
            print(f'Trying to download {name} for {try_count} time')
            try_count += 1
            response = requests.get(url=url, headers=headers_download, timeout=timeout)
            if response.status_code == 200:
                return response.content
            else:
                print(response.status_code, response.reason)
        except Exception as e:
            traceback.print_exc()
            continue

    raise ValueError('Failed to download image.')

def get_ranking(mode, filtered, pages=2):
    url = 'https://www.pixiv.net/'
    image_list = []
    for i in range(pages):
        url = url + f"ranking.php?mode={mode}&p={i+1}&format=json"
        res = requests.get(url, headers=headers, timeout=timeout)
        datas = res.json()["contents"]
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
    artworks_data = requests.get(artworks_url, headers=headers, timeout=timeout).json()["body"]
    for artwork in artworks_data:
        img_url = artwork['urls']['original']
        img_url_proxied = img_url.replace("i.pximg.net", CF_WORKER_URL, 1)  # 将原url替换为代理url
        msg['imgs_url'].append(img_url_proxied)
    return msg
