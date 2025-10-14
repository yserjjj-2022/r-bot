# -*- coding: utf-8 -*-
# app/modules/telegram_handler_v2.py
# ВЕРСИЯ 2.2 (14.10.2025): Финальная полная версия.
# Включает все согласованные доработки: динамические переменные, заглушки,
# обработку input_text, ai_enabled и защиту от повторных нажатий.

import random
import re
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
import traceback
from sqlalchemy.orm import Session
from decouple import config

# --- Безопасные импорты и полные заглушки ---
try:
    from app.modules.database import SessionLocal, crud
    from app.modules import gigachat_handler, state_calculator
    from app.modules.hot_reload import get_current_graph
    MODULES_AVAILABLE = True
except ImportError as e:
    print(f"⚠️ ВНИМАНИЕ: Не удалось импортировать основные модули ({e}). Используются заглушки.")
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
        def build_full_context_for_ai(db, session_id, user_id, q, opts, et, ap): return "Контекст для AI"

    class state_calculator:
        @staticmethod
        def calculate_new_state(formula, current_state):
            for var, value in current_state.items():
                if var in formula: formula = formula.replace(var, str(value))
            try: return {'score': eval(formula)}
            except: return current_state

# --- Глобальные переменные и константы ---
user_sessions = {}
INTERACTIVE_NODE_TYPES = ["task", "input_text", "ai_proactive"]
AUTOMATIC_NODE_TYPES = ["condition", "randomizer", "state"]

