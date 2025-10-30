# -*- coding: utf-8 -*-
# app/modules/telegram_handler.py — PATCH: отмена timeout при нажатии кнопки

from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
import traceback

try:
    from app.modules.timing_engine import cancel_timeout_for_session
except Exception:
    def cancel_timeout_for_session(session_id: int) -> bool:
        return False

# ... остальной код файла остаётся без изменений ...
# Ниже — фрагмент внутри button_callback(call):

# ДОБАВИТЬ внутри обработчика кнопки, сразу после валидаций и перед обработкой логики узла:
# s = user_sessions.get(chat_id)
# if s and s.get('session_id'):
#     try:
#         cancelled = cancel_timeout_for_session(s['session_id'])
#         if cancelled:
#             print(f"[TIMEOUT] Cancelled for session {s['session_id']}")
#     except Exception:
#         pass
