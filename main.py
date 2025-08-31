import os
import asyncio
from flask import Flask, request
import telegram
from bot import application  # импорт Telegram Application

app = Flask(__name__)

@app.route("/")
def hello_world():
    name = os.environ.get("NAME", "World")
    return f"Hello {name}!"

@app.route("/telegram", methods=["POST"])
def telegram_webhook():
    """Handles incoming Telegram updates (синхронный Flask)."""
    update = telegram.Update.de_json(request.get_json(force=True), application.bot)

    # запускаем асинхронный метод через asyncio.run
    asyncio.run(application.process_update(update))

    return "ok"

if __name__ == "__main__":
    # Flask dev server (в проде лучше Gunicorn/uWSGI + gevent/uvicorn)
    app.run(debug=True, host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
