# -*- coding: utf-8 -*-
# app/modules/telegram_handler.py
# ВЕРСИЯ 3.4 (16.10.2025): ИСПРАВЛЕНИЕ ЗАДВОЕНИЯ ФИНАЛЬНЫХ СООБЩЕНИЙ
# - ДОБАВЛЕНО: Подробная диагностика для выяснения проблемы с ai_proactive.
# - УЛУЧШЕН: Более гибкий регекс, устойчивый к разным форматам.
# - ИСПРАВЛЕНО: Логика дублирования сообщений в финальных узлах (предотвращение повтора для автоматических узлов).

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

# --- Безопасный калькулятор ---
class SafeStateCalculator:
    SAFE_GLOBALS = {
        "__builtins__": None, "random": random, "math": math,
        "int": int, "float": float, "round": round, "max": max, "min": min, "abs": abs,
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
                    local_vars["score"] = value
            return local_vars
        except Exception as e:
            print(f"⚠️ Ошибка формулы '{formula}': {e}")
            return current_state

# --- Глобальные переменные и константы ---
user_sessions = {}
INTERACTIVE_NODE_TYPES = ["task", "input_text", "question"]
AUTOMATIC_NODE_TYPES = ["condition", "randomizer", "state"]

# --- Вспомогательная функция для текста ---
def _normalize_newlines(text: str) -> str:
    """Заменяет текстовую последовательность '\\n' на реальный символ переноса '\n'."""
    if isinstance(text, str):
        return text.replace('\\n', '\n')
    return text

def register_handlers(bot: telebot.TeleBot, initial_graph_data: dict):
    print(f"✅ [HANDLER v3.4] Регистрация обработчиков... AI_AVAILABLE={AI_AVAILABLE}")

    def process_node(chat_id, node_id):
        db = SessionLocal()
        try:
            graph, session = get_current_graph(), user_sessions.get(chat_id)
            if not graph:
                print("❌ process_node: graph is None")
                bot.send_message(chat_id, "Критическая ошибка: сценарий не загружен.")
                return
            if not session:
                print("❌ process_node: session is None")
                bot.send_message(chat_id, "Ошибка сессии. /start")
                return
            node = graph["nodes"].get(str(node_id))
            if not node:
                print(f"❌ process_node: node '{node_id}' не найден")
                bot.send_message(chat_id, f"Ошибка сценария: узел '{node_id}' не найден.")
                return

            session['current_node_id'] = node_id
            node_type = node.get("type", "")
            print(f"🚀 [PROCESS] ChatID={chat_id} NodeID={node_id} FullType='{node_type}'")
            
            # ⭐ ДИАГНОСТИКА: Показываем весь узел для ai_proactive
            if node_id == "game_failure" or "ai_proactive" in node_type:
                print(f"🔍 [ДИАГНОСТИКА] Узел {node_id}:")
                print(f"   - type: '{node.get('type')}'")
                print(f"   - text: '{node.get('text', '')[:100]}...'")
                print(f"   - options: {len(node.get('options', []))}")
                print(f"   - ai_enabled: '{node.get('ai_enabled')}'")

            # --- ГЛАВНЫЙ МАРШРУТИЗАТОР УЗЛОВ ---
            if node_type.startswith("ai_proactive"):
                _handle_proactive_ai_node(db, bot, chat_id, node_id, node)
            elif node_type in AUTOMATIC_NODE_TYPES:
                _handle_automatic_node(db, bot, chat_id, node)
            elif node_type in INTERACTIVE_NODE_TYPES:
                _handle_interactive_node(db, bot, chat_id, node_id, node)
            else:
                _handle_terminal_node(db, bot, chat_id, node)
        except Exception:
            traceback.print_exc()
            bot.send_message(chat_id, "Критическая ошибка движка. /start")
        finally:
            if db: db.close()

    def _handle_proactive_ai_node(db, bot, chat_id, node_id, node):
        """Генерирует сообщение от ИИ, затем показывает основной контент."""
        print(f"🤖 [AI PROACTIVE] === НАЧАЛО ОБРАБОТКИ ===")
        print(f"🤖 [AI PROACTIVE] Узел: {node_id}")
        print(f"🤖 [AI PROACTIVE] AI_AVAILABLE: {AI_AVAILABLE}")
        
        type_str = node.get("type", "")
        print(f"🤖 [AI PROACTIVE] Полная строка типа: '{type_str}'")
        print(f"🤖 [AI PROACTIVE] Длина строки: {len(type_str)}")
        
        ai_message_sent = False
        
        try:
            role, task_prompt = _parse_ai_proactive_prompt(type_str)
            print(f"🤖 [AI PROACTIVE] Результат парсинга: role='{role}', task='{task_prompt}'")
            
            if role and task_prompt and AI_AVAILABLE:
                print("🤖 [AI PROACTIVE] ✅ Все условия выполнены. Генерируем ответ...")
                bot.send_chat_action(chat_id, 'typing')
                
                session = user_sessions[chat_id]
                context = crud.build_full_context_for_ai(
                    db, session['session_id'], session['user_id'], task_prompt,
                    node.get("options", []), event_type="proactive", ai_persona=role
                )
                print(f"🤖 [AI PROACTIVE] Контекст создан длиной {len(context)} символов")
                
                ai_response = gigachat_handler.get_ai_response("", system_prompt=context)
                print(f"🤖 [AI PROACTIVE] Получен ответ длиной {len(ai_response)} символов")
                
                bot.send_message(chat_id, _normalize_newlines(ai_response), parse_mode="Markdown")
                crud.create_ai_dialogue(db, session['session_id'], node_id, f"PROACTIVE: {task_prompt}", ai_response)
                ai_message_sent = True
                print("🤖 [AI PROACTIVE] ✅ Сообщение успешно отправлено!")
            else:
                print(f"🤖 [AI PROACTIVE] ❌ Условия не выполнены:")
                print(f"   - role: {role}")
                print(f"   - task_prompt: {task_prompt}")
                print(f"   - AI_AVAILABLE: {AI_AVAILABLE}")
        except Exception as e:
            print(f"❌ [AI PROACTIVE] Ошибка: {e}")
            traceback.print_exc()
        
        # Показываем основной контент узла
        if node.get("options"):
            print("🤖 [AI PROACTIVE] Показываем интерактивный контент")
            _handle_interactive_node(db, bot, chat_id, node_id, node)
        else:
            print("🤖 [AI PROACTIVE] Терминальный узел")
            if node.get("text"):
                text = _format_text(db, chat_id, node.get("text"))
                _send_message(bot, chat_id, node, text)
        
        print(f"🤖 [AI PROACTIVE] === КОНЕЦ ОБРАБОТКИ ===")

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
            print(f"⚖️ [CONDITION] '{expr}' -> {res}. Next={next_node_id}")
        elif node_type == "randomizer":
            br = node.get("branches", [])
            if br:
                next_node_id = random.choices(br, weights=[b.get("weight", 1) for b in br], k=1)[0].get("next_node_id")
            print(f"🎲 [RANDOMIZER] Next={next_node_id}")
        
        if next_node_id: 
            process_node(chat_id, next_node_id)
        else: 
            _handle_terminal_node(db, bot, chat_id, node)

    def _handle_interactive_node(db, bot, chat_id, node_id, node):
        """Показывает текст и кнопки."""
        print(f"📝 [INTERACTIVE] Узел {node_id}")
        text = _format_text(db, chat_id, node.get("text", "(нет текста)"))
        markup = _build_keyboard(node_id, node)
        _send_message(bot, chat_id, node, text, markup)

    def _handle_terminal_node(db, bot, chat_id, node):
        """Финальный узел."""
        print(f"🏁 [TERMINAL] Завершение для ChatID={chat_id}")
        
        # ИСПРАВЛЕНИЕ: Отправляем текст, только если это не автоматический узел.
        # Текст автоматических узлов (state, condition) уже был отправлен ранее.
        if node.get("text") and node.get("type") not in AUTOMATIC_NODE_TYPES:
            _send_message(bot, chat_id, node, _format_text(db, chat_id, node.get("text")))
        
        bot.send_message(chat_id, "Игра завершена. /start для новой игры")
        s_id = user_sessions.get(chat_id, {}).get('session_id')
        if s_id and AI_AVAILABLE: 
            crud.end_session(db, s_id)
        if chat_id in user_sessions: 
            del user_sessions[chat_id]

    def _handle_timing_node(db, bot, chat_id, node):
        print(f"⏰ [TIMING] Команда '{node.get('timing')}'")
        next_node_id = node.get("next_node_id")
        if next_node_id: 
            process_node(chat_id, next_node_id)
        else: 
            _handle_terminal_node(db, bot, chat_id, node)

    def _format_text(db, chat_id, t):
        s = user_sessions[chat_id]
        states = crud.get_all_user_states(db, s['user_id'], s['session_id'])
        try:
            return t.format(**states)
        except Exception:
            return t

    def _build_keyboard(node_id, node):
        markup = InlineKeyboardMarkup()
        options = node.get("options", []).copy()
        if not options: 
            return None
        
        node_type = node.get("type", "")
        if (node_type == "task" or node_type.startswith("ai_proactive")) and node.get("randomize_options", False):
            random.shuffle(options)
            print(f"🔀 Узел {node_id}: ответы перемешаны.")
        
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
        print(f"DEBUG_EVAL: type(score)={type(states.get('score'))}, value={states.get('score')}")
        try:
            return eval(condition_str, SafeStateCalculator.SAFE_GLOBALS, states)
        except Exception as e:
            print(f"condition eval error '{condition_str}': {e}")
            return False

    def _parse_ai_proactive_prompt(type_str):
        """⭐ УЛУЧШЕННЫЙ ПАРСЕР с диагностикой"""
        print(f"🔍 [PARSE] === НАЧАЛО ПАРСИНГА ===")
        print(f"🔍 [PARSE] Входная строка: '{type_str}'")
        print(f"🔍 [PARSE] Длина: {len(type_str)}")
        print(f"🔍 [PARSE] Начинается с 'ai_proactive': {type_str.startswith('ai_proactive')}")
        
        # Пробуем несколько вариантов регекса
        patterns = [
            r'ai_proactive:\s*([a-zA-Z0-9_]+)\s*\("(.+?)"\)',  # Основной
            r'ai_proactive:\s*([a-zA-Z0-9_]+)\s*\((.+?)\)',   # Без кавычек
            r'ai_proactive\s*:\s*([a-zA-Z0-9_]+)\s*\("(.+?)"\)', # С пробелами
        ]
        
        for i, pattern in enumerate(patterns):
            print(f"🔍 [PARSE] Пробуем паттерн {i+1}: {pattern}")
            m = re.search(pattern, type_str)
            if m:
                groups = m.groups()
                print(f"🔍 [PARSE] ✅ НАЙДЕНО! Группы: {groups}")
                print(f"🔍 [PARSE] === КОНЕЦ ПАРСИНГА ===")
                return groups
            else:
                print(f"🔍 [PARSE] ❌ Паттерн {i+1} не подошел")
        
        print("🔍 [PARSE] ❌ НИ ОДИН ПАТТЕРН НЕ ПОДОШЕЛ")
        print(f"🔍 [PARSE] === КОНЕЦ ПАРСИНГА ===")
        return (None, None)

    @bot.message_handler(commands=['start'])
    def start_game(message):
        chat_id = message.chat.id
        print(f"🎮 [GAME START] ChatID={chat_id}, AI_AVAILABLE={AI_AVAILABLE}")
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
            print(f"CALL from ChatID={call.message.chat.id} data='{call.data}' AI_AVAILABLE={AI_AVAILABLE}")
        except Exception:
            traceback.print_exc()

        chat_id = getattr(call.message, "chat", type("o", (), {"id": None})) .id
        session = user_sessions.get(chat_id)
        if not session:
            print("SESSION MISSING -> answering alert")
            try: 
                bot.answer_callback_query(call.id, "Сессия истекла. Начните заново.", show_alert=True)
            except Exception: 
                pass
            return

        if call.message.message_id == session.get('last_message_id'):
            print("DUPLICATE PRESS -> ignored")
            try: 
                bot.answer_callback_query(call.id)
            except Exception: 
                pass
            return

        session['last_message_id'] = call.message.message_id
        try: 
            bot.answer_callback_query(call.id)
        except Exception: 
            pass

        db = SessionLocal()
        try:
            try:
                node_id, btn_idx_str = call.data.split('|')
                btn_idx = int(btn_idx_str)
                print(f"PARSED node_id='{node_id}' btn_index={btn_idx}")
            except Exception as e:
                print(f"PARSE ERROR call.data='{call.data}': {e}")
                return

            graph = get_current_graph()
            if not graph:
                print("GRAPH IS NONE"); return

            node = graph.get("nodes", {}).get(node_id)
            if not node:
                print(f"NODE '{node_id}' NOT FOUND"); return

            options = node.get("options", []).copy()
            if (node.get("type", "") == "task" or node.get("type", "").startswith("ai_proactive")) and node.get("randomize_options", False):
                random.shuffle(options)
            
            if not options or btn_idx >= len(options):
                print("OPTION INDEX ERROR"); return
            
            option = options[btn_idx]
            print(f"OPTION text='{option.get('text')}' has_formula={'formula' in option and bool(option['formula'])}")

            if "formula" in option and option["formula"]:
                states_before = crud.get_all_user_states(db, session['user_id'], session['session_id'])
                states_after = SafeStateCalculator.calculate(option["formula"], states_before)
                print("--- CRUD DEBUG ---")
                for k, v in states_after.items():
                    if k not in states_before or states_before[k] != v:
                        print(f"UPDATE {k}: {states_before.get(k, 'N/A')} -> {v}")
                        crud.update_user_state(db, session['user_id'], session['session_id'], k, v)

            crud.create_response(db, session['session_id'], node_id,
                                 answer_text=option.get("interpretation", option["text"]),
                                 node_text=node.get("text", ""))

            if len(options) == 1:
                try: 
                    bot.edit_message_reply_markup(chat_id, call.message.message_id, reply_markup=None)
                except Exception: 
                    pass
            else:
                try:
                    original_text = _format_text(db, chat_id, node.get("text", ""))
                    new_text = f"{_normalize_newlines(original_text)}\n\n*Ваш ответ: {option['text']}*"
                    bot.edit_message_text(new_text, chat_id, call.message.message_id, reply_markup=None, parse_mode="Markdown")
                except Exception: 
                    pass
            
            next_node_id = option.get("next_node_id") or node.get("next_node_id")
            print(f"NEXT node_id={next_node_id}")
            if next_node_id:
                process_node(chat_id, next_node_id)
            else:
                _handle_terminal_node(db, bot, chat_id, node)
        except Exception:
            print("EXCEPTION IN button_callback:")
            traceback.print_exc()
        finally:
            if db: db.close()
        print("====== CALLBACK END ======\n")

    @bot.message_handler(content_types=['text'])
    def text_message_handler(message):
        chat_id = message.chat.id
        if message.text == '/start': 
            return
        session = user_sessions.get(chat_id)
        if not session or not session.get('current_node_id'): 
            return
        graph, node = get_current_graph(), None
        if graph: 
            node = graph.get("nodes", {}).get(session.get('current_node_id'))
        if not node: 
            return
        
        db = SessionLocal()
        try:
            ai_role = node.get("ai_enabled")
            if ai_role and AI_AVAILABLE:
                print(f"🤖 [AI REACTIVE] Запрос к роли '{ai_role}' на узле {session.get('current_node_id')}")
                bot.send_chat_action(chat_id, 'typing')
                context = crud.build_full_context_for_ai(
                    db, session['session_id'], session['user_id'], message.text,
                    node.get("options", []), event_type="reactive", ai_persona=ai_role
                )
                ai_answer = gigachat_handler.get_ai_response(message.text, system_prompt=context)
                crud.create_ai_dialogue(db, session['session_id'], session.get('current_node_id'), message.text, ai_answer)
                bot.reply_to(message, _normalize_newlines(ai_answer), parse_mode="Markdown")
            elif node.get("type") == "input_text":
                crud.create_response(db, session['session_id'], session.get('current_node_id'),
                                     answer_text=message.text, node_text=node.get("text", ""))
                next_node_id = node.get("next_node_id")
                if next_node_id: 
                    process_node(chat_id, next_node_id)
                else: 
                    _handle_terminal_node(db, bot, chat_id, node)
            else:
                bot.reply_to(message, "Пожалуйста, используйте кнопки для навигации.")
        except Exception:
            traceback.print_exc()
        finally:
            if db: db.close()