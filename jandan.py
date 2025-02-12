import requests
import random
import traceback
from lxml import html


base_url = 'https://jandan.net'
headers = {'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36'}
timeout = (3, 30)

def get_top_comments(filtered):
    all_comments = {}
    top_url = base_url + '/top'
    res = requests.get(url=top_url, headers=headers, timeout=timeout).text
    tree = html.fromstring(res)
    commentlist = tree.xpath('//*[@id="pic"]/ol/li')
    for comment in commentlist:
        comment_id = str(comment.xpath('./div/div/div[2]/span/a/@href')[0]).split('/')[-1]
        if comment_id not in filtered:
            imgs = comment.xpath('./div/div/div[2]/p/a/@href')
            img_urls = ['https:' + str(img_url) for img_url in imgs]
            all_comments[comment_id] = img_urls
    if all_comments:
        random_comment = {}
        comment_id, img_urls = random.choice(list(all_comments.items()))
        random_comment['comment_url'] = base_url + '/t/' + comment_id
        random_comment['img_urls'] = img_urls
        return random_comment
    else:
        raise ValueError('No More Images.')

def get_comment_img(img_url):
    print('Downloading jandan images...')
    try_count = 1
    while try_count < 5:
        try:
            print(f'Trying to download {img_url} for {try_count} time')
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
