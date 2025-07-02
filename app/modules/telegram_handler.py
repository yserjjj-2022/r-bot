# app/modules/telegram_handler.py

import random
import re
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
import traceback # <-- Добавляем traceback для детальных логов ошибок

from app.modules.database import SessionLocal, crud
from app.modules import gigachat_handler

user_sessions = {}

# Ваша функция register_handlers остается без изменений, мы правим только ее внутренности
def register_handlers(bot: telebot.TeleBot, graph_data: dict):
    
    # Вспомогательная функция send_node_message остается без изменений
    def send_node_message(chat_id, node_id):
        # ... (здесь ваш код без изменений)
        node = graph_data["nodes"].get(node_id)
        session_info = user_sessions.get(chat_id)
        if not node or not session_info:
            bot.send_message(chat_id, "Произошла ошибка: узел или сессия не найдены.")
            return

        node_type = node.get("type", "question")

        if node_type == "condition":
            condition_str = node.get("condition")
            db = SessionLocal()
            try:
                match = re.search(r'\{(\w+)\}', condition_str)
                if not match:
                    send_node_message(chat_id, node.get("else_node_id"))
                    return

                question_node_id = match.group(1)
                value_to_compare = condition_str.split('==')[-1].strip().strip("'\"")
                
                user_response = crud.get_response_for_node(db, session_info['session_id'], question_node_id)
                
                if user_response and user_response.answer_text == value_to_compare:
                    send_node_message(chat_id, node.get("then_node_id"))
                else:
                    send_node_message(chat_id, node.get("else_node_id"))
            finally:
                db.close()
            return
            
        if node.get("type") == "randomizer":
            branches = node.get("branches", [])
            if not branches:
                bot.send_message(chat_id, "Ошибка конфигурации графа: узел-рандомизатор не имеет веток.")
                return
            
            weights = [branch.get("weight", 1) for branch in branches]
            chosen_branch = random.choices(branches, weights=weights, k=1)[0]
            next_node_id = chosen_branch.get("next_node_id")
            
            if not next_node_id:
                bot.send_message(chat_id, "Ошибка конфигурации графа: ветка рандомизатора не имеет next_node_id.")
                return
                
            send_node_message(chat_id, next_node_id)
            return

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


    # --- ГЛАВНОЕ ИЗМЕНЕНИЕ ЗДЕСЬ ---
    @bot.message_handler(commands=['start'])
    def start_interview(message):
        # Наш первый "жучок"
        print(f"--- 1. ОБРАБОТЧИК /start СРАБОТАЛ для пользователя {message.chat.id} ---")
        
        chat_id = message.chat.id
        db = SessionLocal()
        
        try:
            print("--- 2. Попытка получить/создать пользователя... ---")
            user = crud.get_or_create_user(db, telegram_id=chat_id)
            
            print(f"--- 3. Пользователь получен (ID: {user.id}). Попытка создать сессию... ---")
            # Проверяем, что graph_id существует, прежде чем его использовать
            if "graph_id" not in graph_data:
                 print("!!! КРИТИЧЕСКАЯ ОШИБКА: 'graph_id' не найден в graph_data !!!")
                 # Можно отправить сообщение пользователю или просто выйти
                 bot.send_message(chat_id, "Ошибка конфигурации бота. Не удалось начать сессию.")
                 return

            session = crud.create_session(db, user_id=user.id, graph_id=graph_data["graph_id"])
            
            print(f"--- 4. Сессия создана (ID: {session.id}). Регистрация в user_sessions... ---")
            user_sessions[chat_id] = {'session_id': session.id, 'node_id': None, 'last_question_message_id': None}
            
            # Проверяем, что start_node_id существует
            if "start_node_id" not in graph_data:
                print("!!! КРИТИЧЕСКАЯ ОШИБКА: 'start_node_id' не найден в graph_data !!!")
                bot.send_message(chat_id, "Ошибка конфигурации бота. Не найден стартовый узел.")
                return

            print("--- 5. Попытка отправить стартовое сообщение... ---")
            send_node_message(chat_id, graph_data["start_node_id"])
            
            print("--- 6. ВСЕ ШАГИ ВНУТРИ ОБРАБОТЧИКА УСПЕШНО ЗАВЕРШЕНЫ ---")

        except Exception as e:
            # ЭТО САМАЯ ВАЖНАЯ ЧАСТЬ! Она поймает любую скрытую ошибку.
            print(f"!!! КРИТИЧЕСКАЯ ОШИБКА ВНУТРИ ОБРАБОТЧИКА /start: {e} !!!")
            traceback.print_exc() # Напечатает полный путь ошибки, чтобы мы точно знали, где она
        finally:
            # Этот блок гарантирует, что БД закроется в любом случае
            print("--- 7. Закрытие сессии БД... ---")
            db.close()


    # --- Остальные обработчики с "легким" логированием ---
    @bot.callback_query_handler(func=lambda call: True)
    def handle_callback_query(call):
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


    @bot.message_handler(content_types=['text'])
    def handle_text_message(message):
        # Пропускаем обработку команды /start здесь, чтобы избежать двойной логики
        if message.text.startswith('/start'):
            return
            
        print(f"--- Получено текстовое сообщение от {message.chat.id}: '{message.text}' ---")
        
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
