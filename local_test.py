# local_test.py - Специальный файл для локального тестирования в режиме Polling

import telebot
import json
from decouple import config
import os
import shutil

# --- Вспомогательные функции (остаются без изменений) ---
def load_graph(filename: str) -> dict:
    try:
        with open(filename, 'r', encoding='utf-8') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError) as e:
        print(f"Ошибка загрузки графа {filename}: {e}")
        return None

# --- Инициализация и настройка ---

# 1. Получаем переменные окружения из вашего файла .env
# Нам больше не нужен SERVER_URL!
BOT_TOKEN = config("TELEGRAM_BOT_TOKEN")
GRAPH_PATH = config("GRAPH_PATH", default="data/default_interview.json")

# 2. Инициализируем бота
bot = telebot.TeleBot(BOT_TOKEN)

# 3. Проверяем и копируем файл сценария, если нужно.
# Эта логика полезна и для локального запуска.
template_graph_path = 'data/default_interview.json'
if not os.path.exists(GRAPH_PATH):
    print(f"Файл сценария в {GRAPH_PATH} не найден. Копирую из шаблона...")
    try:
        shutil.copy(template_graph_path, GRAPH_PATH)
        print("Копирование успешно завершено.")
    except Exception as e:
        print(f"ОШИБКА: Не удалось скопировать файл сценария: {e}")

# 4. Загружаем граф и регистрируем обработчики
graph_data = load_graph(GRAPH_PATH)
if graph_data:
    # Ваша функция register_handlers должна быть импортирована
    from app.modules.telegram_handler import register_handlers
    register_handlers(bot, graph_data)
    print("Обработчики успешно зарегистрированы.")
else:
    print("Критическая ошибка: не удалось загрузить граф сценариев. Бот не сможет обрабатывать команды.")
    # Выходим, если граф не загружен
    exit()

# --- Финальный шаг: Запуск ---
if __name__ == "__main__":
    print("Удаляем старый вебхук, чтобы Telegram не пытался его использовать...")
    bot.remove_webhook()
    
    print("Бот запущен в режиме Polling. Нажмите Ctrl+C для остановки.")
    # Запускаем бота в режиме "звонков" в Telegram. Это блокирующая операция.
    bot.infinity_polling()

