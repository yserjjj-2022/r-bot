# app/__main__.py - ВЕРСИЯ С HOT-RELOAD (ИСПРАВЛЕННАЯ)

import telebot
import json  # ← НУЖЕН ДЛЯ load_graph()
import os
import uuid
import shutil
from flask import Flask, request, send_from_directory

# Настройка чтения секретов из файлов (Amvera) или переменных окружения (локально)
from decouple import config as default_config, Config, RepositorySecret

if os.path.exists('/run/secrets'):
    # Чтение секретов из файлов в Amvera
    secret_repo = RepositorySecret('/run/secrets')
    config = Config(repository=secret_repo)
else:
    # Чтение из переменных окружения или .env файла (локально)
    config = default_config

# --- ИМПОРТИРУЕМ HOT-RELOAD ---
from app.modules.hot_reload import start_hot_reload, get_current_graph

# --- Вспомогательные функции ---
def load_graph(filename: str) -> dict:
    """DEPRECATED: используйте hot_reload.get_current_graph()"""
    try:
        with open(filename, 'r', encoding='utf-8') as f:
            return json.load(f)  # ← ВОТ ЗДЕСЬ НУЖЕН json
    except (FileNotFoundError, json.JSONDecodeError) as e:
        print(f"Ошибка загрузки графа {filename}: {e}")
        return None

# --- Инициализация ---
# Читаем секреты с защитой от лишних символов
BOT_TOKEN = config("TELEGRAM_BOT_TOKEN").strip()
GRAPH_PATH = config("GRAPH_PATH", default="/data/default_interview.json")
SERVER_URL = config("SERVER_URL")

# Безопасное создание webhook URL без использования BOT_TOKEN
WEBHOOK_SECRET = config("WEBHOOK_SECRET", default=str(uuid.uuid4())).strip()
WEBHOOK_PATH = f"/webhook/{WEBHOOK_SECRET}"
WEBHOOK_URL = f"{SERVER_URL}{WEBHOOK_PATH}"

app = Flask(__name__)

@app.route('/', methods=['GET'])
def health_check():
    return "Bot is alive and listening!", 200

bot = telebot.TeleBot(BOT_TOKEN)

# --- ПОДГОТОВКА ФАЙЛА СЦЕНАРИЯ ---
template_graph_path = '/app/data/default_interview.json'
if not os.path.exists(GRAPH_PATH):
    print(f"Файл сценария в {GRAPH_PATH} не найден. Копирую из шаблона...")
    try:
        os.makedirs(os.path.dirname(GRAPH_PATH), exist_ok=True)
        shutil.copy(template_graph_path, GRAPH_PATH)
        print("Копирование успешно завершено.")
    except Exception as e:
        print(f"ОШИБКА: Не удалось скопировать файл сценария: {e}")

# --- HOT-RELOAD СИСТЕМА ---
print("=== ЗАПУСК HOT-RELOAD СИСТЕМЫ ===")
start_hot_reload(GRAPH_PATH, poll_interval=30)

# Получаем актуальный граф
graph_data = get_current_graph()

if graph_data:
    from app.modules.telegram_handler import register_handlers
    register_handlers(bot, graph_data)
    print("Обработчики успешно зарегистрированы.")
else:
    print("Критическая ошибка: не удалось загрузить граф сценариев.")

# --- ОБРАБОТКА КАРТИНОК ---
@app.route('/images/<path:filename>')
def serve_image(filename):
    image_directory = '/data/images'
    if not os.path.isdir(image_directory):
        print(f"ПРЕДУПРЕЖДЕНИЕ: Директория для изображений {image_directory} не найдена.")
        return "Image directory not found", 404
    
    try:
        return send_from_directory(image_directory, filename)
    except FileNotFoundError:
        print(f"Файл не найден: {image_directory}/{filename}")
        return "File not found", 404

# --- WEBHOOK ---
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
    app.run(host='0.0.0.0', port=8443)
