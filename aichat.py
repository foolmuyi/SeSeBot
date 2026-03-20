import asyncio
import os
import threading
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

API_KEY = os.getenv('Hyperbolic_API_KEY')
client = OpenAI(api_key=API_KEY, base_url="https://api.hyperbolic.xyz/v1")


def get_ai_response(user_message):
    response = client.chat.completions.create(model="deepseek-ai/DeepSeek-R1-0528", messages=user_message, stream=True, 
        temperature=0.6, top_p=0.7, max_tokens=9000)
    for chunk in response:
        if len(chunk.choices) > 0:
            delta = chunk.choices[0].delta
            if delta.content:
                yield delta.content


async def stream_ai_response(user_message):
    loop = asyncio.get_running_loop()
    queue = asyncio.Queue()
    sentinel = object()

    def worker():
        try:
            for chunk in get_ai_response(user_message):
                loop.call_soon_threadsafe(queue.put_nowait, chunk)
        except Exception as exc:
            loop.call_soon_threadsafe(queue.put_nowait, exc)
        finally:
            loop.call_soon_threadsafe(queue.put_nowait, sentinel)

    threading.Thread(target=worker, daemon=True).start()

    while True:
        item = await queue.get()
        if item is sentinel:
            break
        if isinstance(item, Exception):
            raise item
        yield item
