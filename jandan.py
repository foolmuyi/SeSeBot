import requests
import random
import logging
from bs4 import BeautifulSoup
from http_utils import fetch_json, fetch_response


base_url = 'https://jandan.net'
headers = {'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36'}
timeout = (3, 30)
logger = logging.getLogger(__name__)

def get_top_comments(filtered):
    all_comments = {}
    top_url = base_url + '/api/top/post/26402'
    top_data = fetch_json(
        requests.get,
        url=top_url,
        headers=headers,
        timeout=timeout,
        attempts=4,
        error_message='Failed to fetch Jandan top comments',
    )
    comment_list = top_data.get('data')
    if not isinstance(comment_list, list):
        raise ValueError('Failed to fetch Jandan top comments: missing data')
    for comment in comment_list:
        comment_id = comment['id']
        if comment_id not in filtered:
            all_comments[comment_id] = {}
            soup = BeautifulSoup(comment['content'], 'html.parser')
            img_urls = [img['src'] for img in soup.find_all('img') if img.get('src')]
            all_comments[comment_id] = img_urls
    if all_comments:
        random_comment_id = random.choice(list(all_comments.keys()))
        random_comment = {'comment_id': random_comment_id,
                          'img_urls': all_comments[random_comment_id],
                          'comment_url': base_url + '/t/' + str(random_comment_id)}
        return random_comment
    else:
        raise ValueError('真的一张都没有了！')

def get_comment_img(img_url):
    logger.info("Downloading jandan image...")
    response = fetch_response(
        requests.get,
        url=img_url,
        headers=headers,
        timeout=timeout,
        attempts=4,
        error_message='Failed to download image',
    )
    return response.content

def get_hot_sub_comments(comment_id):
    hot_sub_comments = ''
    logger.info("Getting sub comments...")
    sub_comments_url = base_url + f'/api/tucao/list/{comment_id}'
    sub_comments_data = fetch_json(
        requests.get,
        url=sub_comments_url,
        headers=headers,
        timeout=timeout,
        attempts=4,
        error_message='Failed to get comments',
    )
    hot_sub_comments_list = sub_comments_data.get('hot_tucao')
    if not isinstance(hot_sub_comments_list, list):
        raise ValueError('Failed to get comments: missing hot_tucao')
    for each in hot_sub_comments_list:
        soup = BeautifulSoup(each['comment_content'], 'html.parser')
        hot_sub_comments += soup.get_text()
        hot_sub_comments += f'    ⭕⭕[{each["vote_positive"]}]'
        hot_sub_comments += f'    ❌❌[{each["vote_negative"]}]'
        hot_sub_comments += '\n'
    return hot_sub_comments
