import asyncio
import json
import os
import re
import threading
import time
from collections import OrderedDict
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
EXA_DECISION_MODEL = os.getenv("EXA_DECISION_MODEL", DEFAULT_MODEL).strip() or DEFAULT_MODEL
EXA_DECISION_MAX_OUTPUT_TOKENS = _parse_int_env("EXA_DECISION_MAX_OUTPUT_TOKENS", 24, min_value=8, max_value=128)
EXA_DECISION_CONTEXT_MESSAGES = _parse_int_env("EXA_DECISION_CONTEXT_MESSAGES", 6, min_value=2, max_value=20)
EXA_DECISION_TEXT_MAX_CHARS = _parse_int_env("EXA_DECISION_TEXT_MAX_CHARS", 320, min_value=100, max_value=1200)
EXA_DECISION_CACHE_TTL_SECONDS = _parse_float_env("EXA_DECISION_CACHE_TTL_SECONDS", 600.0, min_value=30.0, max_value=86400.0)
EXA_DECISION_CACHE_MAX_SIZE = _parse_int_env("EXA_DECISION_CACHE_MAX_SIZE", 256, min_value=32, max_value=2048)
REMINDER_PARSE_MODEL = os.getenv("REMINDER_PARSE_MODEL", DEFAULT_MODEL).strip() or DEFAULT_MODEL
REMINDER_PARSE_MAX_OUTPUT_TOKENS = _parse_int_env("REMINDER_PARSE_MAX_OUTPUT_TOKENS", 120, min_value=64, max_value=256)

_EXA_DECISION_CACHE = OrderedDict()
_EXA_DECISION_CACHE_LOCK = threading.Lock()


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


def _build_decision_context(messages):
    lines = []
    for message in reversed(messages):
        role = message.get("role")
        if role not in ("user", "assistant"):
            continue
        text = _extract_text_from_content(message.get("content", ""))
        text = _normalize_whitespace(text)
        if not text:
            continue
        lines.append(f"{role}: {_clip_text(text, EXA_DECISION_TEXT_MAX_CHARS)}")
        if len(lines) >= EXA_DECISION_CONTEXT_MESSAGES:
            break
    lines.reverse()
    return "\n".join(lines).strip()


def _get_cached_exa_decision(cache_key):
    now_ts = time.time()
    with _EXA_DECISION_CACHE_LOCK:
        item = _EXA_DECISION_CACHE.get(cache_key)
        if item is None:
            return None
        expires_at, value = item
        if now_ts >= expires_at:
            _EXA_DECISION_CACHE.pop(cache_key, None)
            return None
        _EXA_DECISION_CACHE.move_to_end(cache_key)
        return bool(value)


def _set_cached_exa_decision(cache_key, value):
    expires_at = time.time() + EXA_DECISION_CACHE_TTL_SECONDS
    with _EXA_DECISION_CACHE_LOCK:
        _EXA_DECISION_CACHE[cache_key] = (expires_at, bool(value))
        _EXA_DECISION_CACHE.move_to_end(cache_key)
        while len(_EXA_DECISION_CACHE) > EXA_DECISION_CACHE_MAX_SIZE:
            _EXA_DECISION_CACHE.popitem(last=False)


def _extract_response_output_text(response_obj):
    output_text = getattr(response_obj, "output_text", None)
    if isinstance(output_text, str) and output_text.strip():
        return output_text.strip()

    output_items = getattr(response_obj, "output", None)
    if isinstance(output_items, list):
        parts = []
        for item in output_items:
            content_items = getattr(item, "content", None)
            if content_items is None and isinstance(item, dict):
                content_items = item.get("content")
            if not isinstance(content_items, list):
                continue
            for content_item in content_items:
                item_type = getattr(content_item, "type", None)
                if item_type is None and isinstance(content_item, dict):
                    item_type = content_item.get("type")
                if item_type not in {"output_text", "text"}:
                    continue
                text = getattr(content_item, "text", None)
                if text is None and isinstance(content_item, dict):
                    text = content_item.get("text")
                if isinstance(text, str) and text:
                    parts.append(text)
        if parts:
            return "".join(parts).strip()
    return ""


def _parse_json_object(raw_text):
    if not raw_text:
        return None
    candidate = raw_text.strip()
    if candidate.startswith("```"):
        candidate = re.sub(r"^```(?:json)?\s*", "", candidate, flags=re.IGNORECASE)
        candidate = re.sub(r"\s*```$", "", candidate)
    try:
        parsed = json.loads(candidate)
        if isinstance(parsed, dict):
            return parsed
    except Exception:
        pass
    json_match = re.search(r"\{.*\}", candidate, flags=re.DOTALL)
    if not json_match:
        return None
    try:
        parsed = json.loads(json_match.group(0))
    except Exception:
        return None
    return parsed if isinstance(parsed, dict) else None


def parse_reminder_request(text, now_text, timezone_name):
    instructions = (
        "你是提醒解析器，只输出 JSON。"
        "JSON 字段固定："
        '{"is_reminder": boolean, "remind_at": "YYYY-MM-DD HH:MM", "reminder_text": string, "error": string}。'
        "规则："
        "1) 用户明确表达提醒意图（提醒/闹钟/叫我）时 is_reminder=true；"
        "2) 若用户只说“8点”这类未指明时段的时间，按最近未来时间解释："
        "当前09:00时“8点”=今天20:00，当前07:00时“8点”=今天08:00；"
        "3) 若用户说了早上/下午/晚上等明确时段，优先按时段解释；"
        "4) remind_at 必须是未来时间，按给定当前时间与时区推断；"
        "5) 时间无法确定时，is_reminder=true 且 error 写明原因；"
        "6) 不是提醒请求时，is_reminder=false，其余字段用空字符串。"
    )
    prompt = (
        f"当前时间: {now_text}\n"
        f"时区: {timezone_name}\n"
        f"用户原话: {text}\n"
        "请返回 JSON。"
    )
    response = client.responses.create(
        model=REMINDER_PARSE_MODEL,
        input=[{"role": "user", "content": [{"type": "input_text", "text": prompt}]}],
        instructions=instructions,
        max_output_tokens=REMINDER_PARSE_MAX_OUTPUT_TOKENS,
    )
    raw_text = _extract_response_output_text(response)
    parsed = _parse_json_object(raw_text)
    if not parsed:
        return {
            "is_reminder": False,
            "remind_at": "",
            "reminder_text": "",
            "error": "提醒解析失败（模型未返回合法 JSON）",
        }
    is_reminder = bool(parsed.get("is_reminder", False))
    remind_at = str(parsed.get("remind_at", "")).strip()
    reminder_text = str(parsed.get("reminder_text", "")).strip()
    error = str(parsed.get("error", "")).strip()
    if is_reminder and (not reminder_text):
        reminder_text = "到时间了"
    return {
        "is_reminder": is_reminder,
        "remind_at": remind_at,
        "reminder_text": reminder_text,
        "error": error,
    }


def _parse_need_search(raw_text):
    if not raw_text:
        return None
    normalized = raw_text.strip()

    try:
        parsed = json.loads(normalized)
        if isinstance(parsed, dict):
            need_search = parsed.get("need_search")
            if isinstance(need_search, bool):
                return need_search
    except Exception:
        pass

    pattern = r'"?need_search"?\s*[:=]\s*(true|false)'
    match = re.search(pattern, normalized, flags=re.IGNORECASE)
    if match:
        return match.group(1).lower() == "true"

    lower_text = normalized.lower()
    if lower_text in {"true", "yes", "1"}:
        return True
    if lower_text in {"false", "no", "0"}:
        return False
    return None


def _should_use_exa_by_model(messages, query):
    cache_key = query.lower()
    cached_decision = _get_cached_exa_decision(cache_key)
    if cached_decision is not None:
        return cached_decision

    context_text = _build_decision_context(messages)
    decision_instructions = (
        "You are a strict router for web search.\n"
        "Decide whether external web search is REQUIRED to answer the latest user query reliably.\n"
        "Return ONLY a JSON object with one field:\n"
        '{"need_search": true} or {"need_search": false}\n'
        "Set true only when the answer likely needs up-to-date facts, real-time info, recent events,"
        " prices, schedules, or source verification.\n"
        "Set false for general knowledge, coding, writing, translation, explanation, brainstorming,"
        " or subjective discussion."
    )

    decision_prompt_lines = []
    if context_text:
        decision_prompt_lines.append("Recent conversation:")
        decision_prompt_lines.append(context_text)
        decision_prompt_lines.append("")
    decision_prompt_lines.append(f"Latest user query: {query}")
    decision_prompt = "\n".join(decision_prompt_lines)

    response = client.responses.create(
        model=EXA_DECISION_MODEL,
        input=[{"role": "user", "content": [{"type": "input_text", "text": decision_prompt}]}],
        instructions=decision_instructions,
        max_output_tokens=EXA_DECISION_MAX_OUTPUT_TOKENS,
    )
    raw_text = _extract_response_output_text(response)
    decision = _parse_need_search(raw_text)
    if decision is None:
        decision = False
    _set_cached_exa_decision(cache_key, decision)
    return decision


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
    if (not EXA_ENABLED) or (not EXA_API_KEY):
        return messages

    query = _extract_latest_user_text(messages)
    if not query:
        return messages
    if _should_skip_exa_for_image_prompt(messages, query):
        return messages

    try:
        need_search = _should_use_exa_by_model(messages, query)
    except Exception as exc:
        print(f"[Exa] 搜索判定失败，回退到模型直答: {exc}")
        return messages
    if not need_search:
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
