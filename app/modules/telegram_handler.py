# app/modules/telegram_handler.py
# Финальная версия 5.16: Улучшенная логика завершения игры и обработки "трактовок"

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
    """Проверяет, является ли узел конечным в сценарии."""
    if not node_data:
        return True
    
    # У узла не должно быть выходов
    has_next_node = node_data.get("next_node_id") or node_data.get("then_node_id") or node_data.get("else_node_id")
    if has_next_node:
        return False
        
    # У узла не должно быть вариантов ответа с переходами
    if "options" in node_data and node_data["options"]:
        for option in node_data["options"]:
            if option.get("next_node_id"):
                return False

    # У рандомизатора не должно быть веток
    if "branches" in node_data and node_data["branches"]:
        return False
        
    return True

# --- Вспомогательная функция для безопасного сравнения ---
def _evaluate_condition(condition_str: str, db: Session, user_id: int, session_id: int) -> bool:
    """Безопасно вычисляет строку-условие."""
    ops = {'>': operator.gt, '<': operator.lt, '>=': operator.ge, '<=': operator.le, '==': operator.eq, '!=': operator.ne}
    try:
        match = re.match(r'\{(\w+)\}\s*([<>=!]+)\s*(.+)', condition_str)
        if not match:
            print(f"ОШИБКА: Некорректный формат условия: {condition_str}")
            return False
        key, op_str, value_str = match.groups()
        actual_value_str = crud.get_user_state(db, user_id, session_id, key, '0')
        actual_value = float(actual_value_str)
        comparison_value = float(value_str.strip())
        return ops[op_str](actual_value, comparison_value)
    except (ValueError, KeyError, TypeError) as e:
        print(f"ОШИБКА при вычислении условия '{condition_str}': {e}")
        return False

