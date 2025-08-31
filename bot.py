import os
import asyncio
from dotenv import load_dotenv
from telegram.ext import Application

from handlers.start import start_handler
from handlers.json_handler import json_handler

load_dotenv()

TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")

if not TELEGRAM_BOT_TOKEN:
    print("Error: TELEGRAM_BOT_TOKEN environment variable not set.")
    exit(1)

application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

# Регистрируем handlers
application.add_handler(start_handler)
application.add_handler(json_handler)

# Нужно инициализировать Application (один раз при старте)
async def init_bot():
    await application.initialize()

asyncio.run(init_bot())
