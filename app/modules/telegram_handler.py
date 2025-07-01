# app/modules/telegram_handler.py

import random
import re # <-- Добавляем импорт для работы с регулярными выражениями
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton

from app.modules.database import SessionLocal, crud
from app.modules import gigachat_handler

user_sessions = {}

def register_handlers(bot: telebot.TeleBot, graph_data: dict):
    
    def send_node_message(chat_id, node_id):
        node = graph_data["nodes"].get(node_id)
        session_info = user_sessions.get(chat_id)
        if not node or not session_info:
            bot.send_message(chat_id, "Произошла ошибка: узел или сессия не найдены.")
            return

        node_type = node.get("type", "question") # По умолчанию узел - это вопрос

        # --- ОБНОВЛЕННЫЙ БЛОК ЛОГИКИ ---
        
        # 1. Обработка УСЛОВНОГО ПЕРЕХОДА
        if node_type == "condition":
            condition_str = node.get("condition")
            db = SessionLocal()
            try:
                # Находим placeholder типа {node_id}
                match = re.search(r'\{(\w+)\}', condition_str)
                if not match:
                    # Если условие задано неверно, идем по "else" ветке
                    send_node_message(chat_id, node.get("else_node_id"))
                    return

                # Извлекаем ID вопроса и значение для сравнения
                question_node_id = match.group(1)
                value_to_compare = condition_str.split('==')[-1].strip().strip("'\"")
                
                # Получаем реальный ответ пользователя из БД
                user_response = crud.get_response_for_node(db, session_info['session_id'], question_node_id)
                
                # Сравниваем
                if user_response and user_response.answer_text == value_to_compare:
                    send_node_message(chat_id, node.get("then_node_id"))
                else:
                    send_node_message(chat_id, node.get("else_node_id"))
            finally:
                db.close()
            return
            
        # --- ОБНОВЛЕННЫЙ БЛОК РАНДОМИЗАТОРА С ПОДДЕРЖКОЙ ВЕСОВ ---
        if node.get("type") == "randomizer":
            branches = node.get("branches", [])
            if not branches:
                bot.send_message(chat_id, "Ошибка конфигурации графа: узел-рандомизатор не имеет веток.")
                return
            
            # Извлекаем веса из каждой ветки. Если веса нет, используем 1 (для обратной совместимости).
            weights = [branch.get("weight", 1) for branch in branches]
            
            # Используем random.choices для выбора одной ветки с учетом весов.
            # k=1 означает, что нам нужен только один результат. Возвращается список, поэтому берем [0].
            chosen_branch = random.choices(branches, weights=weights, k=1)[0]
            
            next_node_id = chosen_branch.get("next_node_id")
            
            if not next_node_id:
                bot.send_message(chat_id, "Ошибка конфигурации графа: ветка рандомизатора не имеет next_node_id.")
                return
                
            send_node_message(chat_id, next_node_id)
            return

        # --- Остальной код функции без изменений ---
        session_info = user_sessions.get(chat_id)
        if session_info:
            session_info['node_id'] = node_id

        markup = InlineKeyboardMarkup()
        if "options" in node and node["options"]:
            for idx, option in enumerate(node["options"]):
                callback_payload = f"{idx}|{option.get('next_node_id')}"
                markup.add(InlineKeyboardButton(text=option["text"], callback_data=callback_payload))
        else:
            db = SessionLocal()
            try:
                if session_info:
                    crud.end_session(db, session_info['session_id'])
                    if chat_id in user_sessions: del user_sessions[chat_id]
            finally:
                db.close()
        
        sent_message = bot.send_message(chat_id, node["text"], reply_markup=markup, parse_mode="Markdown")
        if session_info:
            session_info['last_question_message_id'] = sent_message.message_id

    @bot.message_handler(commands=['start'])
    def start_interview(message):
        chat_id = message.chat.id
        db = SessionLocal()
        try:
            user = crud.get_or_create_user(db, telegram_id=chat_id)
            session = crud.create_session(db, user_id=user.id, graph_id=graph_data["graph_id"])
            user_sessions[chat_id] = {'session_id': session.id, 'node_id': None, 'last_question_message_id': None}
            send_node_message(chat_id, graph_data["start_node_id"])
        finally:
            db.close()

    @bot.callback_query_handler(func=lambda call: True)
    def handle_callback_query(call):
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

    @bot.message_handler(content_types=['text'])
    def handle_text_message(message):
        chat_id = message.chat.id
        session_data = user_sessions.get(chat_id)
        if not session_data or not session_data.get('node_id'):
            bot.reply_to(message, "Чтобы задать вопрос ассистенту, пожалуйста, сначала начните опрос командой /start.")
            return

        current_node_id = session_data['node_id']
        node = graph_data["nodes"].get(current_node_id)
        if not node or not node.get("ai_enabled", False):
            bot.reply_to(message, "Для этого вопроса диалог с помощником недоступен.")
            return
            
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
            send_node_message(chat_id, current_node_id)
        finally:
            db.close()
