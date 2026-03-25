import asyncio
import os
import threading
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

API_KEY = os.getenv('Hyperbolic_API_KEY')
client = OpenAI(api_key=API_KEY, base_url="https://api.hyperbolic.xyz/v1")
DEFAULT_MODEL = os.getenv("Hyperbolic_MODEL", "deepseek-ai/DeepSeek-R1-0528")
VISION_MODEL = os.getenv("Hyperbolic_VISION_MODEL", DEFAULT_MODEL)


def _message_has_image(messages):
    for message in messages:
        content = message.get("content", "")
        if isinstance(content, list):
            for item in content:
                if isinstance(item, dict) and item.get("type") == "image_url":
                    return True
    return False


def _parse_delta_content(delta_content):
    if isinstance(delta_content, str):
        return delta_content
    if isinstance(delta_content, list):
        texts = []
        for part in delta_content:
            if isinstance(part, dict):
                text = part.get("text")
                if text:
                    texts.append(text)
            else:
                text = getattr(part, "text", None)
                if text:
                    texts.append(text)
        return "".join(texts)
    return ""


def get_ai_response(user_message):
    model_name = VISION_MODEL if _message_has_image(user_message) else DEFAULT_MODEL
    response = client.chat.completions.create(
        model=model_name,
        messages=user_message,
        stream=True,
        temperature=0.6,
        top_p=0.7,
        max_tokens=9000,
    )
    for chunk in response:
        if len(chunk.choices) > 0:
            delta = chunk.choices[0].delta
            text = _parse_delta_content(delta.content)
            if text:
                yield text


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
