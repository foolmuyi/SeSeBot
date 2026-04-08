import hashlib
import io
import logging
import random
import re
from html import unescape
from pathlib import Path
from urllib.parse import urljoin

import requests
from PIL import Image, ImageDraw, ImageFont

from http_utils import fetch_response


logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).resolve().parent
ASSETS_DIR = BASE_DIR / "assets" / "shici"
BACKGROUND_FILE = ASSETS_DIR / "backgrounds" / "paper1.jpg"
FONT_FILE = ASSETS_DIR / "fonts" / "kangxi_font.ttf"

BASE_URL = "https://www.guwendao.net"
MINGJU_LIST_URL = f"{BASE_URL}/mingjus/"
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36"
    )
}
TIMEOUT = (3, 30)

ENTRY_PATTERN = re.compile(
    r'<a[^>]*href="(?P<quote_link>/mingju/juv_[^"]+)"[^>]*>(?P<quote>.*?)</a>\s*'
    r'<span[^>]*>.*?</span>\s*'
    r'<a[^>]*href="(?P<source_link>[^"]+)"[^>]*>(?P<source>.*?)</a>',
    flags=re.S,
)
CONTSON_PATTERN = re.compile(r'<div class="contson"[^>]*>(.*?)</div>', flags=re.S)
META_DESC_PATTERN = re.compile(
    r'<meta\s+name="description"\s+content="(.*?)"\s*/?>',
    flags=re.S | re.I,
)
QUOTE_ID_PATTERN = re.compile(r"juv_([0-9a-f]+)\.aspx", flags=re.I)


def split_text_by_punctuation(text):
    punctuations = r"[，。！？；、]"
    temp_text = re.sub(punctuations, "\n", text)
    lines = [line.strip() for line in temp_text.split("\n") if line.strip()]
    return lines


def _ensure_assets():
    if not BACKGROUND_FILE.exists():
        raise FileNotFoundError(f"背景图片不存在: {BACKGROUND_FILE}")
    if not FONT_FILE.exists():
        raise FileNotFoundError(f"字体文件不存在: {FONT_FILE}")


def _fetch_html(url, error_message):
    response = fetch_response(
        requests.get,
        url=url,
        headers=HEADERS,
        timeout=TIMEOUT,
        attempts=4,
        error_message=error_message,
    )
    response.encoding = "utf-8"
    return response.text


def _strip_tags(fragment):
    return re.sub(r"<[^>]+>", "", fragment)


def _normalize_inline_text(fragment):
    text = unescape(_strip_tags(fragment))
    text = text.replace("\xa0", " ").replace("\u3000", " ")
    return re.sub(r"\s+", " ", text).strip()


def _normalize_block_text(fragment):
    fragment = re.sub(r"<br\s*/?>", "\n", fragment, flags=re.I)
    fragment = re.sub(r"</p\s*>", "\n", fragment, flags=re.I)
    fragment = re.sub(r"<p[^>]*>", "", fragment, flags=re.I)
    text = unescape(_strip_tags(fragment))
    text = text.replace("\r", "\n").replace("\xa0", " ").replace("\u3000", " ")
    lines = [line.strip() for line in text.split("\n")]
    lines = [line for line in lines if line]
    return "\n".join(lines)


def _build_quote_id(quote_link, quote_text):
    quote_match = QUOTE_ID_PATTERN.search(quote_link)
    if quote_match:
        return f"shici:juv:{quote_match.group(1).lower()}"
    digest = hashlib.md5(f"{quote_link}|{quote_text}".encode("utf-8")).hexdigest()[:12]
    return f"shici:{digest}"


def _extract_mingju_entries(list_html):
    entries = []
    seen_ids = set()
    for match in ENTRY_PATTERN.finditer(list_html):
        quote_link = match.group("quote_link").strip()
        source_link = match.group("source_link").strip()
        quote_text = _normalize_inline_text(match.group("quote"))
        source_text = _normalize_inline_text(match.group("source"))
        if (not quote_text) or (not source_text):
            continue

        quote_id = _build_quote_id(quote_link, quote_text)
        if quote_id in seen_ids:
            continue
        seen_ids.add(quote_id)

        quote_url = urljoin(BASE_URL, quote_link)
        source_url = urljoin(BASE_URL, source_link)
        entries.append(
            {
                "quote_id": quote_id,
                "quote_text": quote_text,
                "source_text": source_text,
                "quote_url": quote_url,
                "source_url": source_url,
            }
        )
    return entries


def _extract_full_text(source_html):
    contson_match = CONTSON_PATTERN.search(source_html)
    if contson_match:
        full_text = _normalize_block_text(contson_match.group(1))
        if full_text:
            return full_text

    meta_match = META_DESC_PATTERN.search(source_html)
    if meta_match:
        fallback_text = _normalize_inline_text(meta_match.group(1))
        if fallback_text:
            return fallback_text

    raise ValueError("Failed to parse full text from source page")


def _fetch_mingju_entries():
    list_html = _fetch_html(MINGJU_LIST_URL, "Failed to fetch guwendao mingju list")
    entries = _extract_mingju_entries(list_html)
    for item in entries:
        item["list_url"] = MINGJU_LIST_URL
    return entries


def _fetch_full_text_by_url(source_url):
    source_html = _fetch_html(source_url, f"Failed to fetch full text page: {source_url}")
    return _extract_full_text(source_html)


def fetch_shici_item(filtered=None):
    entries = _fetch_mingju_entries()
    if not entries:
        raise ValueError("未抓到任何名句。")

    if filtered is not None:
        entries = [entry for entry in entries if entry["quote_id"] not in filtered]
    if not entries:
        raise ValueError("名句都发过了，请稍后再试。")

    entry = random.choice(entries)
    full_text = _fetch_full_text_by_url(entry["source_url"])
    return {
        "quote_id": entry["quote_id"],
        "content": entry["quote_text"],
        "source_text": entry["source_text"],
        "source_url": entry["source_url"],
        "full_text": full_text,
        "full_text_url": entry["source_url"],
        "quote_url": entry["quote_url"],
        "list_url": entry["list_url"],
    }


def _text_size(draw, text, font):
    bbox = draw.textbbox((0, 0), text, font=font)
    return bbox[2] - bbox[0], bbox[3] - bbox[1]


def _build_sign(author, title, sign_text):
    if sign_text:
        return f"—— {sign_text}"
    if author and title:
        return f"—— {author} 《{title}》"
    if title:
        return f"—— 《{title}》"
    return f"—— {author}"


def _measure_layout(draw, lines, sign, font_path, main_size):
    # 落款字体随主字体缩放，但不超过主字体，避免落款喧宾夺主。
    sub_size = min(main_size, max(14, int(main_size * 0.66)))
    font_main = ImageFont.truetype(font_path, main_size)
    font_sub = ImageFont.truetype(font_path, sub_size)

    # 行距与落款间距按字号联动，保持不同字号下的视觉比例一致。
    line_spacing = max(10, int(main_size * 0.42))
    sign_gap = max(14, int(sub_size * 0.85))

    line_height = _text_size(draw, "诗", font_main)[1]
    sign_height = _text_size(draw, "诗", font_sub)[1]
    line_widths = [_text_size(draw, line, font_main)[0] for line in lines]
    max_content_width = max(line_widths) if line_widths else 0
    sign_width = _text_size(draw, sign, font_sub)[0]

    content_height = (line_height * len(lines)) + (line_spacing * (len(lines) - 1))
    block_height = content_height + sign_gap + sign_height
    max_width = max(max_content_width, sign_width)

    return {
        "font_main": font_main,
        "font_sub": font_sub,
        "line_height": line_height,
        "line_spacing": line_spacing,
        "sign_gap": sign_gap,
        "content_height": content_height,
        "block_height": block_height,
        "max_content_width": max_content_width,
        "sign_width": sign_width,
        "max_width": max_width,
    }


