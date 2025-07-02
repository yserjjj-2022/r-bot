# app/__main__.py - Финальная версия для работы с Webhook

import telebot
import json
from decouple import config
from flask import Flask, request
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

# 1. Получаем переменные окружения
BOT_TOKEN = config("TELEGRAM_BOT_TOKEN")
# Путь к файлу в постоянном хранилище /data
GRAPH_PATH = config("GRAPH_PATH", default="/data/default_interview.json") 
# Публичный URL вашего сервера, который вы получили от Amvera
SERVER_URL = config("SERVER_URL") 
# Секретный путь, чтобы никто другой не мог отправлять запросы
# Мы используем токен, это безопасно
WEBHOOK_PATH = f"/webhook/{BOT_TOKEN}"
# Полный URL для вебхука
WEBHOOK_URL = f"{SERVER_URL}{WEBHOOK_PATH}"

# 2. Инициализируем Flask-приложение (наш веб-сервер)
app = Flask(__name__)

# 3. Инициализируем бота
bot = telebot.TeleBot(BOT_TOKEN)

# 4. Проверяем и копируем файл сценария (как мы обсуждали ранее)
template_graph_path = '/app/data/default_interview.json'
if not os.path.exists(GRAPH_PATH):
    print(f"Файл сценария в {GRAPH_PATH} не найден. Копирую из шаблона...")
    try:
        shutil.copy(template_graph_path, GRAPH_PATH)
        print("Копирование успешно завершено.")
    except Exception as e:
        print(f"ОШИБКА: Не удалось скопировать файл сценария: {e}")

# 5. Загружаем граф и регистрируем обработчики
graph_data = load_graph(GRAPH_PATH)
if graph_data:
    # Ваша функция register_handlers должна быть импортирована
    from app.modules.telegram_handler import register_handlers
    register_handlers(bot, graph_data)
    print("Обработчики успешно зарегистрированы.")
else:
    print("Критическая ошибка: не удалось загрузить граф сценариев. Бот не сможет обрабатывать команды.")

# --- Обработка входящих запросов от Telegram ---

# 6. Создаем "маршрут", который будет слушать наш секретный путь
@app.route(WEBHOOK_PATH, methods=['POST'])
def webhook():
    if request.headers.get('content-type') == 'application/json':
        json_string = request.get_data().decode('utf-8')
        update = telebot.types.Update.de_json(json_string)
        bot.process_new_updates([update])
        return '', 200
    else:
        return 'Bad Request', 400
