# -*- coding: utf-8 -*-
# app/modules/telegram_handler.py
# ВЕРСИЯ 4.0.5 (16.01.2026): Исправлена отправка картинок при локальном запуске (без SERVER_URL)

import random
import math
import re
import os
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
import traceback
from sqlalchemy.orm import Session
from decouple import config

try:
    from app.modules.database import SessionLocal, crud
    from app.modules.database import models  # NEW: для проверки is_paused
    from app.modules import gigachat_handler
    from app.modules.hot_reload import get_current_graph
    from app.modules.timing_engine import process_node_timing
    AI_AVAILABLE = True
except Exception as e:
    print(f"⚠️ Модули частично недоступны ({e}). Включены заглушки.")
    AI_AVAILABLE = False

    def get_current_graph(): return None
    def SessionLocal(): return None
    def process_node_timing(user_id, session_id, node_id, timing_config, callback, **context):
        print("⚠️ Timing engine заглушка: немедленный вызов callback")
        callback()

    class crud:
        @staticmethod
        def get_or_create_user(db, telegram_id): return type('obj', (), {'id': 1, 'telegram_id': telegram_id})()
        @staticmethod
        def create_session(db, user_id, graph_id): return type('obj', (), {'id': 1, 'user_id': user_id})()
        @staticmethod
        def end_session(db, session_id): pass
        @staticmethod
        def create_response(db, session_id, node_id, answer_text, node_text=""): pass
        @staticmethod
        def get_user_state(db, user_id, session_id, key, default=None): return default if default is not None else 0
        @staticmethod
        def update_user_state(db, user_id, session_id, key, value): pass
        @staticmethod
        def get_all_user_states(db, user_id, session_id): return {'score': 0}
        @staticmethod
        def create_ai_dialogue(db, session_id, node_id, user_message, ai_response): pass
        @staticmethod
        def build_full_context_for_ai(db, s_id, u_id, q, opts, et, ap): return "Контекст для AI"

# NEW: Дефолтное имя роли для заголовков
AI_DEFAULT_ROLE = config("AI_DEFAULT_ROLE", default="Мастер Игры")

class SafeStateCalculator:
    SAFE_GLOBALS = {"__builtins__": None, "random": random, "math": math,
                    "int": int, "float": float, "round": round, "max": max, "min": min, "abs": abs,
                    "True": True, "False": False, "None": None}
    assign_re = re.compile(r"^\s*[A-Za-z_][A-Za-z0-9_]*\s*=")

    @classmethod
    def calculate(cls, formula: str, current_state: dict) -> dict:
        if not formula or not isinstance(formula, str):
            return current_state
        statements = [s.strip() for s in formula.split(',') if s.strip()]
        local_vars = dict(current_state)
        try:
            for stmt in statements:
                if cls.assign_re.match(stmt):
                    exec(stmt, cls.SAFE_GLOBALS, local_vars)
                else:
                    local_vars["score"] = eval(stmt, cls.SAFE_GLOBALS, local_vars)
            return local_vars
        except Exception as e:
            print(f"⚠️ Ошибка формулы '{formula}': {e}")
            return current_state

user_sessions = {}
INTERACTIVE_NODE_TYPES = ["task", "input_text", "question", "Задача", "Вопрос"]
AUTOMATIC_NODE_TYPES = ["condition", "randomizer", "state", "Условие", "Рандомизатор", "Состояние"]

def _normalize_newlines(text: str) -> str:
    return text.replace('\\n', '\n') if isinstance(text, str) else text

def _format_text(db, chat_id, t):
    s = user_sessions.get(chat_id, {})
    try:
        states = crud.get_all_user_states(db, s.get('user_id'), s.get('session_id'))
    except Exception:
        states = {}
    try:
        return t.format(**states) if isinstance(t, str) else t
    except Exception:
        return t

def _extract_condition_targets(node):
    then_id = node.get("then_node_id") or node.get("then")
    else_id = node.get("else_node_id") or node.get("else")
    if not (then_id and else_id):
        options = node.get("options", [])
        for opt in options:
            label = (opt.get("label") or opt.get("text") or "").strip().lower()
            if label in ("then", "тогда") and not then_id:
                then_id = opt.get("next_node_id")
            elif label in ("else", "иначе") and not else_id:
                else_id = opt.get("next_node_id")
    return then_id, else_id

