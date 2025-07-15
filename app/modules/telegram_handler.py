# app/modules/telegram_handler.py
# Финальная версия 5.14: Добавлена корректная обработка конца игры и "трактовок"

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

# --- Глобальная функция для проверки, является ли узел финальным ---
def is_final_node(node_data):
    if not node_data:
        return True
    has_options = "options" in node_data and node_data["options"]
    has_branches = "branches" in node_data and node_data["branches"]
    has_next_node = any(node_data.get(key) for key in ["next_node_id", "then_node_id", "else_node_id"])
    return not has_options and not has_next_node and not has_branches

def _evaluate_condition(condition_str: str, db: Session, user_id: int, session_id: int) -> bool:
    ops = {'>': operator.gt, '<': operator.lt, '>=': operator.ge, '<=': operator.le, '==': operator.eq, '!=': operator.ne}
    try:
        match = re.match(r'\{(\w+)\}\s*([<>=!]+)\s*(.+)', condition_str)
        if not match: return False
        key, op_str, value_str = match.groups()
        actual_value = float(crud.get_user_state(db, user_id, session_id, key, '0'))
        return ops[op_str](actual_value, float(value_str.strip()))
    except (ValueError, KeyError, TypeError) as e:
        print(f"ОШИБКА при вычислении условия '{condition_str}': {e}")
        return False

def register_handlers(bot: telebot.TeleBot, graph_data: dict):
    
    def _resume_after_pause(chat_id, next_node_id, temp_message_id=None):
        if temp_message_id:
            try: bot.delete_message(chat_id, temp_message_id)
            except Exception as e: print(f"--- [ПАУЗА] Не удалось удалить временное сообщение {temp_message_id}: {e} ---")
        send_node_message(chat_id, next_node_id)

    def send_node_message(chat_id, node_id):
        db = SessionLocal()
        try:
            print(f"--- [НАВИГАЦИЯ] Попытка перехода на узел: {node_id} для чата {chat_id} ---")
            node = graph_data["nodes"].get(node_id)
            session_info = user_sessions.get(chat_id)
            if not node or not session_info:
                bot.send_message(chat_id, "Произошла ошибка: узел или сессия не найдены.")
                if chat_id in user_sessions: del user_sessions[chat_id]
                return

            node_type = node.get("type", "question")
            session_info['node_id'] = node_id
            
            user = crud.get_or_create_user(db, chat_id)

            if node_type == "circumstance":
                current_score_str = crud.get_user_state(db, user.id, session_info['session_id'], 'score', '0')
                state_variables = {'score': int(float(current_score_str))}
                text_template = node.get("text", "").replace('\\n', '\n')
                final_text = text_template.format(**state_variables)
                markup = InlineKeyboardMarkup()
                callback_data = f"0|{node.get('next_node_id')}"
                markup.add(InlineKeyboardButton(text=node.get('option_text', 'Далее'), callback_data=callback_data))
                bot.send_message(chat_id, final_text, reply_markup=markup, parse_mode="Markdown")
                return

            if node_type == "pause":
                delay = float(node.get("delay", 1.0))
                next_node_id = node.get("next_node_id")
                pause_text = node.get("pause_text", "").replace('\\n', '\n')
                temp_message_id = None
                if not next_node_id: return
                if pause_text:
                    sent_msg = bot.send_message(chat_id, pause_text, parse_mode="Markdown")
                    temp_message_id = sent_msg.message_id
                else: bot.send_chat_action(chat_id, 'typing')
                threading.Timer(delay, _resume_after_pause, args=[chat_id, next_node_id, temp_message_id]).start()
                return

            if node_type == "condition":
                result = _evaluate_condition(node.get("condition_string", ""), db, user.id, session_info['session_id'])
                next_node_id = node.get("then_node_id") if result else node.get("else_node_id")
                if next_node_id: send_node_message(chat_id, next_node_id)
                return

            text_template = node.get("text", "")
            current_score_str = crud.get_user_state(db, user.id, session_info['session_id'], 'score', '0')
            capital_before_str = crud.get_user_state(db, user.id, session_info['session_id'], 'capital_before', '0')
            state_variables = {'score': int(float(current_score_str)), 'capital_before': int(float(capital_before_str))}
            if node_type == "state": text_template = node.get("state_message", "Состояние обновлено.")
            try: formatted_text = text_template.format(**state_variables)
            except KeyError: formatted_text = text_template
            final_text_to_send = formatted_text.replace('\\n', '\n')
            
            if node_type == "state":
                bot.send_message(chat_id, final_text_to_send, parse_mode="Markdown")
                next_node_id = node.get("next_node_id")
                if next_node_id: send_node_message(chat_id, next_node_id)
                return

            if node_type == "randomizer":
                branches = node.get("branches", [])
                if not branches: return
                weights = [branch.get("weight", 1) for branch in branches]
                chosen_branch = random.choices(branches, weights=weights, k=1)[0]
                next_node_id = chosen_branch.get("next_node_id")
                if next_node_id: send_node_message(chat_id, next_node_id)
                return

            markup = InlineKeyboardMarkup()
            if node_type in ["question", "task"] and "options" in node and node["options"]:
                unconditional_next_id = node.get("next_node_id")
                for idx, option in enumerate(node["options"]):
                    next_node_id_for_button = option.get("next_node_id") or unconditional_next_id
                    if not next_node_id_for_button: continue
                    markup.add(InlineKeyboardButton(text=option["text"], callback_data=f"{idx}|{next_node_id_for_button}"))
            
            # Если узел финальный, сессия завершится *после* его отправки
            bot.send_message(chat_id, final_text_to_send, reply_markup=markup, parse_mode="Markdown")

            if is_final_node(node):
                print(f"--- [СЕССИЯ] Завершение сессии на финальном узле {node_id} ---")
                crud.end_session(db, session_info['session_id'])
                if chat_id in user_sessions: del user_sessions[chat_id]

        except Exception as e:
            print(f"!!! КРИТИЧЕСКАЯ ОШИБКА в send_node_message для узла {node_id}!!!")
            traceback.print_exc()
            bot.send_message(chat_id, "Произошла внутренняя ошибка. Пожалуйста, начните заново: /start")
            if chat_id in user_sessions: del user_sessions[chat_id]
        finally:
            db.close()

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
            user = crud.get_or_create_user(db, chat_id)

            if node and node.get("type") == "circumstance":
                if node.get("formula"):
                    old_score = float(crud.get_user_state(db, user.id, session_data['session_id'], 'score', '0'))
                    new_score = state_calculator.calculate_new_state(node.get("formula"), {'score': old_score})
                    crud.update_user_state(db, user.id, session_data['session_id'], 'score', new_score)
            
            elif node and node.get("type") == "task":
                try:
                    button_idx_str, _ = call.data.split('|', 1)
                    button_idx = int(button_idx_str)
                    option_data = node["options"][button_idx]
                    if option_data.get("formula"):
                        old_score = float(crud.get_user_state(db, user.id, session_data['session_id'], 'score', '0'))
                        crud.update_user_state(db, user.id, session_data['session_id'], 'capital_before', old_score)
                        new_score = state_calculator.calculate_new_state(option_data.get("formula"), {'score': old_score})
                        crud.update_user_state(db, user.id, session_data['session_id'], 'score', new_score)
                except (ValueError, IndexError, KeyError) as e:
                    print(f"Ошибка при обработке формулы для узла {current_node_id}: {e}")
            
            button_idx_str, next_node_id = call.data.split('|', 1)
            button_idx = int(button_idx_str)

            text_to_save_in_db, pressed_button_text = "N/A", "N/A"
            if node.get("type") == "circumstance":
                pressed_button_text = text_to_save_in_db = node.get("option_text", "Далее")
            elif "options" in node and len(node["options"]) > button_idx:
                option_data = node["options"][button_idx]
                pressed_button_text = option_data['text']
                text_to_save_in_db = option_data.get('interpretation', pressed_button_text)
            
            if text_to_save_in_db != "N/A":
                crud.create_response(db, session_id=session_data['session_id'], node_id=current_node_id, answer_text=text_to_save_in_db)
            
            original_template = node.get("text", "")
            score_str = crud.get_user_state(db, user.id, session_data['session_id'], 'score', '0')
            try: formatted_original = original_template.format(score=int(float(score_str)))
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
        session_data = user_sessions.get(chat_id)
        
        if not session_data or not session_data.get('node_id'):
            bot.reply_to(message, "Игра уже завершена. Чтобы начать новую, используйте команду /start.")
            return
        
        current_node_id = session_data['node_id']
        node = graph_data["nodes"].get(current_node_id)
        
        if is_final_node(node):
            bot.reply_to(message, "Игра окончена. Спасибо за участие! Для начала новой игры используйте /start.")
            if chat_id in user_sessions: del user_sessions[chat_id]
            return

        if node.get("type") == "input_text":
            user_input = message.text
            db = SessionLocal()
            try: crud.create_response(db, session_id=session_data['session_id'], node_id=current_node_id, answer_text=user_input)
            finally: db.close()
            if node.get("next_node_id"): send_node_message(chat_id, node.get("next_node_id"))
        
        elif node.get("ai_enabled", False):
            bot.send_chat_action(chat_id, 'typing')
            db = SessionLocal()
            try:
                session_id = session_data['session_id']
                user = crud.get_or_create_user(db, chat_id)
                system_prompt_context = crud.build_full_context_for_ai(
                    db, session_id, user.id,
                    node.get("text", ""), 
                    node.get("options", []) if node.get("options") else [],
                    node.get("event_type")
                )
                ai_answer = gigachat_handler.get_ai_response(user_message=message.text, system_prompt=system_prompt_context)
                if ai_answer:
                    crud.create_ai_dialogue(db, session_id, current_node_id, message.text, ai_answer)
                    bot.reply_to(message, ai_answer, parse_mode="Markdown")
                    send_node_message(chat_id, current_node_id)
                else: 
                    bot.reply_to(message, "К сожалению, не удалось получить ответ от ассистента.")
            except Exception as e:
                traceback.print_exc()
            finally:
                db.close()
        
        else:
            bot.reply_to(message, "Пожалуйста, используйте кнопки для ответа на этот вопрос.")
