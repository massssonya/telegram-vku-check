from telegram.ext import CommandHandler
from telegram import Update
from telegram.ext import ContextTypes

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Привет! Пришли JSON файл своей услуги. Я проанализирую сценарии")

start_handler = CommandHandler("start", start)