# -------------------------------------------------
# 1. РЕГИСТРАЦИЯ И ГЛАВНЫЙ ДИСПЕТЧЕР
# -------------------------------------------------
def register_handlers(bot: telebot.TeleBot, initial_graph_data: dict):
    print("✅ [HANDLER V2.2] Регистрация обработчиков...")

    def process_node(chat_id, node_id):
        db = SessionLocal()
        try:
            graph, session = get_current_graph(), user_sessions.get(chat_id)
            node = graph["nodes"].get(str(node_id)) if graph else None

            if not all([graph, session, node]):
                bot.send_message(chat_id, "Ошибка сессии/сценария. Начните заново: /start")
                if chat_id in user_sessions: del user_sessions[chat_id]
                return

            session['current_node_id'] = node_id
            node_type = node.get("type", "").split(':')[0]
            print(f"🚀 [PROCESS] ChatID: {chat_id}, NodeID: {node_id}, Type: {node_type}")

            if node.get("timing"): _handle_timing_node(db, bot, chat_id, node)
            elif node_type in AUTOMATIC_NODE_TYPES: _handle_automatic_node(db, bot, chat_id, node)
            elif node_type in INTERACTIVE_NODE_TYPES: _handle_interactive_node(db, bot, chat_id, node)
            else: _handle_final_node(db, bot, chat_id, node)
        
        except Exception:
            traceback.print_exc()
            bot.send_message(chat_id, "Критическая ошибка в движке. Начните заново: /start")
        finally:
            if db: db.close()

    # -------------------------------------------------
    # 2. ОБРАБОТЧИКИ ТИПОВ УЗЛОВ
    # -------------------------------------------------
    def _handle_automatic_node(db, bot, chat_id, node):
        node_type, next_node_id = node.get("type"), None
        if node_type == "state":
            if node.get("text"): _send_message(bot, chat_id, node, _format_text(db, chat_id, node["text"]))
            next_node_id = node.get("next_node_id")
        elif node_type == "condition":
            s = user_sessions[chat_id]
            res = _evaluate_condition(db, s['user_id'], s['session_id'], node.get("text", "False"))
            tr = node.get("transitions", [])
            next_node_id = (tr[0].get("next_node_id") if res and len(tr) > 0 else (tr[1].get("next_node_id") if not res and len(tr) > 1 else None))
            print(f"⚖️ [CONDITION] '{node.get('text')}' -> {res}. Next: {next_node_id}")
        elif node_type == "randomizer":
            br = node.get("branches", [])
            if br: next_node_id = random.choices(br, weights=[b.get("weight", 1) for b in br], k=1)[0].get("next_node_id")
            print(f"🎲 [RANDOMIZER] Выбрана ветка -> {next_node_id}")
        if next_node_id: process_node(chat_id, next_node_id)
        else: _handle_final_node(db, bot, chat_id, node)

    def _handle_interactive_node(db, bot, chat_id, node):
        if node.get("type").startswith("ai_proactive"):
            try:
                role, prompt = _parse_ai_proactive_prompt(node.get("type"))
                if role and prompt and MODULES_AVAILABLE:
                    s = user_sessions[chat_id]
                    context = crud.build_full_context_for_ai(db, s['session_id'], s['user_id'], prompt, node.get("options",[]), None, role)
                    ai_text = gigachat_handler.get_ai_response("", system_prompt=context)
                    bot.send_message(chat_id, ai_text, parse_mode="Markdown")
            except Exception as e: print(f"Ошибка в AI_PROACTIVE: {e}")
        _send_message(bot, chat_id, node, _format_text(db, chat_id, node.get("text", "(нет текста)")), _build_keyboard(node))

    def _handle_final_node(db, bot, chat_id, node):
        print(f"🏁 [SESSION END] ChatID: {chat_id}, Final Node: {node.get('id')}")
        if node.get("text"): _send_message(bot, chat_id, node, _format_text(db, chat_id, node.get("text")))
        bot.send_message(chat_id, "Игра завершена. Для начала новой игры используйте /start")
        s_id = user_sessions.get(chat_id, {}).get('session_id')
        if s_id: crud.end_session(db, s_id)
        if chat_id in user_sessions: del user_sessions[chat_id]

    def _handle_timing_node(db, bot, chat_id, node):
        print(f"⏰ [TIMING STUB] Обнаружена команда '{node.get('timing')}'. Игнорируется.")
        next_node_id = node.get("next_node_id")
        if next_node_id: process_node(chat_id, next_node_id)
        else: _handle_final_node(db, bot, chat_id, node)

    # -------------------------------------------------
    # 3. ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ
    # -------------------------------------------------
    def _format_text(db, chat_id, t):
        s = user_sessions[chat_id]
        states = crud.get_all_user_states(db, s['user_id'], s['session_id'])
        try: return t.format(**states)
        except Exception: return t

    def _build_keyboard(node):
        markup = InlineKeyboardMarkup()
        options = node.get("options", [])
        if not options: return None
        for i, option in enumerate(options):
            markup.add(InlineKeyboardButton(text=option["text"], callback_data=f"{node.get('id')}|{i}"))
        return markup
        
    def _send_message(bot, chat_id, node, text, markup=None):
        try:
            img = node.get("image_id")
            if img and config("SERVER_URL", default=None):
                bot.send_photo(chat_id, f"{config('SERVER_URL')}/images/{img}", caption=text, reply_markup=markup, parse_mode="Markdown")
            else:
                bot.send_message(chat_id, text, reply_markup=markup, parse_mode="Markdown")
        except Exception as e:
            print(f"Ошибка отправки сообщения: {e}")
            bot.send_message(chat_id, text)

    def _evaluate_condition(db, user_id, session_id, condition_str):
        states = crud.get_all_user_states(db, user_id, session_id)
        try: return eval(condition_str, {"__builtins__": {}, "random": random}, states)
        except Exception as e:
            print(f"Ошибка вычисления '{condition_str}': {e}")
            return False

    def _parse_ai_proactive_prompt(type_str):
        match = re.match(r'ai_proactive:(\w+)\("(.+)"\)', type_str)
        return match.groups() if match else (None, None)

    # -------------------------------------------------
    # 4. ОБРАБОТЧИКИ TELEGRAM API
    # -------------------------------------------------
    @bot.message_handler(commands=['start'])
    def start_game(message):
        chat_id = message.chat.id
        print(f"🎮 [GAME START] Новая игра для ChatID: {chat_id}")
        db = SessionLocal()
        try:
            if chat_id in user_sessions: crud.end_session(db, user_sessions[chat_id]['session_id'])
            graph = get_current_graph()
            if not graph or not MODULES_AVAILABLE:
                bot.send_message(chat_id, "Сценарий недоступен или модули не загружены.")
                return
            user = crud.get_or_create_user(db, telegram_id=chat_id)
            session_db = crud.create_session(db, user_id=user.id, graph_id=graph.get("graph_id", "default"))
            user_sessions[chat_id] = {'session_id': session_db.id, 'user_id': user.id, 'last_message_id': None}
            process_node(chat_id, graph["start_node_id"])
        finally:
            if db: db.close()

    @bot.callback_query_handler(func=lambda call: True)
    def button_callback(call):
        chat_id, session = call.message.chat.id, user_sessions.get(call.message.chat.id)
        if not session:
            bot.answer_callback_query(call.id, "Сессия истекла.", show_alert=True)
            return

        if call.message.message_id == session.get('last_message_id'):
            bot.answer_callback_query(call.id)
            return
        session['last_message_id'] = call.message.message_id
        bot.answer_callback_query(call.id)

        db = SessionLocal()
        try:

            # --- Начало блока отладки ---
            graph_debug = get_current_graph()
            print(f"🕵️‍♀️ [DEBUG | callback] Сценарий загружен: {graph_debug is not None}")
            if not graph_debug:
                bot.send_message(chat_id, "ОШИБКА: Сценарий не найден (get_current_graph() вернул None).")
                return 
            # --- Конец блока отладки ---

            node_id, btn_idx_str = call.data.split('|')
            node = get_current_graph()["nodes"].get(node_id)
            option = node["options"][int(btn_idx_str)]
            
            if "formula" in option and option["formula"]:
                states = crud.get_all_user_states(db, session['user_id'], session['session_id'])
                new_states = state_calculator.calculate_new_state(option["formula"], states)
                for k, v in new_states.items(): crud.update_user_state(db, session['user_id'], session['session_id'], k, v)
            
            crud.create_response(db, session_id=session['session_id'], node_id=node_id, answer_text=option.get("interpretation", option["text"]))

            if len(node.get("options", [])) == 1:
                print("📝 [EDIT] Убираем единственную кнопку подтверждения.")
                bot.edit_message_reply_markup(chat_id, call.message.message_id, reply_markup=None)
            else:
                original_text = _format_text(db, chat_id, node.get("text", ""))
                new_text = f"{original_text}\n\n*Ваш ответ: {option['text']}*"
                bot.edit_message_text(new_text, chat_id, call.message.message_id, reply_markup=None, parse_mode="Markdown")

            next_node_id = option.get("next_node_id") or node.get("next_node_id")
            if next_node_id: process_node(chat_id, next_node_id)
            else: _handle_final_node(db, bot, chat_id, node)
        except Exception:
            traceback.print_exc()
        finally:
            if db: db.close()

    @bot.message_handler(content_types=['text'])
    def text_message_handler(message):
        chat_id = message.chat.id
        if message.text == '/start': return
        session = user_sessions.get(chat_id)
        if not session: return

        node = get_current_graph()["nodes"].get(session.get('current_node_id'))
        if not node: return
        
        db = SessionLocal()
        try:
            if node.get("type") == "input_text":
                print(f"💬 [INPUT_TEXT] ChatID: {chat_id} получил текст.")
                crud.create_response(db, session_id=session['session_id'], node_id=node.get('id'), answer_text=message.text)
                next_node_id = node.get("next_node_id")
                if next_node_id: process_node(chat_id, next_node_id)
                else: _handle_final_node(db, bot, chat_id, node)
            
            elif node.get("ai_enabled") and MODULES_AVAILABLE:
                print(f"🤖 [AI HELP] ChatID: {chat_id} запросил помощь ИИ.")
                bot.send_chat_action(chat_id, 'typing')
                context = crud.build_full_context_for_ai(db, session['session_id'], session['user_id'], node.get("text"), node.get("options", []), None, node.get("ai_enabled"))
                ai_answer = gigachat_handler.get_ai_response(message.text, system_prompt=context)
                crud.create_ai_dialogue(db, session['session_id'], node.get('id'), message.text, ai_answer)
                bot.reply_to(message, ai_answer, parse_mode="Markdown")
            
            else:
                bot.reply_to(message, "Пожалуйста, используйте кнопки для навигации.")
        finally:
            if db: db.close()

