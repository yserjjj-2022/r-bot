# app/modules/telegram_handler.py
# Версия 5.0: Добавлена логика для условных переходов (if-else)

import random
import re
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
import traceback
import operator # Импортируем модуль для удобной работы с операторами сравнения
from sqlalchemy.orm import Session

from app.modules.database import SessionLocal, crud
from app.modules import gigachat_handler
from app.modules import state_calculator

user_sessions = {}

# --- Вспомогательная функция для безопасного сравнения ---
def _evaluate_condition(condition_str: str, db: Session, user_id: int, session_id: int) -> bool:
    """
    Безопасно вычисляет строку-условие.
    Пример: "{score} >= 350000" -> True/False
    """
    # Словарь для сопоставления строковых операторов с реальными функциями
    ops = {
        '>': operator.gt, '<': operator.lt, '>=': operator.ge,
        '<=': operator.le, '==': operator.eq, '!=': operator.ne
    }
    try:
        # Используем регулярное выражение для "разбора" строки условия
        match = re.match(r'\{(\w+)\}\s*([<>=!]+)\s*(.+)', condition_str)
        if not match:
            print(f"ОШИБКА: Некорректный формат условия: {condition_str}")
            return False

        key, op_str, value_str = match.groups()
        
        # Получаем реальное значение переменной из БД
        actual_value_str = crud.get_user_state(db, user_id, session_id, key)
        
        # Преобразуем оба значения в числа для корректного сравнения
        actual_value = float(actual_value_str)
        comparison_value = float(value_str.strip())

        # Выполняем сравнение
        return ops[op_str](actual_value, comparison_value)

    except (ValueError, KeyError, TypeError) as e:
        print(f"ОШИБКА при вычислении условия '{condition_str}': {e}")
        return False

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
            # --- НОВАЯ ЛОГИКА: Обработка узла "Условие" ---
            if node_type == "condition":
                user = crud.get_or_create_user(db, chat_id)
                result_is_true = _evaluate_condition(
                    node.get("condition_string", ""),
                    db,
                    user.id,
                    session_info['session_id']
                )
                
                next_node_id = node.get("then_node_id") if result_is_true else node.get("else_node_id")
                
                if next_node_id:
                    send_node_message(chat_id, next_node_id)
                else:
                    print(f"ОШИБКА: У узла-условия '{node_id}' не определен путь для результата.")
                return

            # --- Логика для узлов "Задача" и "Состояние" ---
            if node_type in ["task", "state", "question"]:
                user = crud.get_or_create_user(db, chat_id)
                current_score_str = crud.get_user_state(db, user.id, session_info['session_id'], 'score')
                capital_before_str = crud.get_user_state(db, user.id, session_info['session_id'], 'capital_before')
                
                state_variables = {
                    'score': int(float(current_score_str)),
                    'capital_before': int(float(capital_before_str))
                }

                if node_type == "state":
                    message_template = node.get("state_message", "Состояние обновлено.")
                    message_text = message_template.format(**state_variables)
                    bot.send_message(chat_id, message_text, parse_mode="Markdown")
                    next_node_id = node.get("next_node_id")
                    if next_node_id: send_node_message(chat_id, next_node_id)
                    return
                else:
                    node_text = node.get("text", "").format(**state_variables)
            else:
                node_text = node.get("text", "")
            
            # --- Логика для узла "Рандомизатор" ---
            if node_type == "randomizer":
                branches = node.get("branches", [])
                weights = [branch.get("weight", 1) for branch in branches]
                chosen_branch = random.choices(branches, weights=weights, k=1)[0]
                next_node_id = chosen_branch.get("next_node_id")
                if next_node_id:
                    send_node_message(chat_id, next_node_id)
                return

            # --- Логика создания кнопок ---
            markup = InlineKeyboardMarkup()
            if node_type in ["question", "task"] and "options" in node and node["options"]:
                unconditional_next_id = node.get("next_node_id")
                for idx, option in enumerate(node["options"]):
                    next_node_id_for_button = option.get("next_node_id") or unconditional_next_id
                    if not next_node_id_for_button:
                        print(f"ОШИБКА КОНФИГУРАЦИИ: У варианта '{option['text']}' в узле '{node_id}' не указан next_node_id!")
                        continue
                    callback_payload = f"{idx}|{next_node_id_for_button}"
                    markup.add(InlineKeyboardButton(text=option["text"], callback_data=callback_payload))
            
            # --- Логика для финальных узлов ---
            is_final_node = not ("options" in node and node["options"]) and not node.get("next_node_id")
            if is_final_node and node_type not in ["input_text", "state", "condition"]:
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
        chat_id = message.chat.id
        db = SessionLocal()
        try:
            user = crud.get_or_create_user(db, telegram_id=chat_id)
            session = crud.create_session(db, user_id=user.id, graph_id=graph_data["graph_id"])
            user_sessions[chat_id] = {'session_id': session.id, 'node_id': None}
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
            current_node_id = session_data['node_id']
            node = graph_data["nodes"].get(current_node_id)
            
            if node and node.get("type") == "task":
                try:
                    button_idx = int(call.data.split('|', 1)[0])
                    option_data = node["options"][button_idx]
                    formula = option_data.get("formula")

                    if formula:
                        user = crud.get_or_create_user(db, chat_id)
                        old_score_str = crud.get_user_state(db, user.id, session_data['session_id'], 'score')
                        crud.update_user_state(db, user.id, session_data['session_id'], 'capital_before', float(old_score_str))
                        
                        current_state = {'score': float(old_score_str)}
                        new_score = state_calculator.calculate_new_state(formula, current_state)
                        
                        crud.update_user_state(db, user.id, session_data['session_id'], 'score', new_score)
                        
                except (ValueError, IndexError, KeyError) as e:
                    print(f"Ошибка при обработке формулы для узла {current_node_id}: {e}")
            
            button_idx_str, next_node_id = call.data.split('|', 1)
            button_idx = int(button_idx_str)
            pressed_button_text = call.message.reply_markup.keyboard[button_idx][0].text
            
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

        if node_type == "input_text":
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
        
        elif node.get("ai_enabled", False):
            bot.send_chat_action(chat_id, 'typing')
            db = SessionLocal()
            try:
                session_id = session_data['session_id']
                system_prompt_context = crud.build_full_context_for_ai(db, session_id, node.get("text", ""), node.get("options", []))
                ai_answer = gigachat_handler.get_ai_response(user_message=message.text, system_prompt=system_prompt_context)
                
                if ai_answer:
                    crud.create_ai_dialogue(db, session_id, current_node_id, message.text, ai_answer)
                    bot.reply_to(message, ai_answer, parse_mode="Markdown")
                    send_node_message(chat_id, current_node_id)
                else:
                    print("!!! GigaChat вернул пустой ответ.")
                    bot.reply_to(message, "К сожалению, не удалось получить ответ от ассистента.")

            except Exception as e:
                print("!!! КРИТИЧЕСКАЯ ОШИБКА В БЛОКЕ GIGACHAT !!!")
                traceback.print_exc()
                bot.reply_to(message, "Произошла внутренняя ошибка при обращении к AI-ассистенту.")
            finally:
                db.close()

        else:
            bot.reply_to(message, "Пожалуйста, используйте кнопки для ответа на этот вопрос.")