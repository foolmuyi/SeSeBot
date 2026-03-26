import asyncio
import os
import threading
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

API_KEY = os.getenv('GROK_API_KEY')
client = OpenAI(api_key=API_KEY, base_url="https://api.x.ai/v1")
DEFAULT_MODEL = "grok-4-1-fast-reasoning"
VISION_MODEL = "grok-4.20-0309-reasoning"
# 预留给 Responses API 的 tools，后续可直接填入 web_search/function 等定义。
RESPONSE_TOOLS = []
RESPONSE_TOOL_CHOICE = None


def _message_has_image(messages):
    for message in messages:
        content = message.get("content", "")
        if isinstance(content, list):
            for item in content:
                if isinstance(item, dict) and item.get("type") == "image_url":
                    return True
    return False


def _extract_text_from_content(content):
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        texts = []
        for item in content:
            if isinstance(item, dict) and item.get("type") == "text":
                text = item.get("text", "")
                if text:
                    texts.append(text)
        return "\n".join(texts)
    return str(content)


def _content_to_responses_parts(content):
    if isinstance(content, str):
        return [{"type": "input_text", "text": content}]
    if isinstance(content, list):
        parts = []
        for item in content:
            if not isinstance(item, dict):
                continue
            item_type = item.get("type")
            if item_type == "text":
                text = item.get("text", "")
                if text:
                    parts.append({"type": "input_text", "text": text})
            elif item_type == "image_url":
                image_url = item.get("image_url")
                if isinstance(image_url, dict):
                    image_url = image_url.get("url")
                if image_url:
                    parts.append({"type": "input_image", "image_url": image_url})
        if parts:
            return parts
    return [{"type": "input_text", "text": str(content)}]


def _build_responses_payload(messages):
    instructions = []
    input_items = []
    for message in messages:
        role = message.get("role", "user")
        content = message.get("content", "")
        if role == "system":
            system_text = _extract_text_from_content(content).strip()
            if system_text:
                instructions.append(system_text)
            continue
        if role not in ("user", "assistant", "developer"):
            role = "user"
        input_items.append({"role": role, "content": _content_to_responses_parts(content)})
    final_instructions = "\n\n".join(instructions) if instructions else None
    return final_instructions, input_items


def _stream_with_responses_api(model_name, user_message):
    instructions, input_items = _build_responses_payload(user_message)
    request_kwargs = {
        "model": model_name,
        "input": input_items,
        "stream": True
    }
    if instructions:
        request_kwargs["instructions"] = instructions
    request_kwargs["tools"] = RESPONSE_TOOLS
    if RESPONSE_TOOL_CHOICE is not None:
        request_kwargs["tool_choice"] = RESPONSE_TOOL_CHOICE

    stream = client.responses.create(**request_kwargs)
    for event in stream:
        event_type = getattr(event, "type", "")
        if event_type == "response.output_text.delta":
            delta = getattr(event, "delta", "")
            if delta:
                yield delta
        elif event_type == "error":
            error_obj = getattr(event, "error", None)
            raise RuntimeError(f"Responses API stream error: {error_obj or event}")


def _stream_response_by_model(model_name, user_message):
    yield from _stream_with_responses_api(model_name, user_message)


def _strip_images_from_messages(messages):
    text_messages = []
    for message in messages:
        role = message.get("role", "user")
        content = message.get("content", "")
        if not isinstance(content, list):
            text_messages.append({"role": role, "content": content})
            continue

        text_parts = []
        for part in content:
            if isinstance(part, dict) and part.get("type") == "text":
                text = part.get("text", "").strip()
                if text:
                    text_parts.append(text)
        text_content = "\n".join(text_parts).strip()
        if (not text_content) and role == "user":
            text_content = "[用户发送了图片，但当前模型暂时无法读取图片内容]"
        text_messages.append({"role": role, "content": text_content})
    return text_messages


def get_ai_response(user_message):
    has_image = _message_has_image(user_message)
    if not has_image:
        yield from _stream_response_by_model(DEFAULT_MODEL, user_message)
        return

    vision_emitted = False
    try:
        for chunk in _stream_response_by_model(VISION_MODEL, user_message):
            vision_emitted = True
            yield chunk
        return
    except Exception:
        if vision_emitted:
            raise
        # 视觉模型失败时，回退到默认文本模型并移除图片内容，避免再次因 image_url 报错。
        fallback_messages = _strip_images_from_messages(user_message)
        yield "[提示] 视觉模型当前不可用，已回退到文本模型，以下回答基于文字信息。\n\n"
        try:
            yield from _stream_response_by_model(DEFAULT_MODEL, fallback_messages)
            return
        except Exception as exc:
            raise RuntimeError(
                "视觉模型调用失败，且文本回退也失败。请检查模型名或 API 权限。"
            ) from exc


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
