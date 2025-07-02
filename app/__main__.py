import telebot
import json
from decouple import config # <-- Импортируем config
from app.modules.telegram_handler import register_handlers

def load_graph(filename: str) -> dict:
    try:
        with open(filename, 'r', encoding='utf-8') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError) as e:
        print(f"Ошибка загрузки графа {filename}: {e}")
        return None

def main():
    # Комментарий: Получаем токен. config() сама позаботится о .env
    bot_token = config("TELEGRAM_BOT_TOKEN", default=None)
    if not bot_token:
        print("Ошибка: Токен не найден. Проверьте ваш .env файл.")
        return

    graph_data = load_graph("/data/default_interview.json")
    if not graph_data:
        print("Не удалось запустить бота без графа сценариев.")
        return

    bot = telebot.TeleBot(bot_token)
    register_handlers(bot, graph_data)

    print("Бот запущен и готов вести по графу...")
    bot.infinity_polling()

if __name__ == "__main__":
    main()
