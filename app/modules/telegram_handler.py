# app/modules/telegram_handler.py
# ВЕРСИЯ ДЛЯ ДИАГНОСТИКИ: Добавлено расширенное логирование

import random
import re
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
import traceback
import operator
import threading
from sqlalchemy.orm import Session

from app.modules.database import SessionLocal, crud
from app.modules import gigachat_handler
from app.modules import state_calculator

user_sessions = {}

def is_final_node(node_data):
    if not node_data: return True
    has_next_node = node_data.get("next_node_id") or node_data.get("then_node_id") or node_data.get("else_node_id")
    if has_next_node: return False
    if "options" in node_data and node_data["options"]:
        for option in node_data["options"]:
            if option.get("next_node_id"): return False
    if "branches" in node_data and node_data["branches"]: return False
    return True

def _evaluate_condition(condition_str: str, db: Session, user_id: int, session_id: int) -> bool:
    ops = {'>': operator.gt, '<': operator.lt, '>=': operator.ge, '<=': operator.le, '==': operator.eq, '!=': operator.ne}
    try:
        match = re.match(r'\{(\w+)\}\s*([<>=!]+)\s*(.+)', condition_str)
        if not match: 
            print(f"--- [DIAGNOSTIC] Ошибка парсинга условия: '{condition_str}'")
            return False
        key, op_str, value_str = match.groups()
        actual_value = float(crud.get_user_state(db, user_id, session_id, key, '0'))
        result = ops[op_str](actual_value, float(value_str.strip()))
        print(f"--- [DIAGNOSTIC] Условие: '{condition_str}', Переменная '{key}' = {actual_value}, Результат = {result} ---")
        return result
    except (ValueError, KeyError, TypeError) as e:
        print(f"--- [DIAGNOSTIC] Ошибка вычисления условия: {e}")
        return False

