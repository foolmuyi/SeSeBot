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
  -  `PIXIV_COOKIE`: your Pixiv cookie
  -  `CF_WORKER_URL`: your Cloudflare worker url
  -  `CF_AUTH_KEY`: your Cloudflare worker authentication key
  -  LLM API key from Grok, OpenAI or any other provider
- Create `whitelist.json` and fill it with the Telegram `chat_id` of yourself and your friends.

## Usage
#### Run in Terminal
`Python3 sesebot.py`

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