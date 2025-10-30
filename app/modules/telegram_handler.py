# -*- coding: utf-8 -*-
# app/modules/telegram_handler.py — СТАБИЛЬНАЯ БАЗОВАЯ ВЕРСИЯ с минимальной интеграцией TemporalAction

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
    from app.modules.timing_engine import process_node_timing, cancel_timeout_for_session
    AI_AVAILABLE = True
except Exception as e:
    print(f"⚠️ Модули частично недоступны ({e}). Включены заглушки.")
    AI_AVAILABLE = False
    def get_current_graph(): return None
    def SessionLocal(): return None
    def process_node_timing(user_id, session_id, node_id, timing_config, callback, **context):
        print("⚠️ Timing engine заглушка: немедленный вызов callback")
        callback()
    def cancel_timeout_for_session(session_id: int) -> bool:
        return False

class SafeStateCalculator:
    """Безопасный калькулятор для выполнения формул состояния."""
    SAFE_GLOBALS = {
        "__builtins__": None,
        "random": random, "math": math,
        "int": int, "float": float, "round": round,
        "max": max, "min": min, "abs": abs,
        "True": True, "False": False, "None": None
    }
    assign_re = re.compile(r"^\s*[A-Za-z_][A-Za-z0-9_]*\s*=")

    @classmethod
    def calculate(cls, formula: str, current_state: dict) -> dict:
        """Выполняет формулу и возвращает новое состояние."""
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

# Глобальные данные сессий
user_sessions = {}

# Типы узлов
INTERACTIVE_NODE_TYPES = ["task", "input_text", "question", "Задача", "Вопрос"]
AUTOMATIC_NODE_TYPES = ["condition", "randomizer", "state", "Условие", "Рандомизатор", "Состояние"]

def _normalize_newlines(text: str) -> str:
    """Нормализует переносы строк для Telegram."""
    return text.replace('\n', '\n') if isinstance(text, str) else text

def _format_text(db, chat_id, t):
    """Форматирует текст, подставляя переменные из состояния пользователя."""
    s = user_sessions.get(chat_id, {})
    try:
        states = crud.get_all_user_states(db, s.get('user_id'), s.get('session_id'))
    except Exception:
        states = {}
    try:
        return t.format(**states) if isinstance(t, str) else t
    except Exception:
        return t

# === ОСНОВНАЯ ФУНКЦИЯ РЕГИСТРАЦИИ ОБРАБОТЧИКОВ ===

