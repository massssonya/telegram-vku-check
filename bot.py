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

# Создаем application глобально
application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

# Регистрируем handlers
application.add_handler(start_handler)
application.add_handler(json_handler)

# Инициализация при запуске
def initialize_bot():
    """Инициализирует бота синхронно"""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    
    try:
        loop.run_until_complete(application.initialize())
        loop.run_until_complete(application.start())
        print("Bot initialized successfully")
    except Exception as e:
        print(f"Error initializing bot: {e}")
    finally:
        # Не закрываем loop здесь, так как он может понадобиться для вебхуков
        pass

# Инициализируем при импорте
initialize_bot()