def _select_dynamic_layout(draw, lines, sign, font_path, canvas_width, canvas_height):
    # 控制文本块占背景的目标比例：
    # 1) 最长行宽度 <= 背景宽度的 70%
    # 2) 整个文本块高度 <= 背景高度的 75%
    target_width = canvas_width * 0.70
    target_height = canvas_height * 0.75
    max_main_size = 60
    min_main_size = 18
    best_layout = None

    # 从大字号往小字号试，优先保留更好的可读性。
    for main_size in range(max_main_size, min_main_size - 1, -2):
        layout = _measure_layout(draw, lines, sign, font_path, main_size)
        best_layout = layout
        if (layout["max_width"] <= target_width) and (layout["block_height"] <= target_height):
            return layout

    if best_layout is None:
        return _measure_layout(draw, lines, sign, font_path, min_main_size)

    if best_layout["max_width"] > target_width:
        # 若到最小字号仍超宽，按比例再缩一次，确保不会出界。
        scale = target_width / max(best_layout["max_width"], 1)
        scaled_main_size = max(12, int(best_layout["font_main"].size * scale))
        return _measure_layout(draw, lines, sign, font_path, scaled_main_size)

    return best_layout


def generate_poem_image_left_aligned(
    text,
    author,
    title,
    background_path,
    font_path,
    sign_text=None,
):
    base_img = Image.open(background_path).convert("RGB")
    draw = ImageDraw.Draw(base_img)
    width, height = base_img.size

    text_color = (30, 30, 30)

    lines = split_text_by_punctuation(text)
    if not lines:
        lines = [text.strip() or "无内容"]
    # 以“正文最长行 + 落款行”共同决定字号，避免任一行超宽。
    sign = _build_sign(author=author, title=title, sign_text=sign_text)
    layout = _select_dynamic_layout(
        draw=draw,
        lines=lines,
        sign=sign,
        font_path=font_path,
        canvas_width=width,
        canvas_height=height,
    )

    font_main = layout["font_main"]
    font_sub = layout["font_sub"]
    line_spacing = layout["line_spacing"]
    line_height = layout["line_height"]
    sign_gap = layout["sign_gap"]
    content_height = layout["content_height"]

    common_start_x = (width - layout["max_content_width"]) / 2
    content_start_y = (height - layout["block_height"]) / 2

    current_y = content_start_y
    for line in lines:
        draw.text((common_start_x, current_y), line, font=font_main, fill=text_color)
        current_y += line_height + line_spacing

    sign_y = content_start_y + content_height + sign_gap
    draw.text(((width - layout["sign_width"]) / 2, sign_y), sign, font=font_sub, fill=(80, 80, 80))

    return base_img


def get_shici_card(filtered=None):
    _ensure_assets()
    item = fetch_shici_item(filtered)
    image = generate_poem_image_left_aligned(
        item["content"],
        author="",
        title="",
        background_path=str(BACKGROUND_FILE),
        font_path=str(FONT_FILE),
        sign_text=item["source_text"],
    )
    buffer = io.BytesIO()
    image.save(buffer, format="JPEG", quality=95)
    image.close()
    image_bytes = buffer.getvalue()

    digest = item["quote_id"].split(":")[-1]
    return {
        "quote_id": item["quote_id"],
        "image_bytes": image_bytes,
        "filename": f"shici_{digest}.jpg",
        "text": f"{item['content']}\n—— {item['source_text']}\n原文链接：{item['full_text_url']}",
        "source_text": item["source_text"],
        "source_url": item["source_url"],
        "full_text": item["full_text"],
        "full_text_url": item["full_text_url"],
        "quote_url": item["quote_url"],
        "list_url": item["list_url"],
    }