def register_handlers(bot: telebot.TeleBot, initial_graph_data: dict):
    """Регистрирует обработчики Telegram бота."""
    print(f"✅ [HANDLER v3.8 RESTORED] Регистрация обработчиков... AI_AVAILABLE={AI_AVAILABLE}")

    def _graceful_finish(db, chat_id, node):
        """Безопасное завершение игры."""
        s = user_sessions.get(chat_id)
        if not s:
            return
        if s.get('finished'):
            print("🏁 [FINISH] Уже завершено -> skip")
            return
        
        s['finished'] = True
        
        # Показать финальный текст только для интерактивных узлов
        if node.get('text') and node.get('type') not in AUTOMATIC_NODE_TYPES:
            _send_message(bot, chat_id, node, _format_text(db, chat_id, node.get('text')))
        
        bot.send_message(chat_id, "Игра завершена. /start для новой игры")
        
        # Закрыть сессию в БД
        if s.get('session_id') and AI_AVAILABLE:
            crud.end_session(db, s['session_id'])
        
        # Удалить сессию из памяти
        user_sessions.pop(chat_id, None)

    def process_node(chat_id, node_id):
        """Обрабатывает узел сценария."""
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

            # МИНИМАЛЬНАЯ ИНТЕГРАЦИЯ TimingEngine
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
                    'current_node_id': node_id,
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
            if db: 
                db.close()

    def _execute_node_logic(db, bot, chat_id, node_id, node):
        """Выполняет основную логику узла."""
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
        """Обработка AI proactive узлов."""
        try:
            type_str = node.get("type", "")
            patterns = [
                r'ai_proactive:\s*([a-zA-Z0-9_]+)\s*\("(.+?)"\)',
                r'ai_proactive:\s*([a-zA-Z0-9_]+)\s*\((.+?)\)'
            ]
            
            role = None
            task_prompt = None
            
            for pattern in patterns:
                match = re.search(pattern, type_str)
                if match:
                    role, task_prompt = match.groups()
                    break
            
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
        
        # Продолжить как обычный интерактивный узел
        _handle_interactive_node(db, bot, chat_id, node_id, node)

    def _handle_automatic_node(db, bot, chat_id, node):
        """Обработка автоматических узлов."""
        next_node_id = None
        node_type = node.get("type")
        
        if node_type in ("state", "Состояние"):
            # Выполнить формулу состояния
            formula = node.get("formula")
            if formula and AI_AVAILABLE:
                s = user_sessions.get(chat_id)
                if s:
                    try:
                        current_states = crud.get_all_user_states(db, s['user_id'], s['session_id'])
                        new_states = SafeStateCalculator.calculate(formula, current_states)
                        
                        for key, value in new_states.items():
                            if key not in current_states or current_states[key] != value:
                                crud.set_user_state(db, s['user_id'], s['session_id'], key, value)
                        
                        print(f"✅ [STATE CALC] Формула '{formula}' выполнена для узла {node.get('id', 'unknown')}")
                    except Exception as e:
                        print(f"⚠️ [STATE ERROR] Ошибка вычисления формулы '{formula}': {e}")
            
            # Отобразить текст с обновленными переменными
            if node.get("text"):
                _send_message(bot, chat_id, node, _format_text(db, chat_id, node["text"]))
            
            next_node_id = node.get("next_node_id")
        
        elif node_type in ("condition", "Условие"):
            # Условная логика
            condition_formula = node.get("formula")
            if condition_formula and AI_AVAILABLE:
                s = user_sessions.get(chat_id)
                if s:
                    try:
                        current_states = crud.get_all_user_states(db, s['user_id'], s['session_id'])
                        result = _evaluate_condition_enhanced(condition_formula, current_states)
                        then_node, else_node = _extract_condition_targets(node)
                        next_node_id = then_node if result else else_node
                        print(f"✅ [CONDITION] '{condition_formula}' = {result}, переход к {next_node_id}")
                    except Exception as e:
                        print(f"⚠️ [CONDITION ERROR] Ошибка условия '{condition_formula}': {e}")
                        next_node_id = node.get("next_node_id")
            else:
                next_node_id = node.get("next_node_id")
        
        elif node_type in ("randomizer", "Рандомизатор"):
            # Рандомизация
            branches = node.get("branches", [])
            if branches:
                weights = [branch.get("weight", 1) for branch in branches]
                selected_branch = random.choices(branches, weights=weights, k=1)[0]
                next_node_id = selected_branch.get("next_node_id")
        
        # Переход к следующему узлу или завершение
        if next_node_id:
            process_node(chat_id, next_node_id)
        else:
            _graceful_finish(db, chat_id, node)

    def _handle_interactive_node(db, bot, chat_id, node_id, node):
        """Обработка интерактивных узлов."""
        s = user_sessions.get(chat_id)
        
        # ИСПРАВЛЕНИЕ #1: Выполнить формулу узла ПЕРЕД форматированием текста
        formula = node.get("formula")
        if formula and AI_AVAILABLE and s:
            try:
                current_states = crud.get_all_user_states(db, s['user_id'], s['session_id'])
                new_states = SafeStateCalculator.calculate(formula, current_states)
                
                for key, value in new_states.items():
                    if key not in current_states or current_states[key] != value:
                        crud.set_user_state(db, s['user_id'], s['session_id'], key, value)
                
                print(f"✅ [NODE CALC] Формула '{formula}' выполнена для узла {node_id}")
            except Exception as e:
                print(f"⚠️ [NODE ERROR] Ошибка вычисления формулы '{formula}': {e}")
        
        text = _format_text(db, chat_id, node.get("text", "(нет текста)"))
        options = node.get("options", []).copy()
        
        # Сохранить порядок опций в сессии для синхронизации с callback
        if s:
            s['node_options'] = {node_id: options}
        
        markup = _build_keyboard_from_options(node_id, options)
        _send_message(bot, chat_id, node, text, markup)

    def _build_keyboard_from_options(node_id, options):
        """Создает клавиатуру из опций узла."""
        if not options:
            return None
        
        markup = InlineKeyboardMarkup()
        for i, option in enumerate(options):
            markup.add(InlineKeyboardButton(
                text=option["text"], 
                callback_data=f"{node_id}|{i}"
            ))
        return markup

    def _send_message(bot, chat_id, node, text, markup=None):
        """Отправляет сообщение с опциональной разметкой."""
        processed_text = _normalize_newlines(text)
        try:
            sent_msg = bot.send_message(chat_id, processed_text, reply_markup=markup, parse_mode="Markdown")
            if user_sessions.get(chat_id):
                user_sessions[chat_id]['question_message_id'] = sent_msg.message_id
        except Exception as e:
            print(f"send_message error: {e}")
            bot.send_message(chat_id, processed_text)

    def _evaluate_condition_enhanced(condition_formula: str, states: dict) -> bool:
        """Улучшенная оценка условий с подстановкой переменных."""
        try:
            safe_globals = SafeStateCalculator.SAFE_GLOBALS.copy()
            return bool(eval(condition_formula, safe_globals, states))
        except Exception as e:
            print(f"⚠️ Ошибка условия '{condition_formula}': {e}")
            return False

    def _extract_condition_targets(node) -> tuple:
        """Извлекает целевые узлы then/else из условного узла."""
        options = node.get("options", [])
        then_node = None
        else_node = None
        
        for option in options:
            if option.get("text", "").lower() in ["then", "да", "истина"]:
                then_node = option.get("next_node_id")
            elif option.get("text", "").lower() in ["else", "нет", "ложь"]:
                else_node = option.get("next_node_id")
        
        return then_node or node.get("next_node_id"), else_node or node.get("next_node_id")

    # === ОБРАБОТЧИКИ СОБЫТИЙ ===

    @bot.message_handler(commands=['start'])
    def start_game(message):
        """Обработчик команды /start."""
        chat_id = message.chat.id
        db = SessionLocal()
        try:
            # Закрыть предыдущую сессию
            if chat_id in user_sessions and AI_AVAILABLE:
                crud.end_session(db, user_sessions[chat_id]['session_id'])
            
            # Получить граф сценария
            graph = get_current_graph()
            if not graph or not AI_AVAILABLE:
                bot.send_message(chat_id, "Сценарий недоступен или модули не загружены.")
                return
            
            # Создать пользователя и сессию
            user = crud.get_or_create_user(db, telegram_id=chat_id)
            session_db = crud.create_session(db, user_id=user.id, graph_id=graph.get("graph_id", "default"))
            
            # Инициализировать сессию
            user_sessions[chat_id] = {
                'session_id': session_db.id,
                'user_id': user.id, 
                'last_message_id': None,
                'finished': False
            }
            
            # Начать игру
            process_node(chat_id, graph["start_node_id"])
            
        except Exception:
            traceback.print_exc()
        finally:
            if db: 
                db.close()

    @bot.callback_query_handler(func=lambda call: True)
    def button_callback(call):
        """Обработчик нажатий на кнопки."""
        chat_id = getattr(call.message, "chat", type("o", (), {"id": None})).id
        s = user_sessions.get(chat_id)
        
        if not s:
            try:
                bot.answer_callback_query(call.id, "Сессия истекла. Начните заново.", show_alert=True)
            except Exception:
                pass
            return
        
        if s.get('finished'):
            try:
                bot.answer_callback_query(call.id)
            except Exception:
                pass
            return

        # ОТМЕНА ТАЙМАУТА ПРИ НАЖАТИИ КНОПКИ
        try:
            if s.get('session_id'):
                cancel_timeout_for_session(s['session_id'])
        except Exception:
            pass

        try:
            bot.answer_callback_query(call.id)
        except Exception:
            pass

        db = SessionLocal()
        try:
            # Разбор callback_data формата "{node_id}|{index}"
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

            # Получить сохраненные опции (для синхронизации порядка)
            saved_options = s.get('node_options', {}).get(node_id)
            if saved_options:
                options = saved_options
            else:
                options = node.get("options", []).copy()
            
            if not options or btn_idx >= len(options):
                return
            
            option = options[btn_idx]

            # Выполнение формулы кнопки
            formula = option.get("formula")
            if formula and AI_AVAILABLE:
                try:
                    current_states = crud.get_all_user_states(db, s['user_id'], s['session_id'])
                    new_states = SafeStateCalculator.calculate(formula, current_states)
                    
                    for key, value in new_states.items():
                        if key not in current_states or current_states[key] != value:
                            crud.set_user_state(db, s['user_id'], s['session_id'], key, value)
                    
                    print(f"✅ [BUTTON CALC] Формула '{formula}' выполнена при нажатии '{option['text']}'")
                except Exception as e:
                    print(f"⚠️ [BUTTON ERROR] Ошибка вычисления формулы '{formula}': {e}")

            # Записать ответ в БД
            try:
                crud.create_response(
                    db, s['session_id'], node_id, 
                    answer_text=option.get("interpretation", option["text"]), 
                    node_text=node.get("text", "")
                )
            except Exception:
                pass

            # Убрать клавиатуру
            try:
                bot.edit_message_reply_markup(chat_id, call.message.message_id, reply_markup=None)
            except Exception:
                pass

            # Переход к следующему узлу
            next_node_id = option.get("next_node_id") or node.get("next_node_id")
            if next_node_id:
                process_node(chat_id, next_node_id)
            else:
                _graceful_finish(db, chat_id, node)
                
        except Exception:
            traceback.print_exc()
        finally:
            if db: 
                db.close()