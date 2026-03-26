import asyncio
import os
import threading
from dotenv import load_dotenv
from openai import OpenAI
import requests

load_dotenv()

API_KEY = os.getenv('GROK_API_KEY')
client = OpenAI(api_key=API_KEY, base_url="https://api.x.ai/v1")
DEFAULT_MODEL = "grok-4-1-fast-reasoning"
VISION_MODEL = "grok-4.20-0309-reasoning"
EXA_API_KEY = os.getenv("EXA_API_KEY", "").strip()
EXA_SEARCH_ENDPOINT = os.getenv("EXA_SEARCH_ENDPOINT", "https://api.exa.ai/search").strip()
# 预留给 Responses API 的 tools，后续可直接填入 web_search/function 等定义。
RESPONSE_TOOLS = []
RESPONSE_TOOL_CHOICE = None


def _parse_bool_env(name, default):
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() not in {"0", "false", "off", "no"}


def _parse_int_env(name, default, min_value=None, max_value=None):
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        value = int(raw.strip())
    except ValueError:
        return default
    if min_value is not None and value < min_value:
        value = min_value
    if max_value is not None and value > max_value:
        value = max_value
    return value


def _parse_float_env(name, default, min_value=None, max_value=None):
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        value = float(raw.strip())
    except ValueError:
        return default
    if min_value is not None and value < min_value:
        value = min_value
    if max_value is not None and value > max_value:
        value = max_value
    return value


EXA_ENABLED = _parse_bool_env("EXA_ENABLED", True)
EXA_TIMEOUT_SECONDS = _parse_float_env("EXA_TIMEOUT_SECONDS", 8.0, min_value=1.0, max_value=30.0)
EXA_MAX_RESULTS = _parse_int_env("EXA_MAX_RESULTS", 5, min_value=1, max_value=10)
EXA_QUERY_MAX_CHARS = _parse_int_env("EXA_QUERY_MAX_CHARS", 300, min_value=50, max_value=1200)
EXA_SNIPPET_MAX_CHARS = _parse_int_env("EXA_SNIPPET_MAX_CHARS", 220, min_value=80, max_value=1200)


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


def _normalize_whitespace(text):
    return " ".join(str(text).split()).strip()


def _clip_text(text, max_chars):
    normalized = _normalize_whitespace(text)
    if len(normalized) <= max_chars:
        return normalized
    return normalized[: max_chars - 1].rstrip() + "…"


def _extract_latest_user_text(messages):
    for message in reversed(messages):
        if message.get("role") != "user":
            continue
        text = _extract_text_from_content(message.get("content", ""))
        text = _normalize_whitespace(text)
        if text:
            return _clip_text(text, EXA_QUERY_MAX_CHARS)
    return ""


def _parse_exa_results(payload):
    if not isinstance(payload, dict):
        return []

    candidates = payload.get("results")
    if not isinstance(candidates, list):
        data = payload.get("data")
        if isinstance(data, dict):
            candidates = data.get("results")
    if not isinstance(candidates, list):
        return []

    results = []
    for item in candidates:
        if not isinstance(item, dict):
            continue

        title = _normalize_whitespace(item.get("title", ""))
        url = _normalize_whitespace(item.get("url", ""))
        published = _normalize_whitespace(
            item.get("publishedDate") or item.get("published_date") or ""
        )

        snippet = ""
        highlights = item.get("highlights")
        if isinstance(highlights, list):
            for highlight in highlights:
                if isinstance(highlight, str) and highlight.strip():
                    snippet = highlight.strip()
                    break
        if not snippet:
            text_field = item.get("text")
            if isinstance(text_field, str):
                snippet = text_field.strip()
        if not snippet:
            summary_field = item.get("summary")
            if isinstance(summary_field, str):
                snippet = summary_field.strip()

        if not (title or url or snippet):
            continue

        results.append(
            {
                "title": title or "无标题",
                "url": url,
                "published": published,
                "snippet": _clip_text(snippet, EXA_SNIPPET_MAX_CHARS) if snippet else "",
            }
        )
    return results


def _search_exa(query):
    if not EXA_ENABLED:
        return []
    if not EXA_API_KEY:
        return []
    if not query:
        return []

    payload = {"query": query, "numResults": EXA_MAX_RESULTS}
    headers = {"x-api-key": EXA_API_KEY, "Content-Type": "application/json"}
    response = requests.post(
        EXA_SEARCH_ENDPOINT,
        headers=headers,
        json=payload,
        timeout=EXA_TIMEOUT_SECONDS,
    )
    response.raise_for_status()
    return _parse_exa_results(response.json())


def _build_exa_system_context(query, results):
    lines = [
        "以下是 Exa 搜索的网页结果，请优先基于这些来源回答。",
        "如果结果不足或不确定，请明确说明，不要编造。",
        f"用户查询: {query}",
        "",
    ]
    for idx, item in enumerate(results, 1):
        title = item.get("title", "无标题")
        url = item.get("url", "")
        published = item.get("published", "")
        snippet = item.get("snippet", "")
        if published:
            lines.append(f"[{idx}] {title} ({published})")
        else:
            lines.append(f"[{idx}] {title}")
        if url:
            lines.append(f"URL: {url}")
        if snippet:
            lines.append(f"摘要: {snippet}")
        lines.append("")
    return "\n".join(lines).strip()


def _should_skip_exa_for_image_prompt(messages, query):
    if not _message_has_image(messages):
        return False
    return query in {
        "请描述并分析这张图片。",
        "请描述这张图片。",
        "describe and analyze this image",
        "describe this image",
    }


def _augment_messages_with_exa(messages):
    query = _extract_latest_user_text(messages)
    if not query:
        return messages
    if _should_skip_exa_for_image_prompt(messages, query):
        return messages

    try:
        results = _search_exa(query)
    except Exception as exc:
        print(f"[Exa] 搜索失败，回退到模型直答: {exc}")
        return messages

    if not results:
        return messages

    exa_context = _build_exa_system_context(query, results)
    if not exa_context:
        return messages
    return list(messages) + [{"role": "system", "content": exa_context}]


def get_ai_response(user_message):
    try:
        augmented_messages = _augment_messages_with_exa(user_message)
    except Exception as exc:
        print(f"[Exa] 上下文构建失败，回退到模型直答: {exc}")
        augmented_messages = user_message
    has_image = _message_has_image(augmented_messages)
    if not has_image:
        yield from _stream_response_by_model(DEFAULT_MODEL, augmented_messages)
        return

    vision_emitted = False
    try:
        for chunk in _stream_response_by_model(VISION_MODEL, augmented_messages):
            vision_emitted = True
            yield chunk
        return
    except Exception:
        if vision_emitted:
            raise
        # 视觉模型失败时，回退到默认文本模型并移除图片内容，避免再次因 image_url 报错。
        fallback_messages = _strip_images_from_messages(augmented_messages)
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
