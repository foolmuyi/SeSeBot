import os
import re
import random
import logging
from concurrent.futures import ThreadPoolExecutor
from curl_cffi import requests
from dotenv import load_dotenv
from bs4 import BeautifulSoup, Tag
from http_utils import fetch_response


load_dotenv()
logger = logging.getLogger(__name__)
_PREVIEW_DOWNLOAD_POOL = ThreadPoolExecutor(max_workers=3, thread_name_prefix="javdb-preview")

def download_javdb_img(url):
    logger.info("Downloading JavDB image...")
    name = url.split("/")[-1]
    response = fetch_response(
        requests.get,
        url=url,
        attempts=4,
        timeout=(3, 30),
        error_message=f'Failed to download javdb image {name}',
        retry_delay=2,
        impersonate="chrome",
    )
    return response.content

def download_javdb_imgs(urls):
    # Share the limit across simultaneous preview requests; map preserves order.
    return list(_PREVIEW_DOWNLOAD_POOL.map(download_javdb_img, urls))

def get_javdb_ranking(filtered):
    url = 'https://javdb.com/rankings/movies?p=daily&t=censored'
    res = fetch_response(
        requests.get,
        url=url,
        attempts=4,
        timeout=(3, 30),
        error_message='Failed to fetch JavDB ranking',
        impersonate="chrome",
    )
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
            score_stars = int(score_float + 0.5) * '⭐'
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
        if movie_list:
            random_movie = random.choice(movie_list)
            return random_movie
        else:
            raise ValueError('没有了，歇会儿吧')
    else:
        raise ValueError('HTML parsing failed, target element not found.')

def get_javdb_preview(href):
    url = 'https://javdb.com' + href
    res = fetch_response(
        requests.get,
        url=url,
        attempts=4,
        timeout=(3, 30),
        error_message='Failed to fetch JavDB preview',
        impersonate="chrome",
    )
    soup = BeautifulSoup(res.text, 'html.parser')
    preview_container = soup.find('div', class_ = 'tile-images')
    if preview_container and isinstance(preview_container, Tag):
        images = preview_container.find_all('a', class_='tile-item')
        image_urls = []
        for image in images:
            href = image['href']
            image_urls.append(href)
        image_urls.append(image_urls.pop(0))  # 将封面图放到最后作为结束标志
        return image_urls
    raise ValueError("Failed to get javdb preview image urls.")

def get_javdb_reviews(href):
    movie_url = 'https://javdb.com' + href.rstrip('/')
    url = movie_url + '/reviews/lastest'
    res = fetch_response(
        requests.get,
        url=url,
        attempts=4,
        timeout=(3, 30),
        error_message='Failed to fetch JavDB reviews',
        impersonate="chrome",
        headers={
            'Referer': movie_url,
        },
    )
    soup = BeautifulSoup(res.text, 'html.parser')
    # Review fragments may omit ids; the "more reviews" row shares this class.
    items = soup.select('dt.review-item:not(.more)')
    results = []
    for item in items:
        content = item.select_one('.content')
        if content is None:
            continue
        comment = content.get_text('\n', strip=True)
        if not comment:
            continue
        stars = len(item.select('.score-stars .icon-star:not(.gray)')) * '❤'
        time_element = item.select_one('.time')
        time_text = time_element.get_text(strip=True) if time_element else ''
        results.append({
            "stars": stars,
            "time": time_text,
            "comment": comment
        })
    if not results:
        if soup.select_one('form[action*="/login"], form[action*="/sign_in"]'):
            raise ValueError('Failed to fetch JavDB reviews: login required')
        if soup.select_one('#challenge-form, #challenge-running') or (
            soup.title and 'Just a moment' in soup.title.get_text()
        ):
            raise ValueError('Failed to fetch JavDB reviews: Cloudflare verification required')
    return results
