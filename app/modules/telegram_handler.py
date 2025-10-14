# -*- coding: utf-8 -*-
# app/modules/telegram_handler.py
# ВЕРСИЯ 2.9 (15.10.2025): MAX DEBUG
# - Максимально подробные логи в button_callback
# - SafeStateCalculator (присваивания/выражения/мульти-формулы)
# - Исправлено создание кнопок и node_text в create_response

import random
import math
import re
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
import traceback
from sqlalchemy.orm import Session
from decouple import config

# --- Импорты и заглушки ---
try:
    from app.modules.database import SessionLocal, crud
    from app.modules import gigachat_handler
    from app.modules.hot_reload import get_current_graph
    MODULES_AVAILABLE = True
except Exception as e:
    print(f"⚠️ Модули частично недоступны ({e}). Включены заглушки.")
    MODULES_AVAILABLE = False

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

# --- Безопасный калькулятор ---
class SafeStateCalculator:
    SAFE_GLOBALS = {
        "__builtins__": None,
        "random": random, "math": math,
        "int": int, "float": float, "round": round,
        "max": max, "min": min, "abs": abs,
        "True": True, "False": False, "None": None,
    }
    assign_re = re.compile(r"^\s*[A-Za-z_][A-Za-z0-9_]*\s*=")

    @classmethod
    def calculate(cls, formula: str, current_state: dict) -> dict:
        if not formula or not isinstance(formula, str):
            return current_state
        statements = [stmt.strip() for stmt in formula.split(",") if stmt.strip()]
        local_vars = dict(current_state)
        try:
            for stmt in statements:
                if cls.assign_re.match(stmt):
                    exec(stmt, cls.SAFE_GLOBALS, local_vars)
                else:
                    value = eval(stmt, cls.SAFE_GLOBALS, local_vars)
                    # Политика по умолчанию: пишем в score
                    local_vars["score"] = value
            return local_vars
        except Exception as e:
            print(f"⚠️ Ошибка формулы '{formula}': {e}")
            return current_state

# --- Глобальные ---
user_sessions = {}
INTERACTIVE_NODE_TYPES = ["task", "input_text", "ai_proactive", "question"]
AUTOMATIC_NODE_TYPES = ["condition", "randomizer", "state"]

def register_handlers(bot: telebot.TeleBot, initial_graph_data: dict):
    print("✅ [HANDLER V2.9 MAX_DEBUG] Регистрация обработчиков...")

    def process_node(chat_id, node_id):
        db = SessionLocal()
        try:
            graph, session = get_current_graph(), user_sessions.get(chat_id)
            node = graph["nodes"].get(str(node_id)) if graph else None

            if not graph:
                print("❌ process_node: graph is None")
                bot.send_message(chat_id, "Критическая ошибка: сценарий не загружен.")
                return
            if not session:
                print("❌ process_node: session is None")
                bot.send_message(chat_id, "Ошибка сессии. /start")
                return
            if not node:
                print(f"❌ process_node: node '{node_id}' not found")
                bot.send_message(chat_id, f"Ошибка сценария: узел '{node_id}' не найден.")
                return

            session['current_node_id'] = node_id
            node_type = (node.get("type") or "").split(':')[0]
            print(f"🚀 [PROCESS] ChatID={chat_id} NodeID={node_id} Type={node_type}")

            if node.get("timing"):
                _handle_timing_node(db, bot, chat_id, node)
            elif node_type in AUTOMATIC_NODE_TYPES:
                _handle_automatic_node(db, bot, chat_id, node)
            elif node_type in INTERACTIVE_NODE_TYPES:
                _handle_interactive_node(db, bot, chat_id, node_id, node)
            else:
                _handle_final_node(db, bot, chat_id, node)
        except Exception:
            traceback.print_exc()
            bot.send_message(chat_id, "Критическая ошибка движка. /start")
        finally:
            if db: db.close()

    def _handle_automatic_node(db, bot, chat_id, node):
        node_type = node.get("type")
        next_node_id = None
        if node_type == "state":
            if node.get("text"): _send_message(bot, chat_id, node, _format_text(db, chat_id, node["text"]))
            next_node_id = node.get("next_node_id")
        elif node_type == "condition":
            s = user_sessions[chat_id]
            expr = node.get("text") or node.get("condition_string") or "False"
            res = _evaluate_condition(db, s['user_id'], s['session_id'], expr)
            next_node_id = node.get("then_node_id") if res else node.get("else_node_id")
            print(f"⚖️ [CONDITION] '{expr}' -> {res}. Next={next_node_id}")
        elif node_type == "randomizer":
            br = node.get("branches", [])
            if br:
                next_node_id = random.choices(br, weights=[b.get("weight", 1) for b in br], k=1)[0].get("next_node_id")
            print(f"🎲 [RANDOMIZER] Next={next_node_id}")
        if next_node_id: process_node(chat_id, next_node_id)
        else: _handle_final_node(db, bot, chat_id, node)

    def _handle_interactive_node(db, bot, chat_id, node_id, node):
        if (node.get("type") or "").startswith("ai_proactive"):
            try:
                role, prompt = _parse_ai_proactive_prompt(node.get("type") or "")
                if role and prompt and MODULES_AVAILABLE:
                    s = user_sessions[chat_id]
                    context = crud.build_full_context_for_ai(db, s['session_id'], s['user_id'], prompt, node.get("options",[]), "proactive", role)
                    ai_text = gigachat_handler.get_ai_response("", system_prompt=context)
                    bot.send_message(chat_id, ai_text, parse_mode="Markdown")
            except Exception as e:
                print(f"AI_PROACTIVE error: {e}")
        _send_message(bot, chat_id, node, _format_text(db, chat_id, node.get("text", "(нет текста)")), _build_keyboard(node_id, node))

    def _handle_final_node(db, bot, chat_id, node):
        print(f"🏁 [SESSION END] ChatID={chat_id}")
        if node.get("text"):
            _send_message(bot, chat_id, node, _format_text(db, chat_id, node.get("text")))
        bot.send_message(chat_id, "Игра завершена. /start для новой игры")
        s_id = user_sessions.get(chat_id, {}).get('session_id')
        if s_id and MODULES_AVAILABLE: crud.end_session(db, s_id)
        if chat_id in user_sessions: del user_sessions[chat_id]

    def _handle_timing_node(db, bot, chat_id, node):
        print(f"⏰ [TIMING] Команда '{node.get('timing')}'")
        next_node_id = node.get("next_node_id")
        if next_node_id: process_node(chat_id, next_node_id)
        else: _handle_final_node(db, bot, chat_id, node)

    def _format_text(db, chat_id, t):
        s = user_sessions[chat_id]
        states = crud.get_all_user_states(db, s['user_id'], s['session_id'])
        try:
            return t.format(**states)
        except Exception:
            return t

    def _build_keyboard(node_id, node):
        markup = InlineKeyboardMarkup()
        options = node.get("options", [])
        if not options: return None
        for i, option in enumerate(options):
            markup.add(InlineKeyboardButton(text=option["text"], callback_data=f"{node_id}|{i}"))
        return markup

    def _send_message(bot, chat_id, node, text, markup=None):
        try:
            img = node.get("image_id")
            server_url = config("SERVER_URL", default=None)
            if img and server_url:
                bot.send_photo(chat_id, f"{server_url}/images/{img}", caption=text, reply_markup=markup, parse_mode="Markdown")
            else:
                bot.send_message(chat_id, text, reply_markup=markup, parse_mode="Markdown")
        except Exception as e:
            print(f"send_message error: {e}")
            bot.send_message(chat_id, text)

    def _evaluate_condition(db, user_id, session_id, condition_str):
        states = crud.get_all_user_states(db, user_id, session_id)
        try:
            return eval(condition_str, SafeStateCalculator.SAFE_GLOBALS, states)
        except Exception as e:
            print(f"condition eval error '{condition_str}': {e}")
            return False

    def _parse_ai_proactive_prompt(type_str):
        m = re.match(r'ai_proactive:(\w+)\(\"(.+)\"\)', type_str)
        return m.groups() if m else (None, None)

    # --- Telegram API ---
    @bot.message_handler(commands=['start'])
    def start_game(message):
        chat_id = message.chat.id
        print(f"🎮 [GAME START] ChatID={chat_id}, MODULES_AVAILABLE={MODULES_AVAILABLE}")
        db = SessionLocal()
        try:
            if chat_id in user_sessions and MODULES_AVAILABLE:
                crud.end_session(db, user_sessions[chat_id]['session_id'])
            graph = get_current_graph()
            if not graph or not MODULES_AVAILABLE:
                bot.send_message(chat_id, "Сценарий недоступен или модули не загружены.")
                return
            user = crud.get_or_create_user(db, telegram_id=chat_id)
            session_db = crud.create_session(db, user_id=user.id, graph_id=graph.get("graph_id", "default"))
            user_sessions[chat_id] = {'session_id': session_db.id, 'user_id': user.id, 'last_message_id': None}
            process_node(chat_id, graph["start_node_id"])
        except Exception:
            traceback.print_exc()
        finally:
            if db: db.close()

    @bot.callback_query_handler(func=lambda call: True)
    def button_callback(call):
        print("\n====== CALLBACK BEGIN ======")
        try:
            print(f"CALL from ChatID={call.message.chat.id} data='{call.data}' MODULES_AVAILABLE={MODULES_AVAILABLE}")
        except Exception:
            traceback.print_exc()

        chat_id = getattr(call.message, "chat", type("o", (), {"id": None})) .id
        session = user_sessions.get(chat_id)
        print(f"SESSION exists={session is not None} for ChatID={chat_id}")

        if not session:
            print("SESSION MISSING -> answering alert")
            try: bot.answer_callback_query(call.id, "Сессия истекла. Начните заново.", show_alert=True)
            except Exception: traceback.print_exc()
            return

        print(f"message_id current={call.message.message_id} saved={session.get('last_message_id')}")
        if call.message.message_id == session.get('last_message_id'):
            print("DUPLICATE PRESS -> ignored")
            try: bot.answer_callback_query(call.id)
            except Exception: traceback.print_exc()
            return

        session['last_message_id'] = call.message.message_id
        try: bot.answer_callback_query(call.id)
        except Exception: traceback.print_exc()

        db = SessionLocal()
        try:
            # Разбор данных
            try:
                node_id, btn_idx_str = call.data.split('|')
                print(f"PARSED node_id='{node_id}' btn_index='{btn_idx_str}'")
            except Exception as e:
                print(f"PARSE ERROR call.data='{call.data}': {e}")
                return

            graph = get_current_graph()
            print(f"GRAPH loaded={graph is not None}")
            if not graph:
                print("GRAPH IS NONE")
                return

            node = graph.get("nodes", {}).get(node_id)
            print(f"NODE found={node is not None}")
            if not node:
                print(f"NODE '{node_id}' NOT FOUND; nodes={list(graph.get('nodes', {}).keys())}")
                return

            options = node.get("options", [])
            print(f"OPTIONS len={len(options)}")
            if not options:
                print("NO OPTIONS -> final node fallback")
                _handle_final_node(db, bot, chat_id, node)
                return

            try:
                option_index = int(btn_idx_str)
                option = options[option_index]
            except Exception as e:
                print(f"OPTION INDEX ERROR: {e}")
                return

            print(f"OPTION text='{option.get('text')}' has_formula={'formula' in option and bool(option['formula'])}")

            # Применяем формулу
            if "formula" in option and option["formula"]:
                states_before = crud.get_all_user_states(db, session['user_id'], session['session_id'])
                states_after = SafeStateCalculator.calculate(option["formula"], states_before)

                print("--- CRUD DEBUG ---")
                print(f"Formula: {option['formula']}")
                print(f"States BEFORE: {states_before}")
                print(f"States AFTER : {states_after}")
                print(f"MODULES_AVAILABLE: {MODULES_AVAILABLE}")

                for k, v in states_after.items():
                    if k not in states_before or states_before[k] != v:
                        print(f"UPDATE {k}: {states_before.get(k, 'N/A')} -> {v}")
                        try:
                            crud.update_user_state(db, session['user_id'], session['session_id'], k, v)
                        except Exception:
                            print("update_user_state raised:")
                            traceback.print_exc()

            # Логируем запись ответа
            try:
                print("create_response(...)")
                crud.create_response(
                    db,
                    session_id=session['session_id'],
                    node_id=node_id,
                    answer_text=option.get("interpretation", option["text"]),
                    node_text=node.get("text", "")
                )
            except Exception:
                print("create_response raised:")
                traceback.print_exc()

            # Обновление сообщения
            if len(node.get("options", [])) == 1:
                try:
                    bot.edit_message_reply_markup(chat_id, call.message.message_id, reply_markup=None)
                except Exception: traceback.print_exc()
            else:
                try:
                    original_text = _format_text(db, chat_id, node.get("text", ""))
                    new_text = f"{original_text}\n\n*Ваш ответ: {option['text']}*"
                    bot.edit_message_text(new_text, chat_id, call.message.message_id, reply_markup=None, parse_mode="Markdown")
                except Exception: traceback.print_exc()

            # Переход
            next_node_id = option.get("next_node_id") or node.get("next_node_id")
            print(f"NEXT node_id={next_node_id}")
            if next_node_id:
                process_node(chat_id, next_node_id)
            else:
                _handle_final_node(db, bot, chat_id, node)

        except Exception:
            print("EXCEPTION IN button_callback:")
            traceback.print_exc()
        finally:
            try:
                if db: db.close()
            except Exception:
                traceback.print_exc()
        print("====== CALLBACK END ======\n")

    @bot.message_handler(content_types=['text'])
    def text_message_handler(message):
        chat_id = message.chat.id
        if message.text == '/start': return
        session = user_sessions.get(chat_id)
        if not session or not session.get('current_node_id'): return

        graph = get_current_graph()
        if not graph: return
        node = graph.get("nodes", {}).get(session.get('current_node_id'))
        if not node: return
        
        db = SessionLocal()
        try:
            if node.get("type") == "input_text":
                crud.create_response(
                    db,
                    session_id=session['session_id'],
                    node_id=session.get('current_node_id'),
                    answer_text=message.text,
                    node_text=node.get("text", "")
                )
                next_node_id = node.get("next_node_id")
                if next_node_id: process_node(chat_id, next_node_id)
                else: _handle_final_node(db, bot, chat_id, node)
            elif node.get("ai_enabled") and MODULES_AVAILABLE:
                bot.send_chat_action(chat_id, 'typing')
                context = crud.build_full_context_for_ai(db, session['session_id'], session['user_id'], node.get("text"), node.get("options", []), "reactive", node.get("ai_enabled"))
                ai_answer = gigachat_handler.get_ai_response(message.text, system_prompt=context)
                crud.create_ai_dialogue(db, session['session_id'], session.get('current_node_id'), message.text, ai_answer)
                bot.reply_to(message, ai_answer, parse_mode="Markdown")
            else:
                bot.reply_to(message, "Пожалуйста, используйте кнопки для навигации.")
        except Exception:
            traceback.print_exc()
        finally:
            if db: db.close()
