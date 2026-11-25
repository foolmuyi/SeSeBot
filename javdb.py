import os
import re
import random
import logging
import time
from concurrent.futures import ThreadPoolExecutor
from email.utils import parsedate_to_datetime
from http.cookies import CookieError, SimpleCookie
from threading import Lock
from urllib.parse import urlsplit
from curl_cffi import requests
from dotenv import load_dotenv, set_key
from bs4 import BeautifulSoup, Tag
from http_utils import fetch_response


_JAVDB_ENV_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), '.env')
load_dotenv(_JAVDB_ENV_PATH)
logger = logging.getLogger(__name__)
_PREVIEW_DOWNLOAD_POOL = ThreadPoolExecutor(max_workers=3, thread_name_prefix="javdb-preview")
_REVIEW_COOKIE_LOCK = Lock()
_LAST_REVIEW_HREF = '/v/8w7Da'


class JavdbLoginRequiredError(ValueError):
    pass


def _get_review_cookies():
    cookies = requests.Cookies()
    cookie_header = os.getenv('JAVDB_COOKIE', '').strip()
    if not cookie_header:
        return cookies
    parsed = SimpleCookie()
    try:
        parsed.load(cookie_header)
    except CookieError:
        raise ValueError('JAVDB_COOKIE 格式无效，请填写浏览器请求中的 Cookie 值。') from None
    if not parsed:
        raise ValueError('JAVDB_COOKIE 格式无效，请填写浏览器请求中的 Cookie 值。')
    for name, morsel in parsed.items():
        cookies.set(name, morsel.value, domain='javdb.com', path='/', secure=True)
    return cookies


def _save_refreshed_review_cookie(response, request_cookies):
    response_url = urlsplit(response.url)
    if response_url.scheme != 'https' or response_url.hostname != 'javdb.com':
        return
    headers = getattr(response, 'headers', None)
    if headers is None:
        return
    # curl_cffi 0.14's response.cookies omits expiry and leaves host-only domains
    # empty. Read Set-Cookie directly to preserve those attributes.
    for header in headers.get_list('set-cookie'):
        parsed = SimpleCookie()
        try:
            parsed.load(header)
        except CookieError:
            continue
        cookie = parsed.get('_jdb_session')
        if cookie is None or not cookie.value:
            continue
        domain = (cookie['domain'] or response_url.hostname).lstrip('.').lower()
        if domain != 'javdb.com' or cookie['path'] != '/':
            continue
        try:
            if cookie['max-age']:
                if int(cookie['max-age']) <= 0:
                    continue
            elif cookie['expires'] and parsedate_to_datetime(cookie['expires']).timestamp() <= time.time():
                continue
        except (TypeError, ValueError, OverflowError):
            continue
        if cookie.value == request_cookies.get('_jdb_session'):
            return
        updated = SimpleCookie({item.name: item.value for item in request_cookies.jar})
        updated['_jdb_session'] = cookie.value
        cookie_header = '; '.join(item.OutputString() for item in updated.values())
        os.environ['JAVDB_COOKIE'] = cookie_header
        try:
            set_key(_JAVDB_ENV_PATH, 'JAVDB_COOKIE', cookie_header)
        except OSError:
            logger.warning('Could not save refreshed JavDB cookie to .env; keeping it in memory')
        else:
            logger.info('JavDB login cookie refreshed and saved')
        return


def refresh_javdb_session():
    if os.getenv('JAVDB_COOKIE', '').strip():
        get_javdb_reviews(_LAST_REVIEW_HREF)


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
    # Serialize reads and cookie rotation so parallel commands cannot save stale cookies.
    with _REVIEW_COOKIE_LOCK:
        return _get_javdb_reviews(href)


def _get_javdb_reviews(href):
    global _LAST_REVIEW_HREF
    movie_match = re.fullmatch(r'/v/([A-Za-z0-9]+)', urlsplit(href).path.rstrip('/'))
    if not movie_match:
        raise ValueError('Invalid JavDB movie URL')
    movie_url = 'https://javdb.com/v/' + movie_match.group(1)
    cookies = _get_review_cookies()
    if not cookies:
        raise JavdbLoginRequiredError('JavDB 评论需要登录，尚未配置登录状态。')
    res = fetch_response(
        requests.get,
        url=movie_url + '/reviews/lastest',
        attempts=4,
        timeout=(3, 30),
        error_message='Failed to fetch JavDB reviews',
        impersonate="chrome",
        headers={
            'Referer': movie_url,
        },
        cookies=cookies,
    )
    if urlsplit(res.url).path.rstrip('/') in ('/login', '/sign_in', '/users/sign_in'):
        raise JavdbLoginRequiredError('JavDB 未接受当前登录状态，请更新 Cookie 后重试。')
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
        if soup.select_one('form[action*="/login"], form[action*="/sign_in"]') or (
            'This content requires login to view' in soup.get_text(' ', strip=True)
        ):
            raise JavdbLoginRequiredError('JavDB 未接受当前登录状态，请更新 Cookie 后重试。')
        if soup.select_one('#challenge-form, #challenge-running') or (
            soup.title and 'Just a moment' in soup.title.get_text()
        ):
            raise ValueError('Failed to fetch JavDB reviews: Cloudflare verification required')
    if results:
        _save_refreshed_review_cookie(res, cookies)
        _LAST_REVIEW_HREF = '/v/' + movie_match.group(1)
    return results
