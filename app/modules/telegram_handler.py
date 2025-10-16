# -*- coding: utf-8 -*-
# app/modules/telegram_handler.py
# ВЕРСИЯ 3.5 (16.10.2025): ФИКС ЗАДВОЕНИЯ (флаг завершения)
# - Добавлен флаг session['finished'] для предотвращения любых повторных отправок после окончания игры.
# - Глобальные проверки флага в process_node и _handle_terminal_node.
# - Безопасное завершение из button_callback при отсутствии next_node_id.

import random
import math
import re
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
import traceback
from sqlalchemy.orm import Session
from decouple import config

try:
    from app.modules.database import SessionLocal, crud
    from app.modules import gigachat_handler
    from app.modules.hot_reload import get_current_graph
    AI_AVAILABLE = True
except Exception as e:
    print(f"⚠️ Модули частично недоступны ({e}). Включены заглушки.")
    AI_AVAILABLE = False

    def get_current_graph(): return None
    def SessionLocal(): return None

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
INTERACTIVE_NODE_TYPES = ["task", "input_text", "question"]
AUTOMATIC_NODE_TYPES = ["condition", "randomizer", "state"]

def _normalize_newlines(text: str) -> str:
    return text.replace('\\n', '\n') if isinstance(text, str) else text

def register_handlers(bot: telebot.TeleBot, initial_graph_data: dict):
    print(f"✅ [HANDLER v3.5] Регистрация обработчиков... AI_AVAILABLE={AI_AVAILABLE}")

    def _graceful_finish(db, chat_id, node):
        """Единая точка завершения игры. Учитывает флаг finished и тип узла."""
        s = user_sessions.get(chat_id)
        if not s:
            return
        if s.get('finished'):
            print("🏁 [FINISH] Уже завершено -> skip")
            return
        s['finished'] = True
        # текст повторно не отправляем для автоматических узлов
        if node.get('text') and node.get('type') not in AUTOMATIC_NODE_TYPES:
            _send_message(bot, chat_id, node, _format_text(db, chat_id, node.get('text')))
        bot.send_message(chat_id, "Игра завершена. /start для новой игры")
        if s.get('session_id') and AI_AVAILABLE:
            crud.end_session(db, s['session_id'])
        # Сессию чистим в самом конце
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

            s['current_node_id'] = node_id
            node_type = node.get("type", "")
            print(f"🚀 [PROCESS] ChatID={chat_id} NodeID={node_id} FullType='{node_type}'")

            if node_type.startswith("ai_proactive"):
                _handle_proactive_ai_node(db, bot, chat_id, node_id, node)
            elif node_type in AUTOMATIC_NODE_TYPES:
                _handle_automatic_node(db, bot, chat_id, node)
            elif node_type in INTERACTIVE_NODE_TYPES:
                _handle_interactive_node(db, bot, chat_id, node_id, node)
            else:
                _graceful_finish(db, chat_id, node)
        except Exception:
            traceback.print_exc()
            bot.send_message(chat_id, "Критическая ошибка движка. /start")
        finally:
            if db: db.close()

    def _handle_proactive_ai_node(db, bot, chat_id, node_id, node):
        try:
            type_str = node.get("type", "")
            role, task_prompt = _parse_ai_proactive_prompt(type_str)
            if role and task_prompt and AI_AVAILABLE:
                bot.send_chat_action(chat_id, 'typing')
                s = user_sessions[chat_id]
                context = crud.build_full_context_for_ai(db, s['session_id'], s['user_id'], task_prompt,
                                                         node.get("options", []), event_type="proactive", ai_persona=role)
                ai_response = gigachat_handler.get_ai_response("", system_prompt=context)
                bot.send_message(chat_id, _normalize_newlines(ai_response), parse_mode="Markdown")
                crud.create_ai_dialogue(db, s['session_id'], node_id, f"PROACTIVE: {task_prompt}", ai_response)
        except Exception:
            traceback.print_exc()
        # основной контент узла
        if node.get("options"):
            _handle_interactive_node(db, bot, chat_id, node_id, node)
        else:
            if node.get("text"):
                _send_message(bot, chat_id, node, _format_text(db, chat_id, node.get("text")))

    def _handle_automatic_node(db, bot, chat_id, node):
        node_type = node.get("type")
        next_node_id = None
        if node_type == "state":
            if node.get("text"):
                _send_message(bot, chat_id, node, _format_text(db, chat_id, node["text"]))
            next_node_id = node.get("next_node_id")
        elif node_type == "condition":
            s = user_sessions[chat_id]
            expr = node.get("text") or node.get("condition_string") or "False"
            res = _evaluate_condition(db, s['user_id'], s['session_id'], expr)
            next_node_id = node.get("then_node_id") if res else node.get("else_node_id")
        elif node_type == "randomizer":
            br = node.get("branches", [])
            if br:
                next_node_id = random.choices(br, weights=[b.get("weight", 1) for b in br], k=1)[0].get("next_node_id")
        if next_node_id:
            process_node(chat_id, next_node_id)
        else:
            _graceful_finish(db, chat_id, node)

    def _handle_interactive_node(db, bot, chat_id, node_id, node):
        text = _format_text(db, chat_id, node.get("text", "(нет текста)"))
        markup = _build_keyboard(node_id, node)
        _send_message(bot, chat_id, node, text, markup)

    def _build_keyboard(node_id, node):
        options = node.get("options", []).copy()
        if not options:
            return None
        markup = InlineKeyboardMarkup()
        node_type = node.get("type", "")
        if (node_type == "task" or node_type.startswith("ai_proactive")) and node.get("randomize_options", False):
            random.shuffle(options)
        for i, option in enumerate(options):
            markup.add(InlineKeyboardButton(text=option["text"], callback_data=f"{node_id}|{i}"))
        return markup

    def _send_message(bot, chat_id, node, text, markup=None):
        processed_text = _normalize_newlines(text)
        try:
            img = node.get("image_id")
            server_url = config("SERVER_URL", default=None)
            if img and server_url:
                bot.send_photo(chat_id, f"{server_url}/images/{img}", caption=processed_text, reply_markup=markup, parse_mode="Markdown")
            else:
                bot.send_message(chat_id, processed_text, reply_markup=markup, parse_mode="Markdown")
        except Exception as e:
            print(f"send_message error: {e}")
            bot.send_message(chat_id, processed_text)

    def _evaluate_condition(db, user_id, session_id, condition_str):
        states = crud.get_all_user_states(db, user_id, session_id)
        try:
            return eval(condition_str, SafeStateCalculator.SAFE_GLOBALS, states)
        except Exception:
            return False

    def _parse_ai_proactive_prompt(type_str):
        patterns = [r'ai_proactive:\s*([a-zA-Z0-9_]+)\s*\("(.+?)"\)', r'ai_proactive:\s*([a-zA-Z0-9_]+)\s*\((.+?)\)', r'ai_proactive\s*:\s*([a-zA-Z0-9_]+)\s*\("(.+?)"\)']
        for pattern in patterns:
            m = re.search(pattern, type_str)
            if m:
                return m.groups()
        return (None, None)

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
            print("🚫 [CALLBACK] Сессия уже завершена -> skip")
            return
        if call.message.message_id == s.get('last_message_id'):
            try: bot.answer_callback_query(call.id)
            except Exception: pass
            print("DUPLICATE PRESS -> ignored")
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
            graph = get_current_graph()
            if not graph:
                return
            node = graph.get("nodes", {}).get(node_id)
            if not node:
                return
            options = node.get("options", []).copy()
            if (node.get("type", "") == "task" or node.get("type", "").startswith("ai_proactive")) and node.get("randomize_options", False):
                random.shuffle(options)
            if not options or btn_idx >= len(options):
                return
            option = options[btn_idx]

            if option.get("formula"):
                states_before = crud.get_all_user_states(db, s['user_id'], s['session_id'])
                states_after = SafeStateCalculator.calculate(option["formula"], states_before)
                for k, v in states_after.items():
                    if k not in states_before or states_before[k] != v:
                        crud.update_user_state(db, s['user_id'], s['session_id'], k, v)

            crud.create_response(db, s['session_id'], node_id, answer_text=option.get("interpretation", option["text"]), node_text=node.get("text", ""))

            # скрываем кнопки / помечаем ответ
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
        graph = get_current_graph(); node = None
        if graph:
            node = graph.get("nodes", {}).get(s.get('current_node_id'))
        if not node:
            return
        db = SessionLocal()
        try:
            ai_role = node.get("ai_enabled")
            if ai_role and AI_AVAILABLE:
                bot.send_chat_action(chat_id, 'typing')
                context = crud.build_full_context_for_ai(db, s['session_id'], s['user_id'], message.text, node.get("options", []), event_type="reactive", ai_persona=ai_role)
                ai_answer = gigachat_handler.get_ai_response(message.text, system_prompt=context)
                crud.create_ai_dialogue(db, s['session_id'], s.get('current_node_id'), message.text, ai_answer)
                bot.reply_to(message, _normalize_newlines(ai_answer), parse_mode="Markdown")
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
