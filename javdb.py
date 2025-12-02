import os
import re
import time
import random
import requests
import traceback
from dotenv import load_dotenv
from bs4 import BeautifulSoup, Tag


load_dotenv()
# CF_WORKER_URL = os.getenv('CF_WORKER_URL')
# CF_AUTH_KEY = os.getenv('CF_AUTH_KEY')

headers = {'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36'}
timeout = (3, 30)

def download_javdb_img(url):
    print('javdb image downloading....')
    headers_download = headers.copy()
    # headers_download["CF-Auth-Key"] = CF_AUTH_KEY
    name = url.split("/")[-1]

    try_count = 1
    while try_count < 5:
        try:
            print(f'Trying to download {name} for the {try_count}(th) time')
            try_count += 1
            response = requests.get(url=url, headers=headers_download, timeout=timeout)
            if response.status_code == 200:
                return response.content
            else:
                print(response.status_code, response.reason)
        except Exception as e:
            traceback.print_exc()
            continue

    raise ValueError('Failed to download javdb image.')

def get_javdb_ranking(filtered):
    url = 'https://javdb.com/rankings/movies?p=daily&t=censored'
    res = requests.get(url)
    soup = BeautifulSoup(res.text, 'html.parser')
    movie_container = soup.find('div', class_ = 'movie-list')
    if movie_container and isinstance(movie_container, Tag):
        movies = movie_container.find_all('div', class_='item')
        movie_list = []
        for movie in movies:
            href = str(movie.find('a')['href'])
            title = str(movie.find('a')['title'])
            img_src = str(movie.select_one('div.cover img')['src'])
            code = str(movie.select_one('div.video-title strong').text)
            score_raw = str(movie.find('div', class_='score').find('span', class_='value').text.strip().replace('\xa0', ' '))
            score_pattern = r'^(\d+(?:\.\d+)?)'
            score_float = float(re.match(score_pattern, score_raw).group(1))
            score_stars = round(score_float) * '\U00002B50'
            score = score_stars + ' ' + score_raw
            if code not in filtered:
                movie_info = {
                    'href': href,
                    'title': title,
                    'img_src': img_src,
                    'code': code,
                    'score': score}
                movie_list.append(movie_info)
            else:
                pass
    random_movie = random.choice(movie_list)
    return random_movie

def get_javdb_preview(href):
    url = 'https://javdb.com' + href
    res = requests.get(url)
    soup = BeautifulSoup(res.text, 'html.parser')
    preview_container = soup.find('div', class_ = 'tile-images')
    if preview_container and isinstance(preview_container, Tag):
        images = preview_container.find_all('a', class_='tile-item')
        image_urls = []
        for image in images:
            href = image['href']
            image_urls.append(href)
        return image_urls
    raise ValueError("Failed to get javdb preview image urls.")