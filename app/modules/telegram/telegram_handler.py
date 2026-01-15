# app/modules/telegram/telegram_handler.py

import asyncio
from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import ContextTypes
from app.modules.database import crud, models
from app.modules.graph_engine import engine
from app.modules.database.database import SessionLocal
from app.modules.analytics import analytics

async def show_progress_bar(update: Update, duration: float, text: str = "Думаю..."):
    """
    Показывает 'залипательный' прогресс-бар в чате.
    Использует редактирование сообщения для анимации.
    """
    if duration < 1.0:
        return # Слишком быстро, не мельтешим

    msg = await update.message.reply_text(f"{text} [..........] 0%")
    steps = 10
    step_time = duration / steps
    
    for i in range(1, steps + 1):
        await asyncio.sleep(step_time)
        filled = "■" * i
        empty = "." * (steps - i)
        percent = i * 10
        try:
            await msg.edit_text(f"{text} [{filled}{empty}] {percent}%")
        except Exception:
            pass # Игнорируем ошибки (если юзер удалил чат и т.д.)
    
    await asyncio.sleep(0.5)
    await msg.delete() # Убираем за собой

async def handle_node_execution(update: Update, context: ContextTypes.DEFAULT_TYPE, session, node_id: str, db):
    """
    Центральная функция выполнения узла.
    Включает в себя:
    1. Тайминг-команды (DSL v2.0)
    2. Прогресс-бары
    3. Отправку медиа/текста
    """
    # 1. Получаем данные узла
    node_data = engine.get_node(node_id)
    if not node_data:
        await update.message.reply_text("Ошибка: Узел не найден.")
        return

    # 2. Обработка DSL v2.0 (Presentation)
    # Ищем команды типа typing:5s или wait:2s
    timing_command = node_data.get('timing_command')
    if timing_command:
        # Парсинг простой: "cmd:time:arg"
        parts = timing_command.split(':')
        cmd = parts[0]
        try:
            duration = float(parts[1].replace('s', ''))
        except:
            duration = 0

        if cmd == 'typing':
            # Нативный статус "печатает"
            await context.bot.send_chat_action(chat_id=update.effective_chat.id, action='typing')
            await asyncio.sleep(duration)
        elif cmd == 'wait':
            # Просто ждем
            await asyncio.sleep(duration)
        elif cmd == 'progress':
            # [RESTORED] Наш кастомный прогресс-бар
            text = parts[2] if len(parts) > 2 else "Обработка..."
            await show_progress_bar(update, duration, text)

    # 3. Отправка основного контента
    text = node_data.get('text', '')
    options = node_data.get('options', [])
    keyboard = []
    
    if options:
        # Формируем клавиатуру
        keyboard = [[opt['text']] for opt in options]
    
    markup = ReplyKeyboardMarkup(keyboard, one_time_keyboard=True, resize_keyboard=True) if keyboard else None
    
    if text:
        await update.message.reply_text(text, reply_markup=markup)

    # 4. Обработка DSL v2.0 (Logic - Background Timers)
    # timeout:60s:fail_node
    if 'timeout_command' in node_data:
         # ... (логика регистрации таймера в БД через crud.schedule_timer) ...
         pass 

# ... (Остальной код хендлера) ...