def register_handlers(bot: telebot.TeleBot, graph_data: dict):
    
    def _resume_after_pause(chat_id, next_node_id, temp_message_id=None):
        """Вызывается таймером для продолжения сценария после паузы."""
        if temp_message_id:
            try:
                bot.delete_message(chat_id, temp_message_id)
            except Exception as e:
                print(f"--- [ПАУЗА] Не удалось удалить временное сообщение {temp_message_id}: {e} ---")
        send_node_message(chat_id, next_node_id)

    # --- Основная функция отправки сообщений ---
    def send_node_message(chat_id, node_id):
        db = SessionLocal()
        try:
            print(f"--- [НАВИГАЦИЯ] Попытка перехода на узел: {node_id} для чата {chat_id} ---")
            node = graph_data["nodes"].get(str(node_id))
            session_info = user_sessions.get(chat_id)

            if not node:
                bot.send_message(chat_id, "Произошла ошибка: узел не найден. Попробуйте начать заново с /start.")
                if chat_id in user_sessions: del user_sessions[chat_id]
                return
            
            if not session_info:
                bot.send_message(chat_id, "Игра завершена. Для нового начала, используйте /start.")
                return

            session_info['node_id'] = node_id
            print(f"--- [СЕССИЯ] Установлен текущий узел: {node_id} ---")
            
            user = crud.get_or_create_user(db, chat_id)
            node_type = node.get("type", "question")

            if node_type == "pause":
                delay = float(node.get("delay", 1.0))
                next_node_id = node.get("next_node_id")
                pause_text = node.get("pause_text", "").replace('\\n', '\n')
                temp_message_id = None
                if not next_node_id: return
                
                print(f"--- [ПАУЗА] Задержка на {delay} сек. для чата {chat_id}, затем переход на {next_node_id} ---")
                
                if pause_text:
                    sent_msg = bot.send_message(chat_id, pause_text, parse_mode="Markdown")
                    temp_message_id = sent_msg.message_id
                else:
                    bot.send_chat_action(chat_id, 'typing')
                
                threading.Timer(delay, _resume_after_pause, args=[chat_id, next_node_id, temp_message_id]).start()
                return

            if node_type == "condition":
                result = _evaluate_condition(node.get("condition_string", ""), db, user.id, session_info['session_id'])
                next_node_id = node.get("then_node_id") if result else node.get("else_node_id")
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

            text_template = node.get("text", "")
            if node_type == "state":
                text_template = node.get("state_message", "Состояние обновлено.")

            current_score_str = crud.get_user_state(db, user.id, session_info['session_id'], 'score', '0')
            capital_before_str = crud.get_user_state(db, user.id, session_info['session_id'], 'capital_before', '0')
            state_variables = {'score': int(float(current_score_str)), 'capital_before': int(float(capital_before_str))}
            
            try:
                formatted_text = text_template.format(**state_variables)
            except KeyError:
                formatted_text = text_template

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
            
            bot.send_message(chat_id, final_text_to_send, reply_markup=markup, parse_mode="Markdown")

            if is_final_node(node):
                print(f"--- [СЕССИЯ] Завершение сессии на финальном узле {node_id} ---")
                crud.end_session(db, session_info['session_id'])
                if chat_id in user_sessions:
                    del user_sessions[chat_id]
                return

            if node_type == "state":
                next_node_id = node.get("next_node_id")
                if next_node_id:
                    send_node_message(chat_id, next_node_id)
        
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
            
            button_idx_str, next_node_id = call.data.split('|', 1)
            button_idx = int(button_idx_str)

            text_to_save_in_db = "N/A"
            pressed_button_text = "N/A"
            node_type = node.get("type")

            if node_type == "circumstance":
                formula = node.get("formula")
                pressed_button_text = text_to_save_in_db = node.get("option_text", "Далее")
                if formula:
                    old_score_str = crud.get_user_state(db, user.id, session_data['session_id'], 'score', '0')
                    current_state = {'score': float(old_score_str)}
                    new_score = state_calculator.calculate_new_state(formula, current_state)
                    crud.update_user_state(db, user.id, session_data['session_id'], 'score', new_score)
            
            elif node and node.get("options") and len(node["options"]) > button_idx:
                option_data = node["options"][button_idx]
                pressed_button_text = option_data.get('text', '')
                text_to_save_in_db = option_data.get('interpretation', pressed_button_text)
                
                if node_type == "task" and "formula" in option_data:
                    formula = option_data["formula"]
                    old_score_str = crud.get_user_state(db, user.id, session_data['session_id'], 'score', '0')
                    crud.update_user_state(db, user.id, session_data['session_id'], 'capital_before', float(old_score_str))
                    current_state = {'score': float(old_score_str)}
                    new_score = state_calculator.calculate_new_state(formula, current_state)
                    crud.update_user_state(db, user.id, session_data['session_id'], 'score', new_score)

            if text_to_save_in_db != "N/A":
                crud.create_response(db, session_id=session_data['session_id'], node_id=current_node_id, answer_text=text_to_save_in_db)
            
            original_template = node.get("text", "")
            score_str = crud.get_user_state(db, user.id, session_data['session_id'], 'score', '0')
            try:
                formatted_original = original_template.format(score=int(float(score_str)))
            except KeyError:
                formatted_original = original_template
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
            if chat_id in user_sessions:
                del user_sessions[chat_id]
            return

        node_type = node.get("type", "question")
        
        if node_type == "input_text":
            user_input = message.text
            db = SessionLocal()
            try:
                crud.create_response(db, session_id=session_data['session_id'], node_id=current_node_id, answer_text=user_input)
                next_node_id = node.get("next_node_id")
                if next_node_id:
                    send_node_message(chat_id, next_node_id)
            finally:
                db.close()
        
        elif node.get("ai_enabled", False):
            bot.send_chat_action(chat_id, 'typing')
            db = SessionLocal()
            try:
                user = crud.get_or_create_user(db, chat_id)
                options = node.get("options", [])
                if node.get("type") == "circumstance":
                    options = [{"text": node.get("option_text", "Далее")}]

                system_prompt_context = crud.build_full_context_for_ai(
                    db, session_data['session_id'], user.id,
                    node.get("text", ""), 
                    options,
                    node.get("event_type")
                )
                
                ai_answer = gigachat_handler.get_ai_response(user_message=message.text, system_prompt=system_prompt_context)
                
                if ai_answer:
                    crud.create_ai_dialogue(db, session_data['session_id'], current_node_id, message.text, ai_answer)
                    bot.reply_to(message, ai_answer, parse_mode="Markdown")
                    # После консультации снова показываем исходный вопрос
                    send_node_message(chat_id, current_node_id)
                else: 
                    bot.reply_to(message, "К сожалению, не удалось получить ответ от ассистента.")
            
            except Exception as e:
                traceback.print_exc()
                bot.reply_to(message, "Произошла внутренняя ошибка при обращении к AI-ассистенту.")
            finally:
                db.close()
        
        else:
            bot.reply_to(message, "Пожалуйста, используйте кнопки для ответа на этот вопрос.")