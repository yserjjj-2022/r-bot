# app/modules/telegram_handler.py
# Версия 4.0: Интегрирован "Калькулятор состояний"

import random
import re
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
import traceback

from app.modules.database import SessionLocal, crud
from app.modules import gigachat_handler
# --- ИЗМЕНЕНИЕ: Импортируем наш новый модуль-калькулятор ---
from app.modules import state_calculator

user_sessions = {}

def register_handlers(bot: telebot.TeleBot, graph_data: dict):
    
    # --- Вспомогательная функция для отправки сообщений по графу ---
    def send_node_message(chat_id, node_id):
        node = graph_data["nodes"].get(node_id)
        session_info = user_sessions.get(chat_id)
        if not node or not session_info:
            bot.send_message(chat_id, "Произошла ошибка: узел или сессия не найдены.")
            return

        node_type = node.get("type", "question")
        session_info['node_id'] = node_id
        db = SessionLocal()
        try:
            # --- НОВЫЙ БЛОК: Логика для узлов "Задача" и "Состояние" ---
            if node_type in ["task", "state"]:
                # Получаем все текущие состояния пользователя для этой сессии
                # (предполагаем, что основное состояние - 'score')
                user = crud.get_or_create_user(db, chat_id)
                current_score = crud.get_user_state(db, user.id, session_info['session_id'], 'score')
                
                # Создаем словарь состояний для форматирования текста
                state_variables = {
                    'score': int(current_score),
                    'score_delta': session_info.get('last_delta', 0) # Берем дельту из временной сессии
                }

                # Если это узел-состояние, он не задает вопрос, а показывает результат
                if node_type == "state":
                    message_template = node.get("state_message", "Состояние обновлено.")
                    message_text = message_template.format(**state_variables)
                    bot.send_message(chat_id, message_text, parse_mode="Markdown")
                    
                    # Сразу же переходим на следующий узел, делая узел-состояние "прозрачным"
                    next_node_id = node.get("next_node_id")
                    if next_node_id:
                        send_node_message(chat_id, next_node_id)
                    return # Завершаем выполнение

                # Для узла-задачи просто форматируем текст вопроса
                else: # node_type == "task"
                    node_text = node.get("text", "").format(**state_variables)

            else:
                node_text = node.get("text", "")
            
            # --- Конец нового блока ---

            # Логика для узлов-помощников (условие, рандомизатор)
            if node_type == "condition":
                # ... (этот блок остается без изменений) ...
                return
            
            if node_type == "randomizer":
                # ... (этот блок остается без изменений) ...
                return

            # Логика создания кнопок
            markup = InlineKeyboardMarkup()
            if node_type in ["question", "task"] and "options" in node and node["options"]:
                # ... (этот блок остается почти без изменений) ...
                # Для узла 'task' логика кнопок такая же, как для 'question'
                unconditional_next_id = node.get("next_node_id")
                for idx, option in enumerate(node["options"]):
                    next_node_id_for_button = option.get("next_node_id") or unconditional_next_id
                    if not next_node_id_for_button:
                        print(f"ОШИБКА КОНФИГУРАЦИИ: У варианта '{option['text']}' в узле '{node_id}' не указан next_node_id!")
                        continue
                    # В callback_data передаем индекс кнопки и следующий узел
                    callback_payload = f"{idx}|{next_node_id_for_button}"
                    markup.add(InlineKeyboardButton(text=option["text"], callback_data=callback_payload))
            
            # Логика для финальных узлов
            is_final_node = not ("options" in node and node["options"]) and not node.get("next_node_id")
            if is_final_node and node_type not in ["input_text", "state"]:
                # ... (этот блок остается без изменений) ...
                if session_info:
                    crud.end_session(db, session_info['session_id'])
                    if chat_id in user_sessions: del user_sessions[chat_id]
            
            sent_message = bot.send_message(chat_id, node_text, reply_markup=markup, parse_mode="Markdown")
            if session_info and chat_id in user_sessions:
                session_info['last_question_message_id'] = sent_message.message_id
        
        finally:
            db.close()

    # --- Обработчик команды /start ---
    @bot.message_handler(commands=['start'])
    def start_interview(message):
        # ... (этот блок остается без изменений) ...
        chat_id = message.chat.id
        db = SessionLocal()
        try:
            user = crud.get_or_create_user(db, telegram_id=chat_id)
            session = crud.create_session(db, user_id=user.id, graph_id=graph_data["graph_id"])
            # Инициализируем временное хранилище для дельты
            user_sessions[chat_id] = {'session_id': session.id, 'node_id': None, 'last_question_message_id': None, 'last_delta': 0}
            send_node_message(chat_id, graph_data["start_node_id"])
        except Exception as e:
            traceback.print_exc()
        finally:
            db.close()

    # --- Обработчик нажатия кнопок ---
    @bot.callback_query_handler(func=lambda call: True)
    def handle_callback_query(call):
        chat_id = call.message.chat.id
        session_data = user_sessions.get(chat_id)
        if not session_data:
            bot.answer_callback_query(call.id, "Сессия истекла. Начните заново: /start.", show_alert=True)
            return

        db = SessionLocal()
        try:
            # --- НОВЫЙ БЛОК: Логика для обработки нажатия кнопки в узле "Задача" ---
            current_node_id = session_data['node_id']
            node = graph_data["nodes"].get(current_node_id)
            
            if node and node.get("type") == "task":
                try:
                    button_idx = int(call.data.split('|', 1)[0])
                    option_data = node["options"][button_idx]
                    formula = option_data.get("formula")

                    if formula:
                        user = crud.get_or_create_user(db, chat_id)
                        # Получаем текущее состояние
                        old_score_str = crud.get_user_state(db, user.id, session_data['session_id'], 'score')
                        old_score = int(old_score_str)
                        
                        # Вычисляем новое состояние
                        current_state = {'score': old_score} # Передаем в калькулятор
                        new_score = state_calculator.calculate_new_state(formula, current_state)
                        
                        # Обновляем состояние в БД
                        crud.update_user_state(db, user.id, session_data['session_id'], 'score', new_score)
                        
                        # Сохраняем изменение счета во временную сессию для показа
                        session_data['last_delta'] = new_score - old_score
                        
                except (ValueError, IndexError, KeyError) as e:
                    print(f"Ошибка при обработке формулы для узла {current_node_id}: {e}")
            
            # --- Конец нового блока ---

            # Старая логика сохранения ответа
            try:
                button_idx_str, next_node_id = call.data.split('|', 1)
                button_idx = int(button_idx_str)
                pressed_button_text = call.message.reply_markup.keyboard[button_idx][0].text
            except (ValueError, IndexError):
                pressed_button_text = "N/A"
                next_node_id = call.data
            
            if pressed_button_text != "N/A":
                crud.create_response(db, session_id=session_data['session_id'], node_id=session_data['node_id'], answer_text=pressed_button_text)
            
            bot.answer_callback_query(call.id)
            new_text = f"{call.message.text}\n\n*Ваш ответ: {pressed_button_text}*"
            bot.edit_message_text(chat_id=chat_id, message_id=call.message.message_id, text=new_text, reply_markup=None, parse_mode="Markdown")
            
            send_node_message(chat_id, next_node_id)
            
        except Exception as e:
            traceback.print_exc()
        finally:
            db.close()

    # --- Обработчик текстовых сообщений ---
    @bot.message_handler(content_types=['text'])
    def handle_text_message(message):
        # ... (этот блок остается без изменений) ...
        pass
