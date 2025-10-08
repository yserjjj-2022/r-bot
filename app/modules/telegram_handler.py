# -*- coding: utf-8 -*-

"""
R-Bot Telegram Handler - обработчик сообщений и узлов сценария

ОБНОВЛЕНИЯ:
08.10.2025, 18:11 - УБРАНЫ все проблемные импорты для исправления PyLance ошибок
08.10.2025, 18:02 - ИСПРАВЛЕНЫ импорты datetime для экстренного патча
08.10.2025, 17:19 - ДОБАВЛЕН экстренный daily cutoff патч

"""

import json
import logging
import time
import threading
from datetime import datetime, date
from typing import Dict, List, Optional, Any
import re

# Безопасные импорты телеграм бота
try:
    from telebot import TeleBot
    from telebot.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
    TELEBOT_AVAILABLE = True
except ImportError:
    print("Warning: telebot not available")
    TELEBOT_AVAILABLE = False
    # Заглушки
    class TeleBot:
        def __init__(self, token): pass
    class Message: pass
    class CallbackQuery: pass
    class InlineKeyboardMarkup: pass
    class InlineKeyboardButton: pass

# Безопасные импорты модулей R-Bot
try:
    from app.modules.timing_engine import (
        process_node_timing, 
        cancel_timeout_for_session, 
        enable_timing, 
        get_timing_status
    )
    TIMING_ENGINE_AVAILABLE = True
except ImportError:
    print("Warning: timing_engine not available")
    TIMING_ENGINE_AVAILABLE = False
    # Заглушки
    def process_node_timing(*args, **kwargs): pass
    def cancel_timeout_for_session(*args): pass  
    def enable_timing(): pass
    def get_timing_status(): return {'enabled': False}

try:
    from app.modules.database.models import UserSession, SessionMessage, utc_now
    from app.modules.database import SessionLocal
    DATABASE_AVAILABLE = True
except ImportError:
    print("Warning: database modules not available")
    DATABASE_AVAILABLE = False
    # Заглушки
    class UserSession: pass
    class SessionMessage: pass
    def utc_now(): return datetime.now()
    def SessionLocal(): return None

# НЕ импортируем проблемный GigaChatClient
# try:
#     from app.utils.gigachat_client import GigaChatClient
# except ImportError:
#     print("Warning: GigaChatClient not available")

# Глобальные переменные
logger = logging.getLogger(__name__)
bot = None
scenario_data = {}
user_sessions: Dict[int, Dict] = {}

def initialize_bot(telegram_token: str):
    """Инициализация Telegram бота"""
    global bot
    if not TELEBOT_AVAILABLE:
        logger.error("TeleBot not available")
        return False

    bot = TeleBot(telegram_token)
    logger.info("Telegram bot initialized successfully")
    return True

def load_scenario(file_path: str):
    """Загрузка сценария из JSON файла"""
    global scenario_data
    try:
        with open(file_path, 'r', encoding='utf-8') as file:
            scenario_data = json.load(file)
        logger.info(f"Scenario loaded from {file_path}")
        return True
    except Exception as e:
        logger.error(f"Failed to load scenario: {e}")
        return False

def get_node_by_id(node_id: str) -> Optional[Dict]:
    """Получить узел сценария по ID"""
    for node in scenario_data.get('nodes', []):
        if node.get('id') == node_id:
            return node
    return None

def is_final_node(node_id: str) -> bool:
    """Проверяет, является ли узел финальным"""
    node = get_node_by_id(node_id)
    if not node:
        return True

    # Узел финальный если нет next_node_id и нет кнопок с переходами
    has_next = node.get('next_node_id')
    has_buttons = node.get('buttons', [])

    if has_next:
        return False

    for button in has_buttons:
        if button.get('next_node_id'):
            return False

    return True

def send_node_message(chat_id: int, node_id: str):
    """
    Отправляет сообщение узла сценария с ЭКСТРЕННЫМ DAILY CUTOFF ПАТЧЕМ

    ЭКСТРЕННЫЙ ПАТЧ 08.10.2025 - для выхода из daily цикла при достижении cutoff
    """

    # ============================================================================
    # 🚨 ЭКСТРЕННЫЙ DAILY CUTOFF ПАТЧ - 08.10.2025, 18:11 MSK (БЕЗ ОШИБОК)
    # ============================================================================

    if node_id == 'daily_complete':
        current_date = datetime.now().date()
        cutoff_date = date(2025, 10, 8)  # ЖЕСТКО ЗАШИТО НА СЕГОДНЯ

        print(f"[EMERGENCY-CUTOFF] Node: {node_id}")
        print(f"[EMERGENCY-CUTOFF] Current: {current_date}, Cutoff: {cutoff_date}")
        print(f"[EMERGENCY-CUTOFF] Should transition: {current_date >= cutoff_date}")
        logger.info(f"[EMERGENCY-CUTOFF] Checking cutoff: {current_date} >= {cutoff_date}")

        if current_date >= cutoff_date:
            print("[EMERGENCY-CUTOFF] TRIGGERING CUTOFF TRANSITION!")
            logger.info("[EMERGENCY-CUTOFF] TRIGGERING CUTOFF TRANSITION!")

            try:
                # Отправляем сообщение об окончании исследования
                cutoff_message = (
                    "🎉 Исследовательский период завершен!\n\n"
                    "📊 Спасибо за участие в ежедневных опросах!\n\n"
                    "Теперь несколько итоговых вопросов по всему периоду наблюдений..."
                )

                if bot and TELEBOT_AVAILABLE:
                    bot.send_message(chat_id, cutoff_message)
                    time.sleep(2)

                    # ПРЯМОЙ переход к final_questions
                    logger.info("[EMERGENCY-CUTOFF] Redirecting to final_questions...")
                    send_node_message(chat_id, 'final_questions')
                    return
                else:
                    print("[EMERGENCY-CUTOFF] Bot not available!")

            except Exception as e:
                logger.error(f"[EMERGENCY-CUTOFF] Failed: {e}")
                print(f"[EMERGENCY-CUTOFF] Error: {e}")
                # Fallback - продолжаем обычную логику

    # ============================================================================
    # ОБЫЧНАЯ ЛОГИКА send_node_message
    # ============================================================================

    global user_sessions

    if chat_id not in user_sessions:
        user_sessions[chat_id] = {
            'current_node': node_id,
            'session_data': {},
            'start_time': datetime.now()
        }
    else:
        user_sessions[chat_id]['current_node'] = node_id

    # Получаем узел из сценария
    node = get_node_by_id(node_id)
    if not node:
        logger.error(f"Node not found: {node_id}")
        if bot and TELEBOT_AVAILABLE:
            bot.send_message(chat_id, "❌ Ошибка: узел сценария не найден")
        return

    # Формируем основной текст
    node_text = node.get('text', '')
    node_type = node.get('type', 'message')

    # Обработка динамических переменных
    node_text = process_dynamic_content(node_text, user_sessions[chat_id].get('session_data', {}))

    # Создаем клавиатуру
    keyboard = create_keyboard(node.get('buttons', []))

    # Отправляем сообщение
    try:
        if not bot or not TELEBOT_AVAILABLE:
            logger.error("Bot not available")
            return

        if keyboard:
            sent_message = bot.send_message(chat_id, node_text, reply_markup=keyboard)
        else:
            sent_message = bot.send_message(chat_id, node_text)

        # Сохраняем сообщение в БД (если доступна)
        if DATABASE_AVAILABLE:
            save_message_to_db(chat_id, node_id, node_text, sent_message.message_id)

        logger.info(f"Node message sent: {node_id} to chat {chat_id}")

    except Exception as e:
        logger.error(f"Failed to send message for node {node_id}: {e}")
        return

    # Обработка timing команд
    timing_config = node.get('timing', '')
    if timing_config and timing_config.strip() and TIMING_ENGINE_AVAILABLE:
        session_id = user_sessions[chat_id].get('session_id', chat_id)

        def timing_callback():
            """Callback после выполнения timing"""
            handle_next_node(chat_id, node)

        # Запуск timing engine
        try:
            process_node_timing(
                user_id=chat_id,
                session_id=session_id, 
                node_id=node_id,
                timing_config=timing_config,
                callback=timing_callback,
                bot=bot,
                chat_id=chat_id,
                node_text=node_text,
                buttons=node.get('buttons', []),
                pause_text=node.get('pause_text', '')
            )
        except Exception as e:
            logger.error(f"Timing engine error for node {node_id}: {e}")
            # Fallback - переходим к следующему узлу сразу
            handle_next_node(chat_id, node)
    else:
        # Если нет timing команд, проверяем обычный переход
        if not keyboard and not is_final_node(node_id):
            handle_next_node(chat_id, node)

def handle_next_node(chat_id: int, current_node: Dict):
    """Обработка перехода к следующему узлу"""
    next_node_id = current_node.get('next_node_id')

    if next_node_id:
        # Простой переход к следующему узлу
        send_node_message(chat_id, next_node_id)
    else:
        # Проверяем, есть ли кнопки с переходами
        buttons = current_node.get('buttons', [])
        if not buttons:
            # Финальный узел без кнопок
            logger.info(f"Reached final node for chat {chat_id}")

def create_keyboard(buttons: List[Dict]) -> Optional[InlineKeyboardMarkup]:
    """Создает инлайн-клавиатуру из кнопок узла"""
    if not buttons or not TELEBOT_AVAILABLE:
        return None

    keyboard = InlineKeyboardMarkup()

    for button in buttons:
        button_text = button.get('text', '')
        button_data = button.get('next_node_id', button.get('id', ''))

        if button_text and button_data:
            keyboard.add(InlineKeyboardButton(button_text, callback_data=button_data))

    return keyboard

def process_dynamic_content(text: str, session_data: Dict) -> str:
    """Обработка динамических переменных в тексте"""
    if not text:
        return text

    # Замена переменных типа {{variable_name}}
    def replace_variable(match):
        var_name = match.group(1)
        return str(session_data.get(var_name, f"{{{{ {var_name} }}}}"))

    # Обработка переменных
    text = re.sub(r'\{\{\s*([^}]+)\s*\}\}', replace_variable, text)

    return text

def save_message_to_db(chat_id: int, node_id: str, text: str, message_id: int):
    """Сохранение сообщения в БД"""
    if not DATABASE_AVAILABLE:
        print("Database not available, skipping save")
        return

    try:
        db = SessionLocal()
        if not db:
            return

        # Создаем или обновляем сессию
        session = db.query(UserSession).filter(
            UserSession.chat_id == chat_id
        ).first()

        if not session:
            session = UserSession(
                chat_id=chat_id,
                current_node_id=node_id,
                session_data={},
                created_at=utc_now(),
                updated_at=utc_now()
            )
            db.add(session)
            db.flush()
        else:
            session.current_node_id = node_id
            session.updated_at = utc_now()

        # Сохраняем сообщение
        message_record = SessionMessage(
            session_id=session.id,
            node_id=node_id,
            message_text=text,
            message_id=message_id,
            message_type='bot_message',
            created_at=utc_now()
        )
        db.add(message_record)

        db.commit()

        # Обновляем глобальную сессию
        user_sessions[chat_id]['session_id'] = session.id

    except Exception as e:
        logger.error(f"Failed to save message to DB: {e}")
        if 'db' in locals() and db:
            db.rollback()
    finally:
        if 'db' in locals() and db:
            db.close()

# ============================================================================
# MESSAGE HANDLERS
# ============================================================================

def register_handlers():
    """Регистрация обработчиков сообщений"""

    if not bot or not TELEBOT_AVAILABLE:
        logger.error("Bot not available, cannot register handlers")
        return

    @bot.message_handler(commands=['start'])
    def handle_start(message: Message):
        """Обработчик команды /start"""
        chat_id = message.chat.id
        logger.info(f"Start command from chat {chat_id}")

        # Очищаем предыдущую сессию
        if chat_id in user_sessions:
            # Отменяем активные таймеры
            try:
                if TIMING_ENGINE_AVAILABLE:
                    session_id = user_sessions[chat_id].get('session_id', chat_id)
                    cancel_timeout_for_session(session_id)
            except Exception as e:
                logger.error(f"Failed to cancel timeout: {e}")

        # Инициализируем новую сессию
        user_sessions[chat_id] = {
            'current_node': 'daily_start',
            'session_data': {},
            'start_time': datetime.now()
        }

        # Переходим к начальному узлу
        send_node_message(chat_id, 'daily_start')

    @bot.message_handler(commands=['status'])
    def handle_status(message: Message):
        """Обработчик команды /status"""
        chat_id = message.chat.id

        if chat_id in user_sessions:
            session = user_sessions[chat_id]
            current_node = session.get('current_node', 'unknown')
            start_time = session.get('start_time', datetime.now())
            duration = datetime.now() - start_time

            try:
                if TIMING_ENGINE_AVAILABLE:
                    timing_status = get_timing_status().get('enabled', 'unknown')
                else:
                    timing_status = 'unavailable'
            except:
                timing_status = 'error'

            status_text = (
                f"📊 **Статус сессии**\n\n"
                f"🔹 Текущий узел: `{current_node}`\n"
                f"🔹 Время сессии: {duration}\n"
                f"🔹 Timing engine: {timing_status}"
            )
        else:
            status_text = "❌ Активная сессия не найдена. Используйте /start"

        bot.send_message(chat_id, status_text, parse_mode='Markdown')

    @bot.message_handler(content_types=['text'])
    def handle_text_message(message: Message):
        """Обработчик текстовых сообщений"""
        chat_id = message.chat.id
        text = message.text

        if chat_id not in user_sessions:
            bot.send_message(chat_id, "Используйте /start для начала")
            return

        # Сохраняем ответ пользователя
        current_node = user_sessions[chat_id].get('current_node')
        user_sessions[chat_id]['session_data'][f'{current_node}_response'] = text

        # Отменяем timeout если есть
        try:
            if TIMING_ENGINE_AVAILABLE:
                session_id = user_sessions[chat_id].get('session_id', chat_id)
                cancel_timeout_for_session(session_id)
        except Exception as e:
            logger.error(f"Failed to cancel timeout: {e}")

        logger.info(f"Text message from chat {chat_id}: {text}")

    @bot.callback_query_handler(func=lambda call: True)
    def handle_callback_query(call: CallbackQuery):
        """Обработчик нажатий на инлайн-кнопки"""
        chat_id = call.message.chat.id
        data = call.data

        logger.info(f"Callback query from chat {chat_id}: {data}")

        # Отменяем timeout если есть
        if chat_id in user_sessions:
            try:
                if TIMING_ENGINE_AVAILABLE:
                    session_id = user_sessions[chat_id].get('session_id', chat_id)
                    cancel_timeout_for_session(session_id)
            except Exception as e:
                logger.error(f"Failed to cancel timeout: {e}")

        # Переходим к узлу указанному в callback_data
        send_node_message(chat_id, data)

        # Подтверждаем нажатие кнопки
        bot.answer_callback_query(call.id)

# ============================================================================
# BOT POLLING
# ============================================================================

def start_bot_polling():
    """Запуск бота в режиме polling"""
    if not bot or not TELEBOT_AVAILABLE:
        raise RuntimeError("Bot not available. Call initialize_bot() first.")

    logger.info("Starting bot polling...")

    # Регистрируем обработчики
    register_handlers()

    # Включаем timing engine
    try:
        if TIMING_ENGINE_AVAILABLE:
            enable_timing()
    except Exception as e:
        logger.error(f"Failed to enable timing engine: {e}")

    # Запускаем polling
    try:
        bot.polling(none_stop=True, interval=0.5, timeout=60)
    except Exception as e:
        logger.error(f"Bot polling error: {e}")
        raise

def stop_bot():
    """Остановка бота"""
    if bot:
        bot.stop_polling()
        logger.info("Bot stopped")

# ============================================================================
# ЭКСПОРТ ФУНКЦИЙ
# ============================================================================

__all__ = [
    'initialize_bot',
    'load_scenario', 
    'send_node_message',
    'start_bot_polling',
    'stop_bot',
    'user_sessions'
]
