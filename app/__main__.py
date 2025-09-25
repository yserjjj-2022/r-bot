# app/__main__.py - ОБНОВЛЕННАЯ ВЕРСИЯ С ПОДДЕРЖКОЙ КАРТИНОК

import telebot
import json
from decouple import config
from flask import Flask, request, send_from_directory # <-- 1. ДОБАВЛЕН ИМПОРТ
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

# --- Инициализация и настройка -- (здесь все без изменений) ---

# 1. Получаем переменные окружения
BOT_TOKEN = config("TELEGRAM_BOT_TOKEN")
GRAPH_PATH = config("GRAPH_PATH", default="/data/default_interview.json") 
SERVER_URL = config("SERVER_URL") 
WEBHOOK_PATH = f"/webhook/{BOT_TOKEN}"
WEBHOOK_URL = f"{SERVER_URL}{WEBHOOK_PATH}"

# 2. Инициализируем Flask-приложение (наш веб-сервер)
app = Flask(__name__)

# Маршрут для проверки здоровья от Amvera
@app.route('/', methods=['GET'])
def health_check():
    return "Bot is alive and listening!", 200

# 3. Инициализируем бота
bot = telebot.TeleBot(BOT_TOKEN)

# 4. Проверяем и копируем файл сценария
template_graph_path = '/app/data/default_interview.json'
if not os.path.exists(GRAPH_PATH):
    print(f"Файл сценария в {GRAPH_PATH} не найден. Копирую из шаблона...")
    try:
        # Убедимся, что директория /data существует
        os.makedirs(os.path.dirname(GRAPH_PATH), exist_ok=True)
        shutil.copy(template_graph_path, GRAPH_PATH)
        print("Копирование успешно завершено.")
    except Exception as e:
        print(f"ОШИБКА: Не удалось скопировать файл сценария: {e}")

# 5. Загружаем граф и регистрируем обработчики
graph_data = load_graph(GRAPH_PATH)
if graph_data:
    from app.modules.telegram_handler import register_handlers
    register_handlers(bot, graph_data)
    print("Обработчики успешно зарегистрированы.")
else:
    print("Критическая ошибка: не удалось загрузить граф сценариев. Бот не сможет обрабатывать команды.")


# --- НОВЫЙ БЛОК: ОБРАБОТКА СТАТИЧЕСКИХ ФАЙЛОВ (КАРТИНОК) ---

# 6. Создаем маршрут для отдачи изображений
@app.route('/images/<path:filename>')
def serve_image(filename):
    """
    Этот маршрут будет отдавать файлы из папки /data/images.
    Например, запрос на /images/car_repair.jpg вернет файл /data/images/car_repair.jpg
    """

    # Путь к директории с изображениями в постоянном хранилище
    image_directory = '/data/images'

    # Проверяем, существует ли папка, чтобы избежать ошибок
    if not os.path.isdir(image_directory):
        print(f"ПРЕДУПРЕЖДЕНИЕ: Директория для изображений {image_directory} не найдена.")
        return "Image directory not found", 404

    # Используем безопасную функцию Flask для отправки файла
    try:
        return send_from_directory(image_directory, filename)
    except FileNotFoundError:
        print(f"Файл не найден: {image_directory}/{filename}")
        return "File not found", 404


# --- Обработка входящих запросов от Telegram (старый код без изменений) ---

# 7. Создаем "маршрут", который будет слушать наш секретный путь
@app.route(WEBHOOK_PATH, methods=['POST'])
def webhook():
    if request.headers.get('content-type') == 'application/json':
        json_string = request.get_data().decode('utf-8')
        update = telebot.types.Update.de_json(json_string)
        bot.process_new_updates([update])
        return '', 200
    else:
        return 'Bad Request', 400

if __name__ == "__main__":
    # Запускаем встроенный веб-сервер Flask
    app.run(host='0.0.0.0', port=8443)