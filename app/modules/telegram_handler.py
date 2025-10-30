# -*- coding: utf-8 -*-
# app/modules/telegram_handler.py — СТАБИЛЬНАЯ БАЗОВАЯ ВЕРСИЯ (ОТКАТ)
# Полный откат к состоянию до внедрения TemporalAction и последующих правок
# БЕЗ интеграции таймеров и без дополнительных оптимизаций

import random
import math
import re
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
import traceback

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
    return text.replace('\n', '\n') if isinstance(text, str) else text

def _format_text(db, chat_id, t, local_states=None):
    s = user_sessions.get(chat_id, {})
    try:
        states = local_states if local_states is not None else crud.get_all_user_states(db, s.get('user_id'), s.get('session_id'))
    except Exception:
        states = {}
    try:
        return t.format(**states) if isinstance(t, str) else t
    except Exception:
        return t

# === РЕГИСТРАЦИЯ ОБРАБОТЧИКОВ (БЕЗ ТАЙМЕРОВ) ===

def register_handlers(bot: telebot.TeleBot, initial_graph_data: dict):
    print(f"✅ [HANDLER v3.7 BASELINE] Регистрация обработчиков... AI_AVAILABLE={AI_AVAILABLE}")

    def _graceful_finish(db, chat_id, node):
        s = user_sessions.get(chat_id)
        if not s:
            return
        if s.get('finished'):
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
            _execute_node_logic(db, bot, chat_id, node_id, node)
        except Exception:
            traceback.print_exc()
            bot.send_message(chat_id, "Критическая ошибка движка. /start")
        finally:
            if db: db.close()

    def _execute_node_logic(db, bot, chat_id, node_id, node):
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
                bot.send_chat_action(chat_id, 'typing')
                s = user_sessions[chat_id]
                context = crud.build_full_context_for_ai(
                    db, s['session_id'], s['user_id'], task_prompt,
                    node.get("options", []), event_type="proactive", ai_persona=role
                )
                ai_response = gigachat_handler.get_ai_response("", system_prompt=context)
                bot.send_message(chat_id, _normalize_newlines(ai_response), parse_mode="Markdown")
                crud.create_ai_dialogue(db, s['session_id'], node_id, f"PROACTIVE: {task_prompt}", ai_response)
        except Exception:
            traceback.print_exc()
        _handle_interactive_node(db, bot, chat_id, node_id, node)

    def _handle_automatic_node(db, bot, chat_id, node):
        next_node_id = None
        node_type = node.get("type")
        if node_type in ("state", "Состояние"):
            formula = node.get("formula")
            if formula and AI_AVAILABLE:
                s = user_sessions.get(chat_id)
                if s:
                    try:
                        current_states = crud.get_all_user_states(db, s['user_id'], s['session_id'])
                        new_states = SafeStateCalculator.calculate(formula, current_states)
                        for k, v in new_states.items():
                            if k not in current_states or current_states[k] != v:
                                crud.set_user_state(db, s['user_id'], s['session_id'], k, v)
                    except Exception as e:
                        print(f"⚠️ [STATE ERROR] {e}")
            if node.get("text"):
                _send_message(bot, chat_id, node, _format_text(db, chat_id, node["text"]))
            next_node_id = node.get("next_node_id")
        elif node_type in ("condition", "Условие"):
            next_node_id = node.get("next_node_id")
        elif node_type in ("randomizer", "Рандомизатор"):
            br = node.get("branches", [])
            if br:
                next_node_id = random.choices(br, weights=[b.get("weight", 1) for b in br], k=1)[0].get("next_node_id")
        if next_node_id:
            process_node(chat_id, next_node_id)
        else:
            _graceful_finish(db, chat_id, node)

    def _handle_interactive_node(db, bot, chat_id, node_id, node):
        s = user_sessions.get(chat_id)
        # Выполнить формулу узла (если есть) и использовать локальные значения для форматирования
        local_states = {}
        formula = node.get("formula")
        if formula and AI_AVAILABLE and s:
            try:
                current_states = crud.get_all_user_states(db, s['user_id'], s['session_id'])
                local_states = SafeStateCalculator.calculate(formula, current_states)
                for k, v in local_states.items():
                    if k not in current_states or current_states[k] != v:
                        crud.set_user_state(db, s['user_id'], s['session_id'], k, v)
            except Exception as e:
                print(f"⚠️ [NODE ERROR] {e}")
        text = _format_text(db, chat_id, node.get("text", "(нет текста)"), local_states or None)
        options = node.get("options", []).copy()
        if s:
            s['node_options'] = {node_id: options}
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
        try:
            bot.answer_callback_query(call.id)
        except Exception:
            pass
        db = SessionLocal()
        try:
            try:
                node_id, btn_idx_str = call.data.split('|')
                btn_idx = int(btn_idx_str)
            except Exception as e:
                print(f"PARSE ERROR call.data='{call.data}': {e}")
                return
            graph = get_current_graph()
            node = graph.get("nodes", {}).get(node_id) if graph else None
            if not node:
                return
            options = s.get('node_options', {}).get(node_id) or node.get("options", []).copy()
            if not options or btn_idx >= len(options):
                return
            option = options[btn_idx]
            formula = option.get("formula")
            if formula and AI_AVAILABLE:
                try:
                    current_states = crud.get_all_user_states(db, s['user_id'], s['session_id'])
                    new_states = SafeStateCalculator.calculate(formula, current_states)
                    for k, v in new_states.items():
                        if k not in current_states or current_states[k] != v:
                            crud.set_user_state(db, s['user_id'], s['session_id'], k, v)
                except Exception as e:
                    print(f"⚠️ [BUTTON ERROR] {e}")
            try:
                crud.create_response(db, s['session_id'], node_id, answer_text=option.get("interpretation", option["text"]), node_text=node.get("text", ""))
            except Exception:
                pass
            try:
                bot.edit_message_reply_markup(chat_id, call.message.message_id, reply_markup=None)
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
