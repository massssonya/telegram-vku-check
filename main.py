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
    try:
        update = telegram.Update.de_json(request.get_json(force=True), application.bot)
        
        # Создаем новую event loop для каждого запроса
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        try:
            # Запускаем асинхронную задачу
            loop.run_until_complete(application.process_update(update))
            return "ok"
        finally:
            # Корректно закрываем loop
            loop.close()
            
    except Exception as e:
        print(f"Error processing update: {e}")
        return "error", 500

if __name__ == "__main__":
    # Flask dev server (в проде лучше Gunicorn/uWSGI + gevent/uvicorn)
    app.run(debug=True, host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))