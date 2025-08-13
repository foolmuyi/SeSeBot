import requests
import random
import traceback
import json
from bs4 import BeautifulSoup


base_url = 'https://jandan.net'
headers = {'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36'}
timeout = (3, 30)

def get_top_comments(filtered):
    all_comments = {}
    top_url = base_url + '/api/top/post/26402'
    res = requests.get(url=top_url, headers=headers, timeout=timeout).text
    comment_list = json.loads(res)['data']
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
    print('Downloading jandan images...')
    try_count = 0
    while try_count < 5:
        try:
            print(f'Trying to download {img_url} for {try_count+1} time')
            try_count += 1
            response = requests.get(url=img_url, headers=headers, timeout=timeout)
            if response.status_code == 200:
                return response.content
            else:
                print(response.status_code, response.reason)
        except Exception as e:
            traceback.print_exc()
            continue

    raise ValueError('Failed to download image.')

def get_hot_sub_comments(comment_id):
    hot_sub_comments = ''
    print('Getting sub comments...')
    try_count = 0
    while try_count < 5:
        try:
            print(f'Trying to download sub comments for {try_count+1} time')
            try_count += 1
            sub_comments_url = base_url + f'/api/tucao/list/{comment_id}'
            res = requests.get(url=sub_comments_url, headers=headers, timeout=timeout)
            if res.status_code == 200:
                hot_sub_comments_list = json.loads(res.text)['hot_tucao']
                for each in hot_sub_comments_list:
                    soup = BeautifulSoup(each['comment_content'], 'html.parser')
                    hot_sub_comments += soup.get_text()
                    hot_sub_comments += f'    \U00002B55\U00002B55[{each['vote_positive']}]'
                    hot_sub_comments += f'    \U0000274C\U0000274C[{each['vote_negative']}]'
                    hot_sub_comments += '\n'
                return hot_sub_comments
            else:
                print(res.status_code, res.reason)
        except Exception as e:
            traceback.print_exc()
            continue
    raise ValueError('Failed to get comments.')