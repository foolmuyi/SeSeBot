import requests
import random
import logging
from bs4 import BeautifulSoup
from http_utils import fetch_json, fetch_response


base_url = 'https://jandan.net'
headers = {
    'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36',
    'Referer': base_url + '/pic',
}
timeout = (3, 30)
logger = logging.getLogger(__name__)
pic_post_id = 26402
max_pic_pages = 3


def get_comment_image_urls(comment):
    img_urls = []
    for image in comment.get('images') or []:
        if isinstance(image, str) and image:
            img_urls.append(image)
        elif isinstance(image, dict):
            img_url = image.get('url') or image.get('src')
            if img_url:
                img_urls.append(img_url)
    if img_urls:
        return img_urls

    soup = BeautifulSoup(comment.get('content', ''), 'html.parser')
    return [img['src'] for img in soup.find_all('img') if img.get('src')]


def get_pic_comments():
    comment_pages = []
    latest_url = base_url + f'/api/comment/post/{pic_post_id}?order=desc&page=0'
    latest_data = fetch_json(
        requests.get,
        url=latest_url,
        headers=headers,
        timeout=timeout,
        attempts=4,
        error_message='Failed to fetch Jandan comments',
    )
    if latest_data.get('code') != 0:
        raise ValueError('Failed to fetch Jandan comments: ' + str(latest_data.get('msg', 'unknown error')))

    latest_page = latest_data.get('data')
    if not isinstance(latest_page, dict):
        raise ValueError('Failed to fetch Jandan comments: missing data')

    comment_pages.append(latest_page)
    current_page = latest_page.get('current_page')
    if isinstance(current_page, int):
        for page in range(current_page - 1, max(current_page - max_pic_pages, 0), -1):
            page_url = base_url + f'/api/comment/post/{pic_post_id}?order=desc&page={page}'
            page_data = fetch_json(
                requests.get,
                url=page_url,
                headers=headers,
                timeout=timeout,
                attempts=4,
                error_message='Failed to fetch Jandan comments',
            )
            if page_data.get('code') != 0:
                break
            page_content = page_data.get('data')
            if isinstance(page_content, dict):
                comment_pages.append(page_content)

    comments = []
    for comment_page in comment_pages:
        comment_list = comment_page.get('list')
        if isinstance(comment_list, list):
            comments.extend(comment_list)
    return comments


def get_top_comments(filtered):
    all_comments = {}
    for comment in get_pic_comments():
        comment_id = comment['id']
        if comment_id not in filtered:
            img_urls = get_comment_image_urls(comment)
            if img_urls:
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
        return ''
    for each in hot_sub_comments_list:
        soup = BeautifulSoup(each['comment_content'], 'html.parser')
        hot_sub_comments += soup.get_text()
        hot_sub_comments += f'    ⭕⭕[{each["vote_positive"]}]'
        hot_sub_comments += f'    ❌❌[{each["vote_negative"]}]'
        hot_sub_comments += '\n'
    return hot_sub_comments
