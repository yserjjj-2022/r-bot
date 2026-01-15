# app/__main__.py - Консолидированная версия для Amvera (env-based secrets + безопасный webhook + авто-регистрация)

import telebot
import json
import os
import uuid
import shutil
from flask import Flask, request, send_from_directory
from decouple import config

# --- ИМПОРТИРУЕМ HOT-RELOAD ---
from app.modules.hot_reload import start_hot_reload, get_current_graph

# --- Вспомогательные функции ---
def load_graph(filename: str) -> dict:
    """DEPRECATED: используйте hot_reload.get_current_graph()"""
    try:
        with open(filename, 'r', encoding='utf-8') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError) as e:
        print(f"Ошибка загрузки графа {filename}: {e}")
        return None

# --- Инициализация конфигурации ---
# Согласно документации Amvera, и переменные, и секреты доступны через окружение
BOT_TOKEN = config("TELEGRAM_BOT_TOKEN")
GRAPH_PATH = config("GRAPH_PATH", default="/data/default_interview.json")
# [MODIFIED] SERVER_URL is now optional for local development
SERVER_URL = config("SERVER_URL", default=None)
WEBHOOK_SECRET = config("WEBHOOK_SECRET", default=str(uuid.uuid4()))

# Проверка наличия критически важных переменных
if not BOT_TOKEN:
    raise ValueError("TELEGRAM_BOT_TOKEN must be set in Amvera secrets/environment variables.")

app = Flask(__name__)

@app.route('/', methods=['GET'])
def health_check():
    return "Bot is alive and listening!", 200

bot = telebot.TeleBot(BOT_TOKEN)

# --- WEBHOOK vs POLLING Logic ---
if SERVER_URL:
    # Безопасный путь и URL вебхука (не используем BOT_TOKEN в URL)
    WEBHOOK_PATH = f"/webhook/{WEBHOOK_SECRET}"
    WEBHOOK_URL = f"{SERVER_URL}{WEBHOOK_PATH}"
    
    # --- Регистрация вебхука в Telegram ---
    try:
        print("Setting webhook...")
        bot.remove_webhook()
        bot.set_webhook(url=WEBHOOK_URL)
        print(f"Webhook successfully set to: {WEBHOOK_URL}")
    except Exception as e:
        print(f"Failed to set webhook: {e}")
else:
    print("SERVER_URL not set. Running in POLLING mode (local development).")
    try:
        bot.remove_webhook()
    except:
        pass

# --- ПОДГОТОВКА ФАЙЛА СЦЕНАРИЯ ---
template_graph_path = '/app/data/default_interview.json'
# For local run, if absolute path starts with /data, it might be an issue if folder doesn't exist
# But we trust the user has setup env or folder structure locally.
if not os.path.exists(GRAPH_PATH):
    print(f"Файл сценария в {GRAPH_PATH} не найден. Копирую из шаблона...")
    try:
        os.makedirs(os.path.dirname(GRAPH_PATH), exist_ok=True)
        # Check if template exists
        if os.path.exists(template_graph_path):
            shutil.copy(template_graph_path, GRAPH_PATH)
            print("Копирование успешно завершено.")
        else:
            print(f"Template not found at {template_graph_path}, skipping copy.")
    except Exception as e:
        print(f"ОШИБКА: Не удалось скопировать файл сценария: {e}")

# --- HOT-RELOAD СИСТЕМА ---
print("=== ЗАПУСК HOT-RELOAD СИСТЕМЫ ===")
start_hot_reload(GRAPH_PATH, poll_interval=30)

# Получаем актуальный граф
graph_data = get_current_graph()

if graph_data:
    # Import register_handlers inside main to avoid circular imports if any
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

# --- WEBHOOK endpoint ---
if SERVER_URL:
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
    if SERVER_URL:
        app.run(host='0.0.0.0', port=8443)
    else:
        print("Starting infinite polling...")
        bot.infinity_polling()
