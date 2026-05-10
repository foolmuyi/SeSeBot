# SeSeBot

Telegram bot for ~~downloading Setu~~ and chatting with LLM.

---

## Installation
```Shell
git clone https://github.com/foolmuyi/SeSeBot.git
cd SeSeBot
python3 -m venv venv
source ./venv/bin/activate
pip3 install -r requirements.txt
```

## Configuration
- Create `.env` and set the following environment variables:
  -  `BOT_TOKEN`: your Telegram bot token
  -  `GROUP_CHAT_ID`: the `chat_id` of your Telegram group
  -  `BOT_TIMEZONE` (optional): timezone for reminders, default `Asia/Shanghai`
  -  `LOG_LEVEL` (optional): logging level, default `INFO`
  -  `PIXIV_COOKIE`: your Pixiv cookie
  -  `CF_PIXIV_URL`: your Pixiv Cloudflare worker url
  -  `CF_PIXIV_KEY`: your Pixiv Cloudflare worker authentication key
  -  `CF_BNALPHA_URL`: your bnalpha Cloudflare worker url
  -  `CF_BNALPHA_KEY`: your bnalpha Cloudflare worker authentication key
  -  LLM API key from Grok, OpenAI or any other provider
- To enable image generation/editing, set these code-level constants:
  - `IMAGE_UNDERSTANDING_MODEL` for image understanding (image -> text)
  - `IMAGE_GENERATION_MODEL` for image generation/editing (text -> image, or image+text -> image; empty string means disabled)
  - Optional: `IMAGE_GENERATION_SIZE`, `IMAGE_GENERATION_QUALITY`, `IMAGE_GENERATION_STYLE`, `IMAGE_GENERATION_RESPONSE_FORMAT`
- Create `whitelist.json` and fill it with the Telegram `chat_id` of yourself and your friends.

## Usage
#### Run in Terminal
`Python3 sesebot.py`

#### Reminder command
`/remind <natural language>`
Example: `/remind 明天早上8点提醒我开会`

#### Image generation command
`/draw <prompt>`
Examples:
- `/draw 傍晚海边的赛博朋克城市，电影感构图`
- reply to an image and send `/draw 改成水彩插画风格`

#### Poetry command
`/shici`

#### Run as systemd service
```INI
[Unit]
Description=Telegram SeSe Bot
After=network.target

[Service]
Type=simple
User=ubuntu
WorkingDirectory=/home/ubuntu/SeSeBot
ExecStart=/home/ubuntu/SeSeBot/venv/bin/python3 -u /home/ubuntu/SeSeBot/sesebot.py
Restart=always
RestartSec=30

[Install]
WantedBy=multi-user.target
```

#### Prevent unattended upgrades from restarting this service (Ubuntu)
Replace `sesebot.service` if your unit name is different.
```Shell
echo '$nrconf{override_rc}{qr(^sesebot\.service$)} = 0;' | sudo tee /etc/needrestart/conf.d/99-sesebot.conf
```