def register_handlers(bot: telebot.TeleBot, graph_data: dict):
    
    def _resume_after_pause(chat_id, next_node_id, temp_message_id=None):
        if temp_message_id:
            try: bot.delete_message(chat_id, temp_message_id)
            except Exception: pass
        send_node_message(chat_id, next_node_id)

    def send_node_message(chat_id, node_id):
        print(f"\n--- [DIAGNOSTIC] >>> Вход в send_node_message для узла: '{node_id}'")
        db = SessionLocal()
        try:
            node = graph_data["nodes"].get(str(node_id))
            session_info = user_sessions.get(chat_id)

            if not node:
                print(f"--- [DIAGNOSTIC] Ошибка: Узел '{node_id}' не найден в JSON.")
                return
            if not session_info:
                print(f"--- [DIAGNOSTIC] Ошибка: Сессия для чата {chat_id} не найдена.")
                return

            session_info['node_id'] = node_id
            user = crud.get_or_create_user(db, chat_id)
            node_type = node.get("type", "question")
            print(f"--- [DIAGNOSTIC] Обрабатывается узел '{node_id}', тип: '{node_type}'")

            if node_type == "condition":
                result = _evaluate_condition(node.get("condition_string", ""), db, user.id, session_info['session_id'])
                branch_key = "then_node_id" if result else "else_node_id"
                next_node_id = node.get(branch_key)
                print(f"--- [DIAGNOSTIC] Узел-условие '{node_id}'. Результат: {result}. Следующий узел: '{next_node_id}'")
                if next_node_id:
                    send_node_message(chat_id, next_node_id)
                else:
                    print(f"--- [DIAGNOSTIC] !!! ОШИБКА СЦЕНАРИЯ: Для узла '{node_id}' не определен переход для ветки '{branch_key}'.")
                return

            if node_type == "state":
                print(f"--- [DIAGNOSTIC] Узел-состояние '{node_id}'. Следующий узел: '{node.get('next_node_id')}'")
                text_template = node.get("state_message", "Состояние обновлено.")
                current_score_str = crud.get_user_state(db, user.id, session_info['session_id'], 'score', '0')
                capital_before_str = crud.get_user_state(db, user.id, session_info['session_id'], 'capital_before', '0')
                state_variables = {'score': int(float(current_score_str)), 'capital_before': int(float(capital_before_str))}
                try: formatted_text = text_template.format(**state_variables)
                except KeyError: formatted_text = text_template
                final_text_to_send = formatted_text.replace('\\n', '\n')
                bot.send_message(chat_id, final_text_to_send, parse_mode="Markdown")
                next_node_id = node.get("next_node_id")
                if next_node_id:
                    send_node_message(chat_id, next_node_id)
                else:
                    print(f"--- [DIAGNOSTIC] !!! ОШИБКА СЦЕНАРИЯ: У узла 'state' '{node_id}' нет next_node_id.")
                return

            print(f"--- [DIAGNOSTIC] Узел '{node_id}' является интерактивным. Готовится сообщение.")
            text_template = node.get("text", "")
            current_score_str = crud.get_user_state(db, user.id, session_info['session_id'], 'score', '0')
            capital_before_str = crud.get_user_state(db, user.id, session_info['session_id'], 'capital_before', '0')
            state_variables = {'score': int(float(current_score_str)), 'capital_before': int(float(capital_before_str))}
            try: formatted_text = text_template.format(**state_variables)
            except KeyError: formatted_text = text_template
            final_text_to_send = formatted_text.replace('\\n', '\n')

            markup = InlineKeyboardMarkup()
            options = node.get("options", [])
            if node_type == "circumstance":
                 markup.add(InlineKeyboardButton(text=node.get('option_text', 'Далее'), callback_data=f"0|{node.get('next_node_id')}"))
            elif node_type in ["question", "task"] and options:
                unconditional_next_id = node.get("next_node_id")
                for idx, option in enumerate(options):
                    next_node_id_for_button = option.get("next_node_id") or unconditional_next_id
                    if not next_node_id_for_button: continue
                    markup.add(InlineKeyboardButton(text=option["text"], callback_data=f"{idx}|{next_node_id_for_button}"))
            
            print(f"--- [DIAGNOSTIC] Отправка сообщения для узла '{node_id}'...")
            bot.send_message(chat_id, final_text_to_send, reply_markup=markup, parse_mode="Markdown")
            print(f"--- [DIAGNOSTIC] Сообщение для узла '{node_id}' успешно отправлено.")

            if is_final_node(node) and not node.get("ai_enabled"):
                print(f"--- [DIAGNOSTIC] Завершение сессии на финальном узле без AI: {node_id}")
                crud.end_session(db, session_info['session_id'])
                if chat_id in user_sessions: del user_sessions[chat_id]
        
        except Exception as e:
            print(f"--- [DIAGNOSTIC] !!! КРИТИЧЕСКАЯ ОШИБКА в send_node_message для узла '{node_id}' !!!")
            traceback.print_exc()
        finally:
            print(f"--- [DIAGNOSTIC] <<< Выход из send_node_message для узла: '{node_id}' (блок finally)")
            db.close()

    @bot.message_handler(commands=['start'])
    def start_interview(message):
        chat_id = message.chat.id
        print(f"--- [DIAGNOSTIC] Получена команда /start от chat_id: {chat_id}")
        db = SessionLocal()
        try:
            user = crud.get_or_create_user(db, telegram_id=chat_id)
            session = crud.create_session(db, user_id=user.id, graph_id=graph_data["graph_id"])
            user_sessions[chat_id] = {'session_id': session.id, 'node_id': None}
            print(f"--- [DIAGNOSTIC] Создана сессия {session.id} для пользователя {user.id}")
            start_node = graph_data["start_node_id"]
            send_node_message(chat_id, start_node)
        except Exception as e:
            traceback.print_exc()
        finally:
            db.close()
    
    @bot.callback_query_handler(func=lambda call: True)
    def handle_callback_query(call):
        chat_id = call.message.chat.id
        print(f"--- [DIAGNOSTIC] Получен callback_query: '{call.data}' от chat_id: {chat_id}")
        session_data = user_sessions.get(chat_id)
        if not session_data:
            print(f"--- [DIAGNOSTIC] Сессия для callback не найдена.")
            bot.answer_callback_query(call.id, "Сессия истекла. Начните заново: /start.", show_alert=True)
            return
        
        db = SessionLocal()
        try:
            current_node_id = session_data['node_id']
            print(f"--- [DIAGNOSTIC] Текущий узел при callback: '{current_node_id}'")
            node = graph_data["nodes"].get(current_node_id)
            user = crud.get_or_create_user(db, chat_id)
            
            button_idx_str, next_node_id = call.data.split('|', 1)
            print(f"--- [DIAGNOSTIC] Callback: Индекс кнопки: {button_idx_str}, следующий узел: '{next_node_id}'")
            button_idx = int(button_idx_str)

            text_to_save_in_db, pressed_button_text = "N/A", "N/A"
            node_type = node.get("type")

            if node_type == "circumstance":
                pressed_button_text = node.get("option_text", "Далее")
                text_to_save_in_db = node.get('interpretation', pressed_button_text)
                formula = node.get("formula")
                if formula:
                    old_score_str = crud.get_user_state(db, user.id, session_data['session_id'], 'score', '0')
                    new_score = state_calculator.calculate_new_state(formula, {'score': float(old_score_str)})
                    crud.update_user_state(db, user.id, session_data['session_id'], 'score', new_score)
            
            elif node and node.get("options") and len(node["options"]) > button_idx:
                option_data = node["options"][button_idx]
                pressed_button_text = option_data.get('text', '')
                text_to_save_in_db = option_data.get('interpretation', pressed_button_text)
                
                if node_type == "task" and "formula" in option_data:
                    formula = option_data["formula"]
                    old_score_str = crud.get_user_state(db, user.id, session_data['session_id'], 'score', '0')
                    crud.update_user_state(db, user.id, session_data['session_id'], 'capital_before', float(old_score_str))
                    new_score = state_calculator.calculate_new_state(formula, {'score': float(old_score_str)})
                    crud.update_user_state(db, user.id, session_data['session_id'], 'score', new_score)

            if text_to_save_in_db != "N/A":
                crud.create_response(db, session_id=session_data['session_id'], node_id=current_node_id, answer_text=text_to_save_in_db)
            
            original_template = node.get("text", "")
            score_str = crud.get_user_state(db, user.id, session_data['session_id'], 'score', '0')
            capital_before_str = crud.get_user_state(db, user.id, session_data['session_id'], 'capital_before', '0')
            
            try: formatted_original = original_template.format(score=int(float(score_str)), capital_before=int(float(capital_before_str)))
            except KeyError: formatted_original = original_template
            clean_original = formatted_original.replace('\\n', '\n')
            
            new_text = f"{clean_original}\n\n*Ваш ответ: {pressed_button_text}*"
            
            bot.answer_callback_query(call.id)
            bot.edit_message_text(chat_id=chat_id, message_id=call.message.message_id, text=new_text, reply_markup=None, parse_mode="Markdown")
            send_node_message(chat_id, next_node_id)
        except Exception as e:
            traceback.print_exc()
        finally:
            db.close()

    @bot.message_handler(content_types=['text'])
    def handle_text_message(message):
        if message.text.startswith('/start'):
            start_interview(message)
            return

        chat_id = message.chat.id
        print(f"--- [DIAGNOSTIC] Получено текстовое сообщение: '{message.text}' от chat_id: {chat_id}")
        session_data = user_sessions.get(chat_id)

        if not session_data or not session_data.get('node_id'):
            print(f"--- [DIAGNOSTIC] Сессия для текстового сообщения не найдена.")
            bot.reply_to(message, "Игра уже завершена. Чтобы начать новую, используйте команду /start.")
            return
        
        current_node_id = session_data['node_id']
        node = graph_data["nodes"].get(current_node_id)
        
        if node and node.get("ai_enabled", False):
            print(f"--- [DIAGNOSTIC] AI-помощь включена для узла '{current_node_id}'.")
            bot.send_chat_action(chat_id, 'typing')
            db = SessionLocal()
            try:
                user = crud.get_or_create_user(db, chat_id)
                is_final = is_final_node(node)
                print(f"--- [DIAGNOSTIC] Узел '{current_node_id}' является финальным: {is_final}.")

                if is_final:
                    system_prompt_context = crud.build_final_chat_prompt(db, session_data['session_id'])
                else:
                    options = node.get("options", [])
                    if node.get("type") == "circumstance": options = [{"text": node.get("option_text", "Далее")}]
                    system_prompt_context = crud.build_full_context_for_ai(
                        db, session_data['session_id'], user.id,
                        node.get("text", ""), options, node.get("event_type")
                    )
                
                ai_answer = gigachat_handler.get_ai_response(user_message=message.text, system_prompt=system_prompt_context)
                
                if ai_answer:
                    crud.create_ai_dialogue(db, session_data['session_id'], current_node_id, message.text, ai_answer)
                    bot.reply_to(message, ai_answer, parse_mode="Markdown")

                if is_final:
                    print(f"--- [DIAGNOSTIC] Окончательное завершение сессии после финального чата на узле {current_node_id}")
                    crud.end_session(db, session_data['session_id'])
                    if chat_id in user_sessions: del user_sessions[chat_id]
                elif ai_answer:
                    print(f"--- [DIAGNOSTIC] Возврат к вопросу '{current_node_id}' после консультации.")
                    send_node_message(chat_id, current_node_id)
            
            except Exception as e:
                traceback.print_exc()
            finally:
                db.close()
        
        elif node.get("type") == "input_text":
            print(f"--- [DIAGNOSTIC] Обработка input_text для узла '{current_node_id}'.")
            user_input = message.text
            db = SessionLocal()
            try:
                crud.create_response(db, session_id=session_data['session_id'], node_id=current_node_id, answer_text=user_input)
                if node.get("next_node_id"): 
                    send_node_message(chat_id, node.get("next_node_id"))
            finally:
                db.close()
        else:
            print(f"--- [DIAGNOSTIC] Некорректное текстовое сообщение для узла '{current_node_id}'.")
            bot.reply_to(message, "Пожалуйста, используйте кнопки для ответа на этот вопрос.")

