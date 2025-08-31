from telegram.ext import MessageHandler, filters, ContextTypes
from telegram import Update, error
from services.json_analysis import process_json_file

async def handle_json_file(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    document = update.message.document

    if document.mime_type == 'application/json' or (document.file_name and document.file_name.endswith('.json')):
        await process_json_file(update, context, document)
    else:
        await update.message.reply_text("Получен файл, но это не JSON.")

json_handler = MessageHandler(filters.Document.ALL, handle_json_file)
