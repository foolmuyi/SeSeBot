import os
import io
import re
import json
import time
import traceback
from pixiv import *
from aichat import *
from jandan import *
from dotenv import load_dotenv
from PIL import Image
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, CallbackContext


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
        await update.effective_message.reply_text('我知道你很急，但你先别急...')
        try:
            chat_id = str(update.effective_message.chat.id)
            if chat_id not in self.filtered.keys():
                self.filtered[chat_id] = []
            msg = get_ranking(mode, self.filtered[chat_id], pages=2)
            artworks_url = msg['artworks_url']
            artworks_id = artworks_url.split("/")[-1]
            self.filtered[chat_id].append(artworks_id)
            for img_url in msg['imgs_url']:
                img = download_img(img_url, artworks_url)
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
        try:
            if chat_id not in self.filtered.keys():
                self.filtered[chat_id] = []
            comment = get_top_comments(self.filtered[chat_id])
            comment_id = comment['comment_id']
            self.filtered[chat_id].append(comment_id)
            for img_url in comment['img_urls']:
                filename = img_url.split('/')[-1]
                img = get_comment_img(img_url)
                img_width, img_height = Image.open(io.BytesIO(img)).size
                if img_url.split('.')[-1] == 'gif':
                    await self.application.bot.send_animation(chat_id=chat_id, animation=img, filename=filename)
                elif ((len(img) < 10*1024*1024) and ((img_width + img_height) < 10000) and (0.05 < img_height/img_width < 20)):
                    await self.application.bot.send_photo(chat_id=chat_id, photo=img)
                else:
                    await self.application.bot.send_document(chat_id=chat_id, document=img, filename=filename)
            hot_sub_comments = get_hot_sub_comments(comment_id)
            text2send = hot_sub_comments + '\n' + comment['comment_url']
            await self.application.bot.send_message(chat_id=chat_id, text=text2send)
        except Exception as e:
            traceback.print_exc()
            await self.application.bot.send_message(chat_id=chat_id, text=('Error:\n' + str(e)))

    async def edit_reply(self, reply_message, reply_text):
        try:
            await reply_message.edit_text(text=reply_text, parse_mode='Markdown')
        except:
            await reply_message.edit_text(text=reply_text)

    def split_message_with_codeblock(self, message):
        # 匹配所有三个反引号的位置（考虑转义情况）
        pattern = r'(?<!\\)(?:\\\\)*```'
        matches = list(re.finditer(pattern, message))
        
        # 状态跟踪
        in_code_block = False
        last_open_index = -1  # 记录最后一个未闭合代码块的起始位置
        
        # 遍历所有匹配的反引号
        for match in matches:
            if not in_code_block:
                # 遇到代码块开始
                in_code_block = True
                last_open_index = match.start()
            else:
                # 遇到代码块结束
                in_code_block = False
                last_open_index = -1  # 重置未闭合标记
        
        # 如果消息以未闭合代码块结束，则进行分割
        if in_code_block and last_open_index >= 0:
            # 第一条消息：从头到未闭合代码块开始之前（确保闭合）
            part1 = message[:last_open_index]
            # 第二条消息：从未闭合代码块开始到结束
            part2 = message[last_open_index:]
            return [part1, part2]
        
        # 无需分割
        return [message]

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

    async def handle_message(self, update, context):
        user_id = str(update.effective_message.from_user.id)
        if user_id not in self.whitelist:
            return
        message_text = update.effective_message.text or update.effective_message.caption
        if message_text:
            lower_message_text = message_text.lower()
        else:
            return  # 忽略不含文本的纯媒体消息
        keywords = ['色色', '色图', '涩涩', '涩图', '瑟瑟', '瑟图', 'xp', 'p站', 'lsp', 'pixiv']
        try:
            for keyword in keywords:
                if keyword in lower_message_text:
                    if self.check_working_time():
                        mode = 'daily'
                    else:
                        mode = 'daily_r18'

                    await self.get_pixiv_imgs(update, mode)
                    break
                else:
                    pass

            if update.effective_message.reply_to_message and update.effective_message.reply_to_message.from_user.id == context.bot.id:
                chat_id = str(update.effective_message.chat.id)
                message_id = update.effective_message.message_id
                fast_reply = await self.application.bot.send_message(chat_id=chat_id, text=("容我想想..."), 
                    reply_to_message_id=message_id)
                if chat_id not in self.aichat_contexts.keys():
                    # self.aichat_contexts[chat_id] = [{"role": "system", "content": "让我们说中文!"}]
                    self.aichat_contexts[chat_id] = []  # DeepSeek recommands "No system prompt" for R1
                self.aichat_contexts[chat_id].append({"role": "user", "content": message_text})
                est_tokens = sum([len(message['content']) for message in self.aichat_contexts[chat_id]])
                while (len(self.aichat_contexts[chat_id]) > 2) and (est_tokens > 5000):
                    self.aichat_contexts[chat_id] = self.aichat_contexts[chat_id][1:]
                    est_tokens = sum([len(message['content']) for message in self.aichat_contexts[chat_id]])
                print('Waiting for LLM response...')
                full_text = ''    # 整个回答完整文本
                current_message = ''    # 最新一条消息
                buffer_text = ''    # 单次消息更新
                for chunk in get_ai_response(self.aichat_contexts[chat_id]):
                    full_text += chunk
                    current_message += chunk
                    buffer_text += chunk
                    if current_message >= 4096:
                        finished_message = current_message[:4096]
                        current_message = current_message[4096:]
                        splited_messages = split_message_with_codeblock(finished_message)
                        if len(splited_messages) == 2:
                            finished_message = splited_messages[0]
                            current_message = splited_messages[1] + current_message
                        await self.edit_reply(fast_reply, finished_message)
                        time.sleep(1.5)  # MAX_MESSAGES_PER_SECOND_PER_CHAT = 1
                        fast_reply = await self.application.bot.send_message(chat_id=chat_id, 
                            text=current_message, reply_to_message_id=message_id)
                        time.sleep(1.5)
                        buffer_text = ''
                        continue
                    if len(buffer_text) > 100:
                        await self.edit_reply(fast_reply, current_message)
                        buffer_text = ''
                        time.sleep(3.5)  # MAX_MESSAGES_PER_MINUTE_PER_GROUP = 20
                reply_text = current_message + '\n(无语，和你说不下去，典型的碳基生物思维)'
                await self.edit_reply(fast_reply, reply_text[:4096])
                self.aichat_contexts[chat_id].append({"role": "assistant", "content": full_text})
                print('Reply sent successfully')
            else:
                pass
        except Exception as e:
            traceback.print_exc()
            await update.effective_message.reply_text('Error:\n' + str(e))

    def add_handlers(self):
        self.application.add_handler(CommandHandler('start', self.start_command))
        self.application.add_handler(CommandHandler('pixiv', self.pixiv_command))
        self.application.add_handler(CommandHandler('jandan', self.jandan_command))
        self.application.add_handler(CommandHandler('ping', self.ping_command))
        self.application.add_handler(MessageHandler(filters.ALL, self.handle_message))

    async def job_wrapper(self, context):
        await self.get_jandan_imgs(update=None, context=context)

    def set_scheduler(self):
        GROUP_CHAT_ID = os.getenv('GROUP_CHAT_ID')
        self.application.job_queue.run_repeating(self.job_wrapper, interval=3693, chat_id=GROUP_CHAT_ID, name='scheduled jandan')

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
