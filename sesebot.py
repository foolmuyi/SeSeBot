import asyncio
import os
import io
import base64
import json
import time
import traceback
from pixiv import *
from aichat import *
from jandan import *
from javdb import *
from bnalpha import *
from dotenv import load_dotenv
from PIL import Image
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.error import TimedOut
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, CallbackContext, CallbackQueryHandler


class TelegramBot:
    def __init__(self, token):
        self.application = Application.builder().token(token).build()
        self.filtered = {}
        self.aichat_contexts = {}
        dir_path = os.path.dirname(os.path.abspath(__file__))
        whitelist_path = os.path.join(dir_path, "whitelist.json")
        with open(whitelist_path, "r") as f:
            self.whitelist = json.load(f)

    @staticmethod
    def check_access(func):
        async def wrapper(self, update, context, *args, **kwargs):
            user_id = str(update.effective_user.id)
            if user_id not in self.whitelist:
                await update.message.reply_text("前面的区域以后再来探索吧:)")
                return
            return await func(self, update, context, *args, **kwargs)
        return wrapper

    def check_working_time(self):
        hour_seconds = 60*60
        day_seconds = 24*hour_seconds
        weekday = (time.time()//day_seconds + 3)%7    # 0~6
        hours = (time.time()//hour_seconds)%24    # 0~23 UTC
        if (weekday < 5) and (0 < hours < 9):
            return True
        else:
            return False

    async def get_pixiv_imgs(self, update, mode):
        await update.effective_message.reply_text('我知道你很急，但你先别急！')
        try:
            chat_id = str(update.effective_message.chat.id)
            if chat_id not in self.filtered.keys():
                self.filtered[chat_id] = []
            msg = await asyncio.to_thread(get_pixiv_ranking, mode, self.filtered[chat_id], 2)
            artworks_url = msg['artworks_url']
            artworks_id = artworks_url.split("/")[-1]
            self.filtered[chat_id].append(artworks_id)
            for img_url in msg['imgs_url']:
                img = await asyncio.to_thread(download_pixiv_img, img_url, artworks_url)
                img_width, img_height = Image.open(io.BytesIO(img)).size
                if ((len(img) < 10*1024*1024) and ((img_width + img_height) < 10000) 
                    and (0.05 < img_height/img_width < 20)):
                    await self.application.bot.send_photo(chat_id=chat_id, photo=img)
                else:
                    filename = img_url.split("/")[-1]
                    await self.application.bot.send_document(chat_id=chat_id, document=img, filename=filename)
            await update.effective_message.reply_text(artworks_url)
        except Exception as e:
            traceback.print_exc()
            await update.effective_message.reply_text('Error:\n' + str(e))

    async def get_jandan_imgs(self, update, context):
        if update:
            chat_id = str(update.effective_message.chat.id)
            await update.effective_message.reply_text('你可少看点儿沙雕图吧！')
        else:
            if not self.check_working_time():
                return
            else:
                chat_id = str(context.job.chat_id)
                await self.application.bot.send_message(chat_id=chat_id, text='沙雕图来咯')
        has_comment = False
        try:
            if chat_id not in self.filtered.keys():
                self.filtered[chat_id] = []
            comment = await asyncio.to_thread(get_top_comments, self.filtered[chat_id])
            comment_id = comment['comment_id']
            has_comment = True
            self.filtered[chat_id].append(comment_id)
            for img_url in comment['img_urls']:
                filename = img_url.split('/')[-1]
                img = await asyncio.to_thread(get_comment_img, img_url)
                img_width, img_height = Image.open(io.BytesIO(img)).size
                if img_url.split('.')[-1] == 'gif':
                    await self.application.bot.send_animation(chat_id=chat_id, animation=img, filename=filename)
                elif ((len(img) < 10*1024*1024) and ((img_width + img_height) < 10000) and (0.05 < img_height/img_width < 20)):
                    await self.application.bot.send_photo(chat_id=chat_id, photo=img)
                else:
                    await self.application.bot.send_document(chat_id=chat_id, document=img, filename=filename)
        except TimedOut:  # Telegram自身Bug：发送成功后仍有可能收到TimeOut异常
            traceback.print_exc()
        except Exception as e:
            traceback.print_exc()
            await self.application.bot.send_message(chat_id=chat_id, text=('Error:\n' + str(e)))
        finally:
            if has_comment == True:  # 至少要成功获取到图片链接才能尝试获取评论
                try:
                    hot_sub_comments = await asyncio.to_thread(get_hot_sub_comments, comment_id)
                    text2send = hot_sub_comments + '\n' + comment['comment_url']
                    await self.application.bot.send_message(chat_id=chat_id, text=text2send)
                except Exception as e:
                    traceback.print_exc()
                    await self.application.bot.send_message(chat_id=chat_id, text=('Error:\n' + str(e)))

    async def get_javdb_cover(self, update):
        try:
            chat_id = str(update.effective_message.chat.id)
            if chat_id not in self.filtered.keys():
                self.filtered[chat_id] = []
            msg = await asyncio.to_thread(get_javdb_ranking, self.filtered[chat_id])
            movie_url = 'https://javdb.com' + msg['href']
            movie_title = msg['title']
            movie_cover_url = msg['img_src']
            movie_code = msg['code']
            movie_score = msg['score']
            self.filtered[chat_id].append(movie_code)
            movie_info_msg = f"{movie_code}  {movie_title}\n{movie_score}\n{movie_url}\n"
            movie_cover = await asyncio.to_thread(download_javdb_img, movie_cover_url)
            img_width, img_height = Image.open(io.BytesIO(movie_cover)).size
            if ((len(movie_cover) < 10*1024*1024) and ((img_width + img_height) < 10000) and (0.05 < img_height/img_width < 20)):
                    await self.application.bot.send_photo(chat_id=chat_id, photo=movie_cover)
            else:
                filename = movie_cover_url.split("/")[-1]
                await self.application.bot.send_document(chat_id=chat_id, document=movie_cover, filename=filename)
            movie_reviews = await asyncio.to_thread(get_javdb_reviews, msg['href'])
            if movie_reviews:
                for each in movie_reviews:
                    movie_info_msg += f'\n{each['stars']}  {each['time']}\n{each['comment']}'
            if len(movie_info_msg) > 4096:
                movie_info_msg = movie_info_msg[:4090] + '......'
            keyboard = [
                [InlineKeyboardButton("让我康康", callback_data=f'detail:{msg['href']}'), 
                 InlineKeyboardButton("换一个", callback_data='next:null')]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await update.effective_message.reply_text(movie_info_msg, reply_markup=reply_markup)
        except Exception as e:
            traceback.print_exc()
            await update.effective_message.reply_text('Error:\n' + str(e))

    async def get_javdb_details(self, update, href):
        try:
            chat_id = str(update.effective_message.chat.id)
            await self.application.bot.send_message(chat_id=chat_id, text='我知道你很急，但你先别急...')
            image_urls = await asyncio.to_thread(get_javdb_preview, href)
            for image_url in image_urls:
                preview_image = await asyncio.to_thread(download_javdb_img, image_url)
                img_width, img_height = Image.open(io.BytesIO(preview_image)).size
                if ((len(preview_image) < 10*1024*1024) and ((img_width + img_height) < 10000) and (0.05 < img_height/img_width < 20)):
                        await self.application.bot.send_photo(chat_id=chat_id, photo=preview_image)
                else:
                    filename = image_url.split("/")[-1]
                    await self.application.bot.send_document(chat_id=chat_id, document=preview_image, filename=filename)
                await asyncio.sleep(1.5)
        except Exception as e:
            traceback.print_exc()
            await self.application.bot.send_message(chat_id=chat_id, text=('Error:\n' + str(e)))

    async def get_alpha_news(self, context):
        try:
            if "last_news_ts" not in context.bot_data:
                context.bot_data['last_news_ts'] = time.time()
            alpha_news = await asyncio.to_thread(check_alpha, context.bot_data['last_news_ts'])
            context.bot_data['last_news_ts'] = alpha_news['ts']
        except Exception as e:
            traceback.print_exc()
            return
        if alpha_news['msg']:
            chat_id = str(context.job.chat_id)
            await self.application.bot.send_message(chat_id=chat_id, text=alpha_news['msg'])
        else:
            print("No alpha news found.")

    async def edit_reply(self, reply_message, reply_text):
        try:
            await reply_message.edit_text(text=reply_text, parse_mode='Markdown')
        except:
            await reply_message.edit_text(text=reply_text)

    @staticmethod
    def _is_escaped(text, index):
        backslashes = 0
        i = index - 1
        while i >= 0 and text[i] == "\\":
            backslashes += 1
            i -= 1
        return (backslashes % 2) == 1

    def _scan_markdown_state(self, text):
        state = {
            "code_fence": False,
            "latex_block_dollar": False,
            "latex_block_bracket": False,
            "latex_inline_paren": False,
            "latex_inline_dollar": False,
        }
        i = 0
        n = len(text)
        while i < n:
            if text.startswith("```", i) and (not self._is_escaped(text, i)):
                state["code_fence"] = not state["code_fence"]
                i += 3
                continue

            if state["code_fence"]:
                i += 1
                continue

            if text.startswith("\\[", i) and (not self._is_escaped(text, i)):
                state["latex_block_bracket"] = True
                i += 2
                continue
            if text.startswith("\\]", i) and (not self._is_escaped(text, i)):
                state["latex_block_bracket"] = False
                i += 2
                continue
            if text.startswith("\\(", i) and (not self._is_escaped(text, i)):
                state["latex_inline_paren"] = True
                i += 2
                continue
            if text.startswith("\\)", i) and (not self._is_escaped(text, i)):
                state["latex_inline_paren"] = False
                i += 2
                continue
            if text.startswith("$$", i) and (not self._is_escaped(text, i)):
                state["latex_block_dollar"] = not state["latex_block_dollar"]
                i += 2
                continue
            if text[i] == "$" and (not self._is_escaped(text, i)):
                state["latex_inline_dollar"] = not state["latex_inline_dollar"]
                i += 1
                continue

            i += 1
        return state

    @staticmethod
    def _state_balanced(state):
        return not (
            state["code_fence"]
            or state["latex_block_dollar"]
            or state["latex_block_bracket"]
            or state["latex_inline_paren"]
            or state["latex_inline_dollar"]
        )

    @staticmethod
    def _boundary_markers_from_state(state):
        closing = []
        reopening = []
        if state["code_fence"]:
            closing.append("\n```")
            reopening.append("```\n")
        if state["latex_block_dollar"]:
            closing.append("\n$$")
            reopening.append("$$\n")
        if state["latex_block_bracket"]:
            closing.append("\\]")
            reopening.append("\\[")
        if state["latex_inline_paren"]:
            closing.append("\\)")
            reopening.append("\\(")
        if state["latex_inline_dollar"]:
            closing.append("$")
            reopening.append("$")
        return "".join(closing), "".join(reopening)

    def _close_unfinished_markdown(self, text, max_len=4096):
        base = text or ""
        state = self._scan_markdown_state(base)
        closing, _ = self._boundary_markers_from_state(state)
        if closing:
            allowed_len = max(0, max_len - len(closing))
            base = base[:allowed_len]
            return base + closing
        return base[:max_len]

    def split_message_for_markdown(self, message, limit=4096):
        if len(message) <= limit:
            return message, ""

        split_idx = limit
        min_limit = max(1, int(limit * 0.65))
        separators = set(["\n", " ", "\t", "。", "，", ",", ".", "!", "?", "；", ";", "：", ":"])
        for idx in range(limit, min_limit, -1):
            if message[idx - 1] not in separators:
                continue
            state = self._scan_markdown_state(message[:idx])
            if self._state_balanced(state):
                split_idx = idx
                break

        head_raw = message[:split_idx]
        tail_raw = message[split_idx:]

        state = self._scan_markdown_state(head_raw)
        closing, reopening = self._boundary_markers_from_state(state)

        allowed_head_len = max(1, limit - len(closing))
        head_core = head_raw[:allowed_head_len]
        head = head_core + closing
        carry_over = head_raw[allowed_head_len:]
        tail = reopening + carry_over + tail_raw
        return head, tail

    def build_streaming_text(self, text):
        cursor = "▌"
        clean_text = self._close_unfinished_markdown(text, max_len=4096-len(cursor))
        if not clean_text.strip():
            return cursor
        return clean_text + cursor

    async def keep_typing(self, chat_id, stop_event, interval=4.0):
        while not stop_event.is_set():
            try:
                await self.application.bot.send_chat_action(chat_id=chat_id, action="typing")
            except Exception:
                pass
            try:
                await asyncio.wait_for(stop_event.wait(), timeout=interval)
            except asyncio.TimeoutError:
                continue

    def ensure_aichat_context(self, chat_id):
        if (chat_id not in self.aichat_contexts.keys()) or (not self.aichat_contexts[chat_id]):
            self.aichat_contexts[chat_id] = [
                {"role": "system", "content": "注意，可以结合上下文，但只需回答最新的一个问题，请使用中文。"}
            ]

    def estimate_message_size(self, content):
        if isinstance(content, str):
            return len(content)
        if isinstance(content, list):
            total_size = 0
            for item in content:
                if not isinstance(item, dict):
                    continue
                if item.get("type") == "text":
                    total_size += len(item.get("text", ""))
                elif item.get("type") == "image_url":
                    total_size += 800
                else:
                    total_size += 200
            return total_size
        return len(str(content))

    def trim_aichat_context(self, chat_id, max_context_size=10000):
        est_tokens = sum([self.estimate_message_size(message['content']) for message in self.aichat_contexts[chat_id]])
        while (len(self.aichat_contexts[chat_id]) > 2) and (est_tokens > max_context_size):
            del self.aichat_contexts[chat_id][1]
            est_tokens = sum([self.estimate_message_size(message['content']) for message in self.aichat_contexts[chat_id]])

    async def _download_file_bytes(self, tg_file):
        if hasattr(tg_file, "download_as_bytearray"):
            file_bytes = await tg_file.download_as_bytearray()
            return bytes(file_bytes)
        if hasattr(tg_file, "download_to_memory"):
            buffer = io.BytesIO()
            await tg_file.download_to_memory(out=buffer)
            return buffer.getvalue()
        raise RuntimeError("当前 telegram 版本不支持图片下载接口")

    async def _extract_image_data_url(self, message):
        if not message:
            return None
        mime_type = None
        tg_file = None
        if message.photo:
            mime_type = "image/jpeg"
            tg_file = await message.photo[-1].get_file()
        elif message.document and message.document.mime_type and message.document.mime_type.startswith("image/"):
            mime_type = message.document.mime_type
            tg_file = await message.document.get_file()
        if not tg_file:
            return None
        file_bytes = await self._download_file_bytes(tg_file)
        if len(file_bytes) > 8 * 1024 * 1024:
            raise ValueError("图片太大，请压缩到 8MB 以内再试。")
        base64_data = base64.b64encode(file_bytes).decode("ascii")
        return f"data:{mime_type};base64,{base64_data}"

    async def build_user_multimodal_content(self, message):
        message_text = (message.text or message.caption or "").strip()
        image_data_urls = []
        current_message_image = await self._extract_image_data_url(message)
        if current_message_image:
            image_data_urls.append(current_message_image)
        # 用户回复图片消息但自己只发了文本时，自动附上关联图片
        if (not image_data_urls) and message.reply_to_message:
            replied_image = await self._extract_image_data_url(message.reply_to_message)
            if replied_image:
                image_data_urls.append(replied_image)

        if not message_text and not image_data_urls:
            return None, None

        if image_data_urls:
            prompt_text = message_text if message_text else "请描述并分析这张图片。"
            content = [{"type": "text", "text": prompt_text}]
            for image_data_url in image_data_urls:
                content.append({"type": "image_url", "image_url": {"url": image_data_url}})
            if message_text:
                context_text = f"{message_text}\n[附带图片 {len(image_data_urls)} 张]"
            else:
                context_text = "[用户发送了图片]"
            return content, context_text

        return message_text, message_text

    @check_access
    async def start_command(self, update, context):
        chat_id = str(update.message.chat.id)
        if (chat_id not in self.filtered.keys()) and (chat_id not in self.aichat_contexts.keys()):
            await update.message.reply_text("欢迎使用")
        else:
            await update.message.reply_text("历史记录已清除,仿佛身体被掏空")
        self.filtered[chat_id] = []
        self.aichat_contexts[chat_id] = []

    @check_access
    async def pixiv_command(self, update, context):
        try:
            await self.get_pixiv_imgs(update, 'daily_r18')
        except Exception as e:
            traceback.print_exc()
            await update.effective_message.reply_text('Error:\n' + str(e))

    @check_access
    async def javdb_command(self, update, context):
        try:
            await self.get_javdb_cover(update)
        except Exception as e:
            traceback.print_exc()
            await update.effective_message.reply_text('Error:\n' + str(e))

    @check_access
    async def jandan_command(self, update, context):
        try:
            await self.get_jandan_imgs(update, context)
        except Exception as e:
            traceback.print_exc()
            await update.effective_message.reply_text('Error:\n' + str(e))

    async def ping_command(self, update, context):
        user_id = str(update.effective_message.from_user.id)
        chat_id = str(update.effective_message.chat.id)
        await update.message.reply_text(f"Pong! 你的userid是{user_id}，当前chatid是{chat_id}")

    async def javdb_button(self, update, context):
        query = update.callback_query
        await query.answer()
        data = query.data.split(':')
        action = data[0]
        param = data[1]
        if action == "next":
            await self.get_javdb_cover(update)
        elif action == "detail":
            await self.get_javdb_details(update, param)

    async def handle_message(self, update, context):
        incoming_message = update.effective_message
        if not incoming_message or not incoming_message.from_user:
            return
        user_id = str(incoming_message.from_user.id)
        if user_id not in self.whitelist:
            return
        typing_stop_event = None
        typing_task = None
        try:
            replied_message = incoming_message.reply_to_message
            if not replied_message or not replied_message.from_user or replied_message.from_user.id != context.bot.id:
                return

            user_content, user_context_text = await self.build_user_multimodal_content(incoming_message)
            if user_content is None:
                return

            chat_id = str(incoming_message.chat.id)
            message_id = incoming_message.message_id
            typing_stop_event = asyncio.Event()
            typing_task = asyncio.create_task(self.keep_typing(chat_id, typing_stop_event))
            fast_reply = await self.application.bot.send_message(
                chat_id=chat_id,
                text="容我想想...",
                reply_to_message_id=message_id,
            )

            self.ensure_aichat_context(chat_id)
            self.trim_aichat_context(chat_id)
            llm_messages = self.aichat_contexts[chat_id] + [{"role": "user", "content": user_content}]
            self.aichat_contexts[chat_id].append({"role": "user", "content": user_context_text})

            print('Waiting for LLM response...')
            full_text = ''    # 整个回答完整文本
            current_message = ''    # 最新一条消息
            buffer_text = ''    # 单次消息更新
            async for chunk in stream_ai_response(llm_messages):
                full_text += chunk
                current_message += chunk
                buffer_text += chunk
                if len(current_message) > 4096:
                    finished_message, current_message = self.split_message_for_markdown(current_message, limit=4096)
                    await self.edit_reply(fast_reply, finished_message)
                    await asyncio.sleep(1.5)  # MAX_MESSAGES_PER_SECOND_PER_CHAT = 1
                    if len(current_message.strip()) > 0:
                        new_message = current_message
                    else:
                        new_message = ''
                    fast_reply = await self.application.bot.send_message(chat_id=chat_id,
                        text=self.build_streaming_text(new_message), reply_to_message_id=message_id)
                    await asyncio.sleep(1.5)
                    buffer_text = ''
                    continue
                if len(buffer_text) > 100:
                    await self.edit_reply(fast_reply, self.build_streaming_text(current_message))
                    buffer_text = ''
                    await asyncio.sleep(3.5)  # MAX_MESSAGES_PER_MINUTE_PER_GROUP = 20
            reply_text = current_message if current_message.strip() else "（空回复）"
            if reply_text != "（空回复）":
                reply_text = self._close_unfinished_markdown(reply_text, max_len=4096)
            await self.edit_reply(fast_reply, reply_text[:4096])
            self.aichat_contexts[chat_id].append({"role": "assistant", "content": full_text})
            self.trim_aichat_context(chat_id)
            print('Reply sent successfully')
        except Exception as e:
            traceback.print_exc()
            await update.effective_message.reply_text('Error:\n' + str(e))
        finally:
            if typing_stop_event:
                typing_stop_event.set()
            if typing_task:
                try:
                    await typing_task
                except Exception:
                    pass

    def add_handlers(self):
        self.application.add_handler(CommandHandler('start', self.start_command))
        self.application.add_handler(CommandHandler('pixiv', self.pixiv_command))
        self.application.add_handler(CommandHandler('javdb', self.javdb_command))
        self.application.add_handler(CommandHandler('jandan', self.jandan_command))
        self.application.add_handler(CommandHandler('ping', self.ping_command))
        self.application.add_handler(CallbackQueryHandler(self.javdb_button))
        ai_chat_filters = (filters.TEXT | filters.PHOTO | filters.Document.IMAGE) & (~filters.COMMAND)
        self.application.add_handler(MessageHandler(ai_chat_filters, self.handle_message))

    async def job_wrapper(self, context):
        await self.get_jandan_imgs(update=None, context=context)

    def set_scheduler(self):
        GROUP_CHAT_ID = os.getenv('GROUP_CHAT_ID')
        self.application.job_queue.run_repeating(self.job_wrapper, interval=3693, chat_id=GROUP_CHAT_ID, name='scheduled jandan')
        self.application.job_queue.run_repeating(self.get_alpha_news, interval=300, chat_id=GROUP_CHAT_ID, name='scheduled news')

    def run(self):
        self.add_handlers()
        self.set_scheduler()
        print("Bot is running...")
        self.application.run_polling()

if __name__ == '__main__':
    load_dotenv()
    token = os.getenv('BOT_TOKEN')
    bot = TelegramBot(token)
    bot.run()