def _evaluate_condition_enhanced(db, user_id, session_id, condition_str):
    states = crud.get_all_user_states(db, user_id, session_id) if AI_AVAILABLE else {'score': 0}
    normalized_expr = re.sub(r'\{([a-zA-Z_]\w*)\}', r'\1', condition_str or "False")
    print(f"🔍 [CONDITION DEBUG] '{condition_str}' -> '{normalized_expr}', states={states}")
    try:
        return bool(eval(normalized_expr, SafeStateCalculator.SAFE_GLOBALS, states))
    except Exception as e:
        print(f"❌ [CONDITION ERROR] '{condition_str}' -> '{normalized_expr}': {e}")
        return False

def _save_shuffled_options(chat_id, node_id, options):
    sess = user_sessions.setdefault(chat_id, {})
    sess.setdefault('shuffled', {})
    sess['shuffled'][str(node_id)] = options

def _get_shuffled_options(chat_id, node_id):
    sess = user_sessions.get(chat_id, {})
    store = sess.get('shuffled') or {}
    return store.get(str(node_id))

def _clear_shuffled_options(chat_id, node_id):
    sess = user_sessions.get(chat_id, {})
    store = sess.get('shuffled') or {}
    if str(node_id) in store:
        del store[str(node_id)]

def register_handlers(bot: telebot.TeleBot, initial_graph_data: dict):
    print(f"✅ [HANDLER v4.0.5] Регистрация обработчиков... AI_AVAILABLE={AI_AVAILABLE}")

    def _graceful_finish(db, chat_id, node):
        s = user_sessions.get(chat_id)
        if not s:
            return
        if s.get('finished'):
            print("🏁 [FINISH] Уже завершено -> skip")
            return
        s['finished'] = True
        if node.get('text') and node.get('type') not in AUTOMATIC_NODE_TYPES:
            _send_message(bot, chat_id, node, _format_text(db, chat_id, node.get('text')))
        bot.send_message(chat_id, "Игра завершена. /start для новой игры")
        if s.get('session_id') and AI_AVAILABLE:
            crud.end_session(db, s['session_id'])
        user_sessions.pop(chat_id, None)

    def process_node(chat_id, node_id):
        db = SessionLocal()
        try:
            s = user_sessions.get(chat_id)
            if s and s.get('finished'):
                print("🚫 [PROCESS] Сессия уже завершена -> skip")
                return
            graph = get_current_graph()
            if not graph:
                bot.send_message(chat_id, "Критическая ошибка: сценарий не загружен.")
                return
            if not s:
                bot.send_message(chat_id, "Ошибка сессии. /start")
                return
            node = graph["nodes"].get(str(node_id))
            if not node:
                bot.send_message(chat_id, f"Ошибка сценария: узел '{node_id}' не найден.")
                return

            timing_config = node.get("timing")
            if timing_config:
                print(f"⏱️ [TIMING DETECTED] Узел {node_id}, конфиг: {timing_config}")

                def execute_node_callback():
                    callback_db = SessionLocal()
                    try:
                        _execute_node_logic(callback_db, bot, chat_id, node_id, node)
                    finally:
                        callback_db.close()

                context = {
                    'bot': bot, 'chat_id': chat_id,
                    'telegram_user_id': s.get('user_id'),
                    'session_reference': s.get('session_id'),
                    'current_node_id': node_id,  # ИСПРАВЛЕНО: было 'node_id'
                    'node_text': node.get('text', ''),
                    'buttons': node.get('options', []),
                    'next_node_id': node.get('next_node_id'),
                    'question_message_id': user_sessions.get(chat_id, {}).get('question_message_id')
                }

                process_node_timing(
                    user_id=s.get('user_id'), session_id=s.get('session_id'),
                    node_id=node_id, timing_config=timing_config,
                    callback=execute_node_callback, **context
                )
            else:
                _execute_node_logic(db, bot, chat_id, node_id, node)

        except Exception:
            traceback.print_exc()
            bot.send_message(chat_id, "Критическая ошибка движка. /start")
        finally:
            if db: db.close()

    def _execute_node_logic(db, bot, chat_id, node_id, node):
        s = user_sessions.get(chat_id)
        if not s:
            return
        s['current_node_id'] = node_id
        node_type = node.get("type", "")
        if node_type.startswith("ai_proactive"):
            _handle_proactive_ai_node(db, bot, chat_id, node_id, node)
        elif node_type in AUTOMATIC_NODE_TYPES:
            _handle_automatic_node(db, bot, chat_id, node)
        elif node_type in INTERACTIVE_NODE_TYPES:
            _handle_interactive_node(db, bot, chat_id, node_id, node)
        else:
            _graceful_finish(db, chat_id, node)

    def _handle_proactive_ai_node(db, bot, chat_id, node_id, node):
        try:
            type_str = node.get("type", "")
            patterns = [
                r'ai_proactive:\s*([a-zA-Z0-9_]+)\s*\("(.+?)"\)',
                r'ai_proactive:\s*([a-zA-Z0-9_]+)\s*\((.+?)\)'
            ]
            role = None; task_prompt = None
            for p in patterns:
                m = re.search(p, type_str)
                if m:
                    role, task_prompt = m.groups(); break
            if role and task_prompt and AI_AVAILABLE:
                # NEW: Определяем отображаемое имя роли
                display_role = role
                if str(role).lower() in ('true', '1', 'yes', 'on', 'default'):
                    display_role = AI_DEFAULT_ROLE

                wait_msg = bot.send_message(chat_id, "⏳ ...")
                
                s = user_sessions[chat_id]
                context = crud.build_full_context_for_ai(
                    db, s['session_id'], s['user_id'], task_prompt,
                    node.get("options", []), event_type="proactive", ai_persona=role
                )
                ai_response = gigachat_handler.get_ai_response("", system_prompt=context)
                
                if ai_response.startswith("⚠️"):
                    bot.edit_message_text(ai_response, chat_id, wait_msg.message_id)
                    crud.pause_session(db, s['session_id'])
                    return
                
                # NEW: Добавляем заголовок с ролью
                final_text = f"🎭 *{display_role}:*\n{ai_response}"
                
                try:
                    bot.edit_message_text(
                        _normalize_newlines(final_text), 
                        chat_id, 
                        wait_msg.message_id, 
                        parse_mode="Markdown"
                    )
                except Exception as e:
                    print(f"⚠️ Edit error: {e}")
                    bot.delete_message(chat_id, wait_msg.message_id)
                    bot.send_message(chat_id, _normalize_newlines(final_text), parse_mode="Markdown")
                
                crud.create_ai_dialogue(db, s['session_id'], node_id, f"PROACTIVE: {task_prompt}", ai_response)

        except Exception:
            traceback.print_exc()
        _handle_interactive_node(db, bot, chat_id, node_id, node)

    def _handle_automatic_node(db, bot, chat_id, node):
        node_type = node.get("type")
        next_node_id = None
        if node_type in ("state", "Состояние"):
            if node.get("text"):
                _send_message(bot, chat_id, node, _format_text(db, chat_id, node["text"]))
            next_node_id = node.get("next_node_id")
        elif node_type in ("condition", "Условие"):
            s = user_sessions[chat_id]
            expr = node.get("text") or node.get("condition_string") or "False"
            res = _evaluate_condition_enhanced(db, s['user_id'], s['session_id'], expr)
            then_id, else_id = _extract_condition_targets(node)
            next_node_id = then_id if res else else_id
            print(f"⚖️ [CONDITION] '{expr}' -> {res}. Переход: {'THEN -> ' + str(then_id) if res else 'ELSE -> ' + str(else_id)}")
        elif node_type in ("randomizer", "Рандомизатор"):
            br = node.get("branches", [])
            if br:
                next_node_id = random.choices(br, weights=[b.get("weight", 1) for b in br], k=1)[0].get("next_node_id")
        if next_node_id:
            process_node(chat_id, next_node_id)
        else:
            _graceful_finish(db, chat_id, node)

    def _handle_interactive_node(db, bot, chat_id, node_id, node):
        text = _format_text(db, chat_id, node.get("text", "(нет текста)"))
        options = node.get("options", []).copy()
        node_type = node.get("type", "")
        if (node_type in ("task", "Задача") or node_type.startswith("ai_proactive")) and node.get("randomize_options", False):
            random.shuffle(options)
        _save_shuffled_options(chat_id, node_id, options)
        markup = _build_keyboard_from_options(node_id, options)
        _send_message(bot, chat_id, node, text, markup)

    def _build_keyboard_from_options(node_id, options):
        if not options:
            return None
        markup = InlineKeyboardMarkup()
        for i, option in enumerate(options):
            markup.add(InlineKeyboardButton(text=option["text"], callback_data=f"{node_id}|{i}"))
        return markup

    def _send_message(bot, chat_id, node, text, markup=None):
        processed_text = _normalize_newlines(text)
        try:
            img = node.get("image_id")
            server_url = config("SERVER_URL", default=None)
            sent_msg = None

            # [FIX] Логика отправки изображений
            if img:
                if server_url:
                    # Режим Webhook / Cloud: отправляем URL
                    try:
                        sent_msg = bot.send_photo(chat_id, f"{server_url}/images/{img}", caption=processed_text, reply_markup=markup, parse_mode="Markdown")
                    except Exception as e:
                        print(f"⚠️ Ошибка отправки фото по URL: {e}. Пробую текст.")
                        # Fallback to text handled below if sent_msg is None
                else:
                    # Режим Polling / Local: отправляем файл с диска
                    try:
                        # Пытаемся найти файл. Предполагаем, что data/images в корне проекта
                        local_path = os.path.join("data", "images", img)
                        if os.path.exists(local_path):
                            with open(local_path, "rb") as photo:
                                sent_msg = bot.send_photo(chat_id, photo, caption=processed_text, reply_markup=markup, parse_mode="Markdown")
                        else:
                            print(f"⚠️ Локальный файл картинки не найден: {local_path}")
                    except Exception as e:
                         print(f"⚠️ Ошибка отправки локального фото: {e}")

            # Если фото не отправилось (или его нет), шлем текст
            if sent_msg is None:
                sent_msg = bot.send_message(chat_id, processed_text, reply_markup=markup, parse_mode="Markdown")
            
            if user_sessions.get(chat_id):
                user_sessions[chat_id]['question_message_id'] = sent_msg.message_id
        except Exception as e:
            print(f"send_message error: {e}")
            bot.send_message(chat_id, processed_text)

    @bot.message_handler(commands=['start'])
    def start_game(message):
        chat_id = message.chat.id
        db = SessionLocal()
        try:
            if chat_id in user_sessions and AI_AVAILABLE:
                crud.end_session(db, user_sessions[chat_id]['session_id'])
            graph = get_current_graph()
            if not graph or not AI_AVAILABLE:
                bot.send_message(chat_id, "Сценарий недоступен или модули не загружены.")
                return
            user = crud.get_or_create_user(db, telegram_id=chat_id)
            session_db = crud.create_session(db, user_id=user.id, graph_id=graph.get("graph_id", "default"))
            user_sessions[chat_id] = {'session_id': session_db.id, 'user_id': user.id, 'last_message_id': None, 'finished': False}
            process_node(chat_id, graph["start_node_id"])
        except Exception:
            traceback.print_exc()
        finally:
            if db: db.close()

    @bot.callback_query_handler(func=lambda call: True)
    def button_callback(call):
        chat_id = getattr(call.message, "chat", type("o", (), {"id": None})).id
        s = user_sessions.get(chat_id)
        if not s:
            try: bot.answer_callback_query(call.id, "Сессия истекла. Начните заново.", show_alert=True)
            except Exception: pass
            return
        if s.get('finished'):
            try: bot.answer_callback_query(call.id)
            except Exception: pass
            return
        if call.message.message_id == s.get('last_message_id'):
            try: bot.answer_callback_query(call.id)
            except Exception: pass
            return
        s['last_message_id'] = call.message.message_id
        try:
            bot.answer_callback_query(call.id)
        except Exception:
            pass

        db = SessionLocal()
        try:
            try:
                node_id, btn_idx_str = call.data.split('|'); btn_idx = int(btn_idx_str)
            except Exception as e:
                print(f"PARSE ERROR call.data='{call.data}': {e}")
                return
            graph = get_current_graph(); node = graph.get("nodes", {}).get(node_id) if graph else None
            if not node:
                return

            options = _get_shuffled_options(chat_id, node_id) or node.get("options", []).copy()
            if not options or btn_idx >= len(options):
                return
            option = options[btn_idx]
            _clear_shuffled_options(chat_id, node_id)

            if option.get("formula"):
                states_before = crud.get_all_user_states(db, s['user_id'], s['session_id'])
                states_after = SafeStateCalculator.calculate(option["formula"], states_before)
                for k, v in states_after.items():
                    if k not in states_before or states_before[k] != v:
                        crud.update_user_state(db, s['user_id'], s['session_id'], k, v)

            crud.create_response(db, s['session_id'], node_id, answer_text=option.get("interpretation", option["text"]), node_text=node.get("text", ""))

            try:
                if len(options) == 1:
                    bot.edit_message_reply_markup(chat_id, call.message.message_id, reply_markup=None)
                else:
                    original_text = _format_text(db, chat_id, node.get("text", ""))
                    new_text = f"{_normalize_newlines(original_text)}\n\n*Ваш ответ: {option['text']}*"
                    bot.edit_message_text(new_text, chat_id, call.message.message_id, reply_markup=None, parse_mode="Markdown")
            except Exception:
                pass

            next_node_id = option.get("next_node_id") or node.get("next_node_id")
            if next_node_id:
                process_node(chat_id, next_node_id)
            else:
                _graceful_finish(db, chat_id, node)
        except Exception:
            traceback.print_exc()
        finally:
            if db: db.close()

    @bot.message_handler(content_types=['text'])
    def text_message_handler(message):
        chat_id = message.chat.id
        if message.text == '/start':
            return
        s = user_sessions.get(chat_id)
        if not s or not s.get('current_node_id') or s.get('finished'):
            return
        
        # Проверка паузы сессии
        db_check = SessionLocal()
        try:
            session = db_check.query(models.Session).filter(models.Session.id == s['session_id']).first()
            if session and session.is_paused:
                bot.reply_to(message, "⏸️ Игра приостановлена из-за недоступности сервиса. Попробуйте позже.")
                return
        finally:
            db_check.close()
        
        graph = get_current_graph(); node = graph.get("nodes", {}).get(s.get('current_node_id')) if graph else None

        if not node:
            return
        db = SessionLocal()
        try:
            ai_role = node.get("ai_enabled")
            if ai_role and AI_AVAILABLE:
                # NEW: Определяем отображаемое имя роли
                display_role = ai_role
                if str(ai_role).lower() in ('true', '1', 'yes', 'on', 'default'):
                    display_role = AI_DEFAULT_ROLE
                
                wait_msg = bot.reply_to(message, "⏳ ...")
                
                context = crud.build_full_context_for_ai(db, s['session_id'], s['user_id'], message.text, node.get("options", []), event_type="reactive", ai_persona=ai_role)
                ai_answer = gigachat_handler.get_ai_response(message.text, system_prompt=context)
                
                if ai_answer.startswith("⚠️"):
                    bot.edit_message_text(ai_answer, chat_id, wait_msg.message_id)
                    crud.pause_session(db, s['session_id'])
                    return
                
                # NEW: Добавляем заголовок с ролью
                final_text = f"🎭 *{display_role}:*\n{ai_answer}"
                
                try:
                    bot.edit_message_text(
                        _normalize_newlines(final_text),
                        chat_id,
                        wait_msg.message_id,
                        parse_mode="Markdown"
                    )
                except Exception as e:
                    print(f"⚠️ Edit error: {e}")
                    bot.delete_message(chat_id, wait_msg.message_id)
                    bot.reply_to(message, _normalize_newlines(final_text), parse_mode="Markdown")
                
                crud.create_ai_dialogue(db, s['session_id'], s.get('current_node_id'), message.text, ai_answer)

            elif node.get("type") == "input_text":
                crud.create_response(db, s['session_id'], s.get('current_node_id'), answer_text=message.text, node_text=node.get("text", ""))
                next_node_id = node.get("next_node_id")
                if next_node_id:
                    process_node(chat_id, next_node_id)
                else:
                    _graceful_finish(db, chat_id, node)
            else:
                bot.reply_to(message, "Пожалуйста, используйте кнопки для навигации.")
        except Exception:
            traceback.print_exc()
        finally:
            if db: db.close()