# -*- coding: utf-8 -*-
# app/modules/telegram_handler_CLEAN_FULL.py
# ВЕРСИЯ 9.1 (ZERO-TIME): Полностью удалена интеграция с timing_engine.
# Сохранен весь остальной функционал: AI, DB, State, Buttons, etc.

import random
import re
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
import traceback
import operator
from sqlalchemy.orm import Session
from decouple import config

# Безопасные импорты, чтобы код работал даже если модули отсутствуют
try:
    from app.modules.database import SessionLocal, crud
    from app.modules import gigachat_handler
    from app.modules import state_calculator
    from app.modules.hot_reload import get_current_graph
    MODULES_AVAILABLE = True
except ImportError as e:
    print(f"ПРЕДУПРЕЖДЕНИЕ: Один или несколько основных модулей не найдены: {e}")
    MODULES_AVAILABLE = False
    # Создаем заглушки, чтобы приложение не падало
    def get_current_graph(): return None
    class crud:
        @staticmethod
        def get_or_create_user(db, telegram_id): pass
        @staticmethod
        def create_session(db, user_id, graph_id): return type('obj', (object,), {'id': 0})()
        @staticmethod
        def get_user_state(db, user_id, session_id, key, default): return default
        @staticmethod
        def update_user_state(db, user_id, session_id, key, value): pass
        @staticmethod
        def create_response(db, session_id, node_id, node_text, answer_text): pass
        @staticmethod
        def end_session(db, session_id): pass
        @staticmethod
        def build_full_context_for_ai(db, session_id, user_id, current_question, options, event_type, ai_persona): return ""
        @staticmethod
        def create_ai_dialogue(db, session_id, node_id, user_message, ai_response): pass
    def SessionLocal(): return None

user_sessions = {}

# --- Вспомогательные функции ---

def is_final_node(node_data):
    """
    УПРОЩЕНО: Проверяет, является ли узел конечным.
    Больше не учитывает timing-команды.
    """
    if not node_data:
        return True

    has_next_node = (node_data.get("next_node_id") or 
                     node_data.get("then_node_id") or 
                     node_data.get("else_node_id"))
    if has_next_node:
        return False

    if "options" in node_data and node_data["options"]:
        for option in node_data["options"]:
            if option.get("next_node_id"):
                return False

    if "branches" in node_data and node_data["branches"]:
        return False

    return True

def _evaluate_condition(condition_str: str, db: Session, user_id: int, session_id: int) -> bool:
    """Безопасно вычисляет строку-условие."""
    ops = {'>': operator.gt, '<': operator.lt, '>=': operator.ge, '<=': operator.le, '==': operator.eq, '!=': operator.ne}
    try:
        match = re.match(r'\\{(\\w+)\\}\\s*([<>=!]+)\\s*(.+)', condition_str)
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

def parse_ai_proactive_command(type_field: str):
    """Парсит строку type узла формата: ai_proactive: role("локальный_промпт")"""
    AI_PROACTIVE_REGEX = re.compile(r'^ai_proactive:\\s*([A-Za-z_][\\w-])\\s*\\"([^\\"]+)\\"\\s*$')
    if not isinstance(type_field, str):
        return None, None
    m = AI_PROACTIVE_REGEX.match(type_field.strip())
    if not m:
        return None, None
    return m.group(1).strip(), m.group(2).strip()

# --- Основная логика ---

def register_handlers(bot: telebot.TeleBot, initial_graph_data: dict):
    """
    УПРОЩЕНО: Регистрирует обработчики.
    Больше не активирует timing_engine.
    """
    print("✅ [CLEAN HANDLER] Регистрация обработчиков...")

    def send_node_message(chat_id, node_id):
        """
        КЛЮЧЕВОЕ ИЗМЕНЕНИЕ: Полностью удалена вся логика, связанная с timing.
        Только отправка сообщений и мгновенные переходы.
        """
        db = SessionLocal()
        try:
            print(f"--- [НАВИГАЦИЯ] Переход на узел: {node_id} для чата {chat_id} ---")

            if not MODULES_AVAILABLE:
                bot.send_message(chat_id, "Ошибка конфигурации: основные модули недоступны.")
                return
                
            graph_data = get_current_graph()
            if not graph_data:
                bot.send_message(chat_id, "Сценарий временно недоступен.")
                return

            node = graph_data["nodes"].get(str(node_id))
            session_info = user_sessions.get(chat_id)

            if not node:
                bot.send_message(chat_id, "Ошибка: узел не найден. Начните заново: /start.")
                if chat_id in user_sessions: del user_sessions[chat_id]
                return

            if not session_info:
                bot.send_message(chat_id, "Игра завершена. Для нового начала: /start.")
                return

            session_info['node_id'] = node_id
            user = crud.get_or_create_user(db, chat_id)
            node_type = node.get("type", "question")

            # --- УДАЛЕНО: обработка типа "pause" и вся логика timing_engine ---

            if node_type == "condition":
                result = _evaluate_condition(node.get("condition_string", ""), db, user.id, session_info['session_id'])
                next_node_id_next = node.get("then_node_id") if result else node.get("else_node_id")
                if next_node_id_next: send_node_message(chat_id, next_node_id_next)
                return

            if node_type == "randomizer":
                branches = node.get("branches", [])
                if not branches: return
                weights = [branch.get("weight", 1) for branch in branches]
                chosen_branch = random.choices(branches, weights=weights, k=1)[0]
                next_node_id_next = chosen_branch.get("next_node_id")
                if next_node_id_next: send_node_message(chat_id, next_node_id_next)
                return
            
            ai_role, local_prompt = parse_ai_proactive_command(node_type)
            is_proactive = ai_role is not None

            text_template = node.get("text", "")
            if node.get("type") == "state":
                text_template = node.get("state_message", "Состояние обновлено.")

            current_score_str = crud.get_user_state(db, user.id, session_info['session_id'], 'score', '0')
            capital_before_str = crud.get_user_state(db, user.id, session_info['session_id'], 'capital_before', '0')
            state_variables = {'score': int(float(current_score_str)), 'capital_before': int(float(capital_before_str))}
            try:
                formatted_text = text_template.format(**state_variables)
            except (KeyError, ValueError):
                formatted_text = text_template
            final_text_to_send = formatted_text.replace('\\n', '\n')

            markup = InlineKeyboardMarkup()
            options = node.get("options", [])
            callback_prefix = f"{node_id}"

            if is_proactive:
                opts_for_context = options if node.get("type") != "circumstance" else [{"text": node.get("option_text", "Далее")}]
                try:
                    system_prompt_context = crud.build_full_context_for_ai(db, session_info['session_id'], user.id, local_prompt, opts_for_context, node.get("event_type"), ai_role)
                    ai_message = gigachat_handler.get_ai_response(user_message="", system_prompt=system_prompt_context)
                    if ai_message:
                        bot.send_message(chat_id, ai_message, parse_mode="Markdown")
                except Exception:
                    traceback.print_exc()

            if node.get("type") == "circumstance":
                markup.add(InlineKeyboardButton(text=node.get('option_text', 'Далее'), callback_data=f"{callback_prefix}|0|{node.get('next_node_id')}"))
            elif (node.get("type") in ["question", "task"] or is_proactive) and options:
                unconditional_next_id = node.get("next_node_id")
                display_options = options.copy()
                if node.get("randomize_options", False):
                    random.shuffle(display_options)
                for new_idx, option in enumerate(display_options):
                    original_idx = options.index(option)
                    next_node_id_for_button = option.get("next_node_id") or unconditional_next_id
                    if not next_node_id_for_button: continue
                    markup.add(InlineKeyboardButton(text=option["text"], callback_data=f"{callback_prefix}|{original_idx}|{next_node_id_for_button}"))

            image_id = node.get("image_id")
            if image_id:
                server_url = config("SERVER_URL", default="")
                image_url = f"{server_url}/images/{image_id}"
                try:
                    bot.send_photo(chat_id=chat_id, photo=image_url, caption=final_text_to_send, reply_markup=markup, parse_mode="Markdown")
                except Exception:
                    bot.send_message(chat_id, f"{final_text_to_send}\n\n*(Не удалось загрузить изображение)*", reply_markup=markup, parse_mode="Markdown")
            else:
                bot.send_message(chat_id, final_text_to_send, reply_markup=markup, parse_mode="Markdown")

            if is_final_node(node):
                print(f"--- [СЕССИЯ] Завершение на финальном узле {node_id} ---")
                if db: crud.end_session(db, session_info['session_id'])
                if chat_id in user_sessions: del user_sessions[chat_id]
                return

            is_interactive_node = (
                node.get("type") in ["question", "task", "circumstance", "input_text"] and
                (node.get("options") and len(node.get("options")) > 0 or node.get("type") == "input_text")
            )

            if not is_interactive_node and next_node_id_next:
                send_node_message(chat_id, next_node_id_next)

        except Exception:
            print(f"!!! КРИТИЧЕСКАЯ ОШИБКА в send_node_message для узла {node_id}!!!")
            traceback.print_exc()
            bot.send_message(chat_id, "Произошла внутренняя ошибка. Начните заново: /start")
            if chat_id in user_sessions: del user_sessions[chat_id]
        finally:
            if db: db.close()

    @bot.message_handler(commands=['start'])
    def start_interview(message):
        chat_id = message.chat.id
        db = SessionLocal()
        try:
            if not MODULES_AVAILABLE:
                bot.send_message(chat_id, "Ошибка конфигурации: основные модули недоступны.")
                return

            graph_data = get_current_graph()
            if not graph_data:
                bot.send_message(chat_id, "Сценарий временно недоступен.")
                return

            user = crud.get_or_create_user(db, telegram_id=chat_id)
            session = crud.create_session(db, user_id=user.id, graph_id=graph_data["graph_id"])
            user_sessions[chat_id] = {'session_id': session.id, 'node_id': None}
            send_node_message(chat_id, graph_data["start_node_id"])
        finally:
            if db: db.close()

    @bot.callback_query_handler(func=lambda call: True)
    def handle_callback_query(call):
        chat_id = call.message.chat.id
        session_data = user_sessions.get(chat_id)
        if not session_data:
            bot.answer_callback_query(call.id, "Сессия истекла. Начните заново: /start.", show_alert=True)
            return

        db = SessionLocal()
        try:
            if not MODULES_AVAILABLE: return
            
            node_id_from_call, button_idx_str, next_node_id = call.data.split('|', 2)
            button_idx = int(button_idx_str)

            graph_data = get_current_graph()
            node = graph_data["nodes"].get(node_id_from_call) if graph_data else None
            if not node:
                bot.answer_callback_query(call.id, "Ошибка: Действие для этого сообщения устарело.", show_alert=True)
                return

            user = crud.get_or_create_user(db, chat_id)
            node_type = node.get("type")
            
            text_to_save_in_db, pressed_button_text, formula_to_execute = "N/A", "N/A", None

            if node_type == "circumstance":
                pressed_button_text = node.get("option_text", "Далее")
                text_to_save_in_db = pressed_button_text
                formula_to_execute = node.get("formula")
            elif (node_type in ["task", "question"] or "ai_proactive:" in str(node_type)) and node.get("options") and len(node["options"]) > button_idx:
                option_data = node["options"][button_idx]
                pressed_button_text = option_data.get('text', '')
                text_to_save_in_db = option_data.get('interpretation', pressed_button_text)
                formula_to_execute = option_data.get("formula")

            if formula_to_execute:
                old_score_str = crud.get_user_state(db, user.id, session_data['session_id'], 'score', '0')
                crud.update_user_state(db, user.id, session_data['session_id'], 'capital_before', float(old_score_str))
                current_state = {'score': float(old_score_str)}
                new_score = state_calculator.calculate_new_state(formula_to_execute, current_state)
                if new_score is not None:
                    crud.update_user_state(db, user.id, session_data['session_id'], 'score', new_score)

            if text_to_save_in_db != "N/A":
                node_text_for_db = node.get('text', 'Текст узла не найден')
                crud.create_response(db, session_id=session_data['session_id'], node_id=node_id_from_call, node_text=node_text_for_db, answer_text=text_to_save_in_db)

            bot.answer_callback_query(call.id)
            
            try:
                original_template = node.get("text", "")
                score_str = crud.get_user_state(db, user.id, session_data['session_id'], 'score', '0')
                capital_before_str = crud.get_user_state(db, user.id, session_data['session_id'], 'capital_before', '0')
                state_vars = {'score': int(float(score_str)), 'capital_before': int(float(capital_before_str))}
                formatted_original = original_template.format(**state_vars)
                clean_original = formatted_original.replace('\\n', '\n')
                new_text = f"{clean_original}\n\n*Ваш ответ: {pressed_button_text}*"
                bot.edit_message_text(chat_id=chat_id, message_id=call.message.message_id, text=new_text, reply_markup=None, parse_mode="Markdown")
            except Exception:
                bot.edit_message_reply_markup(chat_id=chat_id, message_id=call.message.message_id, reply_markup=None)
                bot.send_message(chat_id, f"✅ *{pressed_button_text}*", parse_mode="Markdown")

            send_node_message(chat_id, next_node_id)
        except Exception:
            traceback.print_exc()
        finally:
            if db: db.close()

    @bot.message_handler(content_types=['text'])
    def handle_text_message(message):
        if message.text.startswith('/start'):
            start_interview(message)
            return

        chat_id = message.chat.id
        session_data = user_sessions.get(chat_id)
        if not session_data or not session_data.get('node_id'):
            bot.reply_to(message, "Игра уже завершена. /start для новой.")
            return

        current_node_id = session_data['node_id']
        graph_data = get_current_graph()
        if not graph_data:
            bot.reply_to(message, "Сценарий временно недоступен.")
            return

        node = graph_data["nodes"].get(current_node_id)
        if is_final_node(node):
            bot.reply_to(message, "Игра окончена. Спасибо! /start для новой игры.")
            if chat_id in user_sessions: del user_sessions[chat_id]
            return

        node_type = node.get("type", "question")
        if node_type == "input_text":
            user_input = message.text
            db = SessionLocal()
            try:
                node_text_for_db = node.get('text', 'Текст узла не найден')
                crud.create_response(db, session_id=session_data['session_id'], node_id=current_node_id, node_text=node_text_for_db, answer_text=user_input)
                next_node_id = node.get("next_node_id")
                if next_node_id:
                    send_node_message(chat_id, next_node_id)
            finally:
                if db: db.close()

        elif node.get("ai_enabled", False):
            bot.send_chat_action(chat_id, 'typing')
            db = SessionLocal()
            try:
                user = crud.get_or_create_user(db, chat_id)
                options = node.get("options", [])
                if node.get("type") == "circumstance":
                    options = [{"text": node.get("option_text", "Далее")}]
                ai_persona = node.get("ai_enabled", "да")
                system_prompt_context = crud.build_full_context_for_ai(db, session_data['session_id'], user.id, node.get("text", ""), options, node.get("event_type"), ai_persona)
                ai_answer = gigachat_handler.get_ai_response(user_message=message.text, system_prompt=system_prompt_context)
                if ai_answer:
                    crud.create_ai_dialogue(db, session_data['session_id'], current_node_id, message.text, ai_answer)
                    bot.reply_to(message, ai_answer, parse_mode="Markdown")
                    send_node_message(chat_id, current_node_id)
                else: 
                    bot.reply_to(message, "К сожалению, не удалось получить ответ от ассистента.")
            except Exception:
                traceback.print_exc()
                bot.reply_to(message, "Произошла внутренняя ошибка при обращении к AI-ассистенту.")
            finally:
                if db: db.close()
        else:
            bot.reply_to(message, "Пожалуйста, используйте кнопки для ответа на этот вопрос.")

