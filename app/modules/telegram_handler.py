# app/modules/telegram_handler.py (Версия 3.1 с однозначной логикой)

import random
import re
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
import traceback

from app.modules.database import SessionLocal, crud
from app.modules import gigachat_handler

user_sessions = {}

def register_handlers(bot: telebot.TeleBot, graph_data: dict):
    
    def send_node_message(chat_id, node_id):
        # ... (код для send_node_message без изменений, он уже правильный) ...
        # (я оставлю его свернутым для краткости, он идентичен коду из прошлого ответа)
        node = graph_data["nodes"].get(node_id)
        session_info = user_sessions.get(chat_id)
        if not node or not session_info:
            bot.send_message(chat_id, "Произошла ошибка: узел или сессия не найдены.")
            return

        node_type = node.get("type", "question")
        session_info['node_id'] = node_id

        if node_type == "condition":
            # ...
            return
        if node_type == "randomizer":
            # ...
            return

        markup = InlineKeyboardMarkup()
        if node_type == "question" and "options" in node and node["options"]:
            unconditional_next_id = node.get("next_node_id")
            for idx, option in enumerate(node["options"]):
                next_node_id_for_button = option.get("next_node_id") or unconditional_next_id
                if not next_node_id_for_button:
                    print(f"ОШИБКА КОНФИГУРАЦИИ: У варианта '{option['text']}' в узле '{node_id}' не указан next_node_id!")
                    continue
                callback_payload = f"{idx}|{next_node_id_for_button}"
                markup.add(InlineKeyboardButton(text=option["text"], callback_data=callback_payload))
        
        is_final_node = not ("options" in node and node["options"]) and not node.get("next_node_id")
        if is_final_node and node_type != "input_text":
            db = SessionLocal()
            try:
                if session_info:
                    crud.end_session(db, session_info['session_id'])
                    if chat_id in user_sessions: del user_sessions[chat_id]
            finally:
                db.close()
        
        sent_message = bot.send_message(chat_id, node["text"], reply_markup=markup, parse_mode="Markdown")
        if session_info and chat_id in user_sessions:
            session_info['last_question_message_id'] = sent_message.message_id

    @bot.message_handler(commands=['start'])
    def start_interview(message):
        # ... (код для /start без изменений) ...
        print(f"--- 1. ОБРАБОТЧИК /start СРАБОТАЛ для пользователя {message.chat.id} ---")
        chat_id = message.chat.id
        db = SessionLocal()
        try:
            user = crud.get_or_create_user(db, telegram_id=chat_id)
            session = crud.create_session(db, user_id=user.id, graph_id=graph_data["graph_id"])
            user_sessions[chat_id] = {'session_id': session.id, 'node_id': None, 'last_question_message_id': None}
            send_node_message(chat_id, graph_data["start_node_id"])
            print("--- 6. ОБРАБОТЧИК /start УСПЕШНО ЗАВЕРШЕН ---")
        except Exception as e:
            print(f"!!! КРИТИЧЕСКАЯ ОШИБКА ВНУТРИ ОБРАБОТЧИКА /start: {e} !!!")
            traceback.print_exc()
        finally:
            print("--- 7. Закрытие сессии БД... ---")
            db.close()

    @bot.callback_query_handler(func=lambda call: True)
    def handle_callback_query(call):
        # ... (код для callback_query без изменений) ...
        print(f"--- Получен callback_query от {call.message.chat.id} с данными: {call.data} ---")
        chat_id = call.message.chat.id
        try:
            button_idx_str, next_node_id = call.data.split('|', 1)
            button_idx = int(button_idx_str)
            pressed_button_text = call.message.reply_markup.keyboard[button_idx][0].text
        except (ValueError, IndexError):
            pressed_button_text = "N/A"
            next_node_id = call.data
        session_data = user_sessions.get(chat_id)
        if not session_data:
            bot.answer_callback_query(call.id, "Сессия истекла. Начните заново: /start.", show_alert=True)
            return
        db = SessionLocal()
        try:
            if pressed_button_text != "N/A":
                crud.create_response(db, session_id=session_data['session_id'], node_id=session_data['node_id'], answer_text=pressed_button_text)
        finally:
            db.close()
        bot.answer_callback_query(call.id)
        new_text = f"{call.message.text}\n\n*Ваш ответ: {pressed_button_text}*"
        bot.edit_message_text(chat_id=chat_id, message_id=call.message.message_id, text=new_text, reply_markup=None, parse_mode="Markdown")
        send_node_message(chat_id, next_node_id)


    # --- ИСПРАВЛЕННАЯ ЛОГИКА "УМНОГО ДИСПЕТЧЕРА" ---
    @bot.message_handler(content_types=['text'])
    def handle_text_message(message):
        if message.text.startswith('/start'): return
        
        chat_id = message.chat.id
        session_data = user_sessions.get(chat_id)
        
        if not session_data or not session_data.get('node_id'):
            bot.reply_to(message, "Чтобы начать опрос, используйте команду /start.")
            return

        current_node_id = session_data['node_id']
        node = graph_data["nodes"].get(current_node_id)
        if not node: return

        node_type = node.get("type", "question")

        # ПРИОРИТЕТ 1: Если узел специально предназначен для ввода текста.
        if node_type == "input_text":
            print(f"Обработка 'input_text' для узла {current_node_id}")
            user_input = message.text
            db = SessionLocal()
            try:
                crud.create_response(db, session_id=session_data['session_id'], node_id=current_node_id, answer_text=user_input)
            finally:
                db.close()
            next_node_id = node.get("next_node_id")
            if next_node_id:
                send_node_message(chat_id, next_node_id)
            else:
                print(f"ОШИБКА: у узла '{current_node_id}' типа 'input_text' нет 'next_node_id'")
        
        # ПРИОРИТЕТ 2: Если узел ПОДДЕРЖИВАЕТ диалог с ИИ.
        elif node.get("ai_enabled", False):
            print(f"Обработка AI диалога для узла {current_node_id}")
            bot.send_chat_action(chat_id, 'typing')
            last_question_message_id = session_data.get('last_question_message_id')
            
            db = SessionLocal()
            try:
                session_id = session_data['session_id']
                system_prompt_context = crud.build_full_context_for_ai(db, session_id, node.get("text", ""), node.get("options", []))
                ai_answer = gigachat_handler.get_ai_response(user_message=message.text, system_prompt=system_prompt_context)
                crud.create_ai_dialogue(db, session_id, current_node_id, message.text, ai_answer)
                if last_question_message_id:
                    try: bot.delete_message(chat_id, last_question_message_id)
                    except Exception as e: print(f"Не удалось удалить старое сообщение (ID: {last_question_message_id}): {e}")
                bot.reply_to(message, ai_answer, parse_mode="Markdown")
                # После ответа ИИ, мы снова показываем исходный вопрос с кнопками
                send_node_message(chat_id, current_node_id)
            finally:
                db.close()

        # ЕСЛИ НИ ОДНО ИЗ УСЛОВИЙ ВЫШЕ НЕ ВЫПОЛНЕНО:
        # Это обычный узел с кнопками, без поддержки ИИ.
        else:
            bot.reply_to(message, "Пожалуйста, используйте кнопки для ответа на этот вопрос.")

