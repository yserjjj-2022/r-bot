# -*- coding: utf-8 -*-
# app/modules/telegram_handler.py
# Версия 8.4: Интеграция с универсальной timeout командой

import random
import re
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
import traceback
import operator
import threading
from sqlalchemy.orm import Session
from decouple import config

from app.modules.database import SessionLocal, crud
from app.modules import gigachat_handler
from app.modules import state_calculator

# Берем актуальный граф на каждом обращении
from app.modules.hot_reload import get_current_graph

# ОБНОВЛЕНО: Интеграция с универсальной timeout командой
from app.modules.timing_engine import process_node_timing, cancel_timeout_for_session, enable_timing, get_timing_status

user_sessions = {}

# ОБНОВЛЕНО: Для отслеживания активных timeout (универсальных)
active_timeout_sessions = {}  # session_id -> {'target_node': str, 'node_id': str}

# --- Глобальная функция для проверки, является ли узел финальным ---
def is_final_node(node_data):
    """Проверяет, является ли узел конечным в сценарии."""
    if not node_data:
        return True

    has_next_node = node_data.get("next_node_id") or node_data.get("then_node_id") or node_data.get("else_node_id")
    if has_next_node:
        return False

    if "options" in node_data and node_data["options"]:
        for option in node_data["options"]:
            if option.get("next_node_id"):
                return False

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

# --- Парсер мини-DSL для проактивного ИИ ---
AI_PROACTIVE_REGEX = re.compile(r'^ai_proactive:\s*([a-zA-Z_][\w-]*)\s*\("([^"]+)")\s*$')

def parse_ai_proactive_command(type_field: str):
    """
    Парсит строку type узла формата: ai_proactive: role("локальный_промпт")
    Возвращает (role, local_prompt) или (None, None), если это не команда.
    """
    if not isinstance(type_field, str):
        return None, None
    m = AI_PROACTIVE_REGEX.match(type_field.strip())
    if not m:
        return None, None
    role = m.group(1).strip()
    local_prompt = m.group(2).strip()
    return role, local_prompt

def register_handlers(bot: telebot.TeleBot, initial_graph_data: dict):
    """
    Регистрирует обработчики для Telegram-бота.
    initial_graph_data теперь игнорируется — используем get_current_graph() для hot-reload.
    """

    # ОБНОВЛЕНО: Активируем универсальную timeout систему
    enable_timing()
    timing_status = get_timing_status()
    print(f"🕐 Universal timeout system activated: {timing_status}")
    print(f"🚀 Available timing commands: {timing_status.get('available_parsers', [])}")

    def _resume_after_pause(chat_id, next_node_id, temp_message_id=None):
        """Вызывается таймером для продолжения сценария после паузы."""
        if temp_message_id:
            try:
                bot.delete_message(chat_id, temp_message_id)
            except Exception as e:
                print(f"--- [ПАУЗА] Не удалось удалить временное сообщение {temp_message_id}: {e} ---")
        send_node_message(chat_id, next_node_id)

    # ОБНОВЛЕНО: Обработчик универсального timeout fallback
    def handle_timeout_fallback(session_id: int, target_node: str):
        """Обрабатывает истечение времени универсального timeout"""
        print(f"[TIMEOUT] Timeout expired for session {session_id} → target: {target_node}")

        # Найти chat_id по session_id
        chat_id = None
        for cid, sess_info in user_sessions.items():
            if sess_info.get('session_id') == session_id:
                chat_id = cid
                break

        if chat_id:
            # Очистить активный timeout
            if session_id in active_timeout_sessions:
                del active_timeout_sessions[session_id]

            # Перейти к target узлу
            send_node_message(chat_id, target_node)
        else:
            print(f"[WARNING] Chat not found for session {session_id}")

    # --- Основная функция отправки сообщений ---
    def send_node_message(chat_id, node_id):
        db = SessionLocal()
        try:
            print(f"--- [НАВИГАЦИЯ] Попытка перехода на узел: {node_id} для чата {chat_id} ---")

            # Всегда берем актуальный граф
            graph_data = get_current_graph()
            if not graph_data:
                bot.send_message(chat_id, "Сценарий временно недоступен. Попробуйте позже.")
                return

            node = graph_data["nodes"].get(str(node_id))
            session_info = user_sessions.get(chat_id)

            if not node:
                bot.send_message(chat_id, "Произошла ошибка: узел не найден. Попробуйте начать заново с /start.")
                if chat_id in user_sessions: 
                    del user_sessions[chat_id]
                return

            if not session_info:
                bot.send_message(chat_id, "Игра завершена. Для нового начала, используйте /start.")
                return

            session_info['node_id'] = node_id
            print(f"--- [СЕССИЯ] Установлен текущий узел: {node_id} ---")

            user = crud.get_or_create_user(db, chat_id)
            node_type = node.get("type", "question")

            # --- Тип "pause" (СТАРАЯ СИСТЕМА - оставляем для обратной совместимости) ---
            if node_type == "pause":
                delay = float(node.get("delay", 1.0))
                next_node_id_next = node.get("next_node_id")
                pause_text = node.get("pause_text", "").replace('\n', '\n')
                temp_message_id = None
                if not next_node_id_next: 
                    return

                print(f"--- [ПАУЗА-СТАРАЯ] Задержка на {delay} сек. для чата {chat_id}, затем переход на {next_node_id_next} ---")

                if pause_text:
                    sent_msg = bot.send_message(chat_id, pause_text, parse_mode="Markdown")
                    temp_message_id = sent_msg.message_id
                else:
                    bot.send_chat_action(chat_id, 'typing')

                threading.Timer(delay, _resume_after_pause, args=[chat_id, next_node_id_next, temp_message_id]).start()
                return

            # --- Тип "condition" ---
            if node_type == "condition":
                result = _evaluate_condition(node.get("condition_string", ""), db, user.id, session_info['session_id'])
                next_node_id_next = node.get("then_node_id") if result else node.get("else_node_id")
                if next_node_id_next: 
                    send_node_message(chat_id, next_node_id_next)
                return

            # --- Тип "randomizer" ---
            if node_type == "randomizer":
                branches = node.get("branches", [])
                if not branches: 
                    return
                weights = [branch.get("weight", 1) for branch in branches]
                chosen_branch = random.choices(branches, weights=weights, k=1)[0]
                next_node_id_next = chosen_branch.get("next_node_id")
                if next_node_id_next: 
                    send_node_message(chat_id, next_node_id_next)
                return

            # --- НОВОЕ: Тип "ai_proactive" с мини-DSL ---
            ai_role, local_prompt = parse_ai_proactive_command(node_type)
            is_proactive = ai_role is not None and local_prompt is not None

            # Формируем базовый текст узла
            text_template = node.get("text", "")
            if node.get("type") == "state":
                text_template = node.get("state_message", "Состояние обновлено.")

            # Подстановка переменных состояния в текст узла
            current_score_str = crud.get_user_state(db, user.id, session_info['session_id'], 'score', '0')
            capital_before_str = crud.get_user_state(db, user.id, session_info['session_id'], 'capital_before', '0')
            state_variables = {'score': int(float(current_score_str)), 'capital_before': int(float(capital_before_str))}
            try:
                formatted_text = text_template.format(**state_variables)
            except (KeyError, ValueError):
                formatted_text = text_template
            final_text_to_send = formatted_text.replace('\n', '\n')

            # Подготовка клавиатуры
            markup = InlineKeyboardMarkup()
            options = node.get("options", [])
            callback_prefix = f"{node_id}"

            # Если узел проактивный — генерируем проактивную реплику ИИ перед основным текстом/кнопками
            if is_proactive:
                print(f"--- [AI-PROACTIVE] role={ai_role}, prompt='{local_prompt}', node={node_id} ---")
                opts_for_context = options
                if node.get("type") == "circumstance":
                    opts_for_context = [{"text": node.get("option_text", "Далее")}]
                try:
                    system_prompt_context = crud.build_full_context_for_ai(
                        db=db,
                        session_id=session_info['session_id'],
                        user_id=user.id,
                        current_question=local_prompt,
                        options=opts_for_context,
                        event_type=node.get("event_type"),
                        ai_persona=ai_role
                    )
                    ai_message = gigachat_handler.get_ai_response(
                        user_message="",
                        system_prompt=system_prompt_context
                    )
                    if ai_message:
                        bot.send_message(chat_id, ai_message, parse_mode="Markdown")
                except Exception:
                    traceback.print_exc()

            # Дальше — стандартная отрисовка узла

            if node.get("type") == "circumstance":
                # Один вариант "Далее"
                markup.add(InlineKeyboardButton(
                    text=node.get('option_text', 'Далее'), 
                    callback_data=f"{callback_prefix}|0|{node.get('next_node_id')}"
                ))
            elif (node.get("type") in ["question", "task"] or "ai_proactive:" in str(node.get("type", ""))) and options:
                unconditional_next_id = node.get("next_node_id")

                # РАНДОМИЗАЦИЯ ОПЦИЙ
                display_options = options.copy()
                original_indices = {}
                if node.get("randomize_options", False):
                    random.shuffle(display_options)
                    print(f"--- [РАНДОМИЗАЦИЯ] Опции для узла {node_id} перемешаны ---")

                for new_idx, option in enumerate(display_options):
                    original_idx = options.index(option)
                    original_indices[new_idx] = original_idx

                for new_idx, option in enumerate(display_options):
                    original_idx = original_indices[new_idx]
                    next_node_id_for_button = option.get("next_node_id") or unconditional_next_id
                    if not next_node_id_for_button: 
                        continue

                    markup.add(InlineKeyboardButton(
                        text=option["text"], 
                        callback_data=f"{callback_prefix}|{original_idx}|{next_node_id_for_button}"
                    ))

            # --- ЛОГИКА ОТПРАВКИ КАРТИНОК ---
            image_id = node.get("image_id")
            if image_id:
                server_url = config("SERVER_URL")
                image_url = f"{server_url}/images/{image_id}"
                try:
                    bot.send_photo(
                        chat_id=chat_id,
                        photo=image_url,
                        caption=final_text_to_send,
                        reply_markup=markup,
                        parse_mode="Markdown"
                    )
                except Exception as e:
                    print(f"ОШИБКА: Не удалось отправить фото {image_url}. {e}")
                    bot.send_message(chat_id, f"{final_text_to_send}\n\n*(Не удалось загрузить изображение)*", reply_markup=markup, parse_mode="Markdown")
            else:
                bot.send_message(chat_id, final_text_to_send, reply_markup=markup, parse_mode="Markdown")

            # ОБНОВЛЕНО: УНИВЕРСАЛЬНАЯ ОБРАБОТКА TIMEOUT КОМАНДЫ
            timing_config = node.get("timing") or node.get("Timing") or node.get("Задержка (сек)")
            if timing_config:
                print(f"--- [TIMING] Обработка timing для узла {node_id}: {timing_config} ---")

                # ОБНОВЛЕНО: Проверяем, содержит ли timing универсальную timeout команду
                if 'timeout:' in str(timing_config):
                    # Регистрируем активный timeout для отмены по клику кнопки
                    active_timeout_sessions[session_info['session_id']] = {
                        'node_id': node_id,
                        'timing_config': timing_config
                    }
                    print(f"[TIMEOUT] Registered timeout for session {session_info['session_id']}")

                # Определяем следующий узел для обычного callback
                next_node_id_cb = (node.get("next_node_id") or 
                                   node.get("then_node_id") or 
                                   node.get("else_node_id"))

                # Поддержка текста паузы
                pause_text = node.get("pause_text") or node.get("Текст паузы") or ""

                # ОБНОВЛЕНО: Расширенный контекст для универсального timeout
                def timing_callback():
                    """Callback после завершения timing процесса"""
                    # Проверить, установлен ли timeout_target_node в контексте
                    if hasattr(timing_callback, 'context') and 'timeout_target_node' in timing_callback.context:
                        target_node = timing_callback.context['timeout_target_node']
                        print(f"[TIMEOUT] Executing timeout transition: {target_node}")
                        handle_timeout_fallback(session_info['session_id'], target_node)
                    elif next_node_id_cb:
                        # Обычный переход
                        send_node_message(chat_id, next_node_id_cb)

                # ОБНОВЛЕНО: Передаем контекст для универсального timeout
                context = {
                    'bot': bot,
                    'chat_id': chat_id,
                    'pause_text': pause_text,
                    'next_node_id': next_node_id_cb,  # Для timeout:30s без override
                    'session_id': session_info['session_id']
                }

                process_node_timing(
                    user_id=user.id,
                    session_id=session_info['session_id'],
                    node_id=node_id,
                    timing_config=str(timing_config),
                    callback=timing_callback,
                    **context
                )
                
                # Сохранить контекст в callback для доступа к timeout_target_node
                timing_callback.context = context
                
                return  # timing_engine сам вызовет callback когда нужно

            # Финальный узел — завершаем сессию
            if is_final_node(node):
                print(f"--- [СЕССИЯ] Завершение сессии на финальном узле {node_id} ---")
                crud.end_session(db, session_info['session_id'])

                # ОБНОВЛЕНО: Очистка активных timeout при завершении сессии
                if session_info['session_id'] in active_timeout_sessions:
                    del active_timeout_sessions[session_info['session_id']]

                if chat_id in user_sessions:
                    del user_sessions[chat_id]
                return

            # Интерактивность узла
            is_interactive_node = (
                node.get("type") == "circumstance" or
                node.get("type") == "input_text" or
                (node.get("options") and len(node.get("options")) > 0)
            )
            next_node_id_next = node.get("next_node_id")

            # НОВОЕ: если узел проактивный и нет опций — авто-переход
            if is_proactive and (not node.get("options") or len(node.get("options")) == 0) and next_node_id_next:
                send_node_message(chat_id, next_node_id_next)
                return

            # ИСПРАВЛЕНО: Узлы с timing НЕ ДЕЛАЮТ автопереход
            timing_check_for_auto = node.get("timing") or node.get("Timing") or node.get("Задержка (сек)")
            if timing_check_for_auto:
                print(f"--- [TIMING] Узел {node_id} содержит timing, автопереход отключен ---")
                return

            # Автопереход только для узлов БЕЗ timing
            if not is_interactive_node and next_node_id_next:
                send_node_message(chat_id, next_node_id_next)

        except Exception:
            print(f"!!! КРИТИЧЕСКАЯ ОШИБКА в send_node_message для узла {node_id}!!!")
            traceback.print_exc()
            bot.send_message(chat_id, "Произошла внутренняя ошибка. Пожалуйста, начните заново: /start")
            if chat_id in user_sessions: 
                del user_sessions[chat_id]
        finally:
            db.close()

    @bot.message_handler(commands=['start'])
    def start_interview(message):
        chat_id = message.chat.id
        db = SessionLocal()
        try:
            graph_data = get_current_graph()
            if not graph_data:
                bot.send_message(chat_id, "Сценарий временно недоступен. Попробуйте позже.")
                return

            user = crud.get_or_create_user(db, telegram_id=chat_id)
            session = crud.create_session(db, user_id=user.id, graph_id=graph_data["graph_id"])
            user_sessions[chat_id] = {'session_id': session.id, 'node_id': None}
            send_node_message(chat_id, graph_data["start_node_id"])
        except Exception:
            traceback.print_exc()
        finally:
            db.close()

    @bot.callback_query_handler(func=lambda call: True)
    def handle_callback_query(call):
        """
        ОБНОВЛЕНО: Обработчик кнопок с поддержкой отмены универсального timeout
        """
        chat_id = call.message.chat.id
        session_data = user_sessions.get(chat_id)
        if not session_data:
            bot.answer_callback_query(call.id, "Сессия истекла. Начните заново: /start.", show_alert=True)
            return

        # ОБНОВЛЕНО: Отмена активного универсального timeout при нажатии кнопки
        session_id = session_data.get('session_id')
        if session_id and session_id in active_timeout_sessions:
            # Отменить timeout в timing_engine
            success = cancel_timeout_for_session(session_id)
            if success:
                print(f"[TIMEOUT] Cancelled timeout for session {session_id} due to button press")

            # Удалить из локального трекинга
            del active_timeout_sessions[session_id]

        db = SessionLocal()
        try:
            node_id_from_call, button_idx_str, next_node_id = call.data.split('|', 2)
            button_idx = int(button_idx_str)

            graph_data = get_current_graph()
            if not graph_data:
                bot.answer_callback_query(call.id, "Сценарий недоступен.", show_alert=True)
                return

            node = graph_data["nodes"].get(node_id_from_call)
            if not node:
                bot.answer_callback_query(call.id, "Ошибка: Действие для этого сообщения устарело.", show_alert=True)
                return

            user = crud.get_or_create_user(db, chat_id)
            node_type = node.get("type")

            text_to_save_in_db = "N/A"
            pressed_button_text = "N/A"
            formula_to_execute = None

            if node_type == "circumstance":
                pressed_button_text = node.get("option_text", "Далее")
                text_to_save_in_db = pressed_button_text
                formula_to_execute = node.get("formula")

            elif node_type in ["task", "question"] and node.get("options") and len(node["options"]) > button_idx:
                option_data = node["options"][button_idx]
                pressed_button_text = option_data.get('text', '')
                text_to_save_in_db = option_data.get('interpretation', pressed_button_text)
                formula_to_execute = option_data.get("formula")

            # Добавлена обработка AI проактивных узлов
            elif "ai_proactive:" in str(node_type) and node.get("options") and len(node["options"]) > button_idx:
                option_data = node["options"][button_idx]
                pressed_button_text = option_data.get('text', '')
                text_to_save_in_db = option_data.get('interpretation', pressed_button_text)
                formula_to_execute = option_data.get("formula")

            # Выполнение формулы состояния (если есть)
            if formula_to_execute:
                old_score_str = crud.get_user_state(db, user.id, session_data['session_id'], 'score', '0')
                crud.update_user_state(db, user.id, session_data['session_id'], 'capital_before', float(old_score_str))

                current_state = {'score': float(old_score_str)}
                new_score = state_calculator.calculate_new_state(formula_to_execute, current_state)
                if new_score is not None:
                    crud.update_user_state(db, user.id, session_data['session_id'], 'score', new_score)

            # Сохраняем ответ пользователя
            if text_to_save_in_db != "N/A":
                node_text_for_db = node.get('text', 'Текст узла не найден')
                crud.create_response(
                    db,
                    session_id=session_data['session_id'],
                    node_id=node_id_from_call,
                    node_text=node_text_for_db,
                    answer_text=text_to_save_in_db
                )

            bot.answer_callback_query(call.id)

            # Удаление кнопок / подтверждение
            try:
                original_template = node.get("text", "")
                score_str = crud.get_user_state(db, user.id, session_data['session_id'], 'score', '0')
                capital_before_str = crud.get_user_state(db, user.id, session_data['session_id'], 'capital_before', '0')
                try:
                    state_vars = {'score': int(float(score_str)), 'capital_before': int(float(capital_before_str))}
                    formatted_original = original_template.format(**state_vars)
                except (KeyError, ValueError):
                    formatted_original = original_template

                clean_original = formatted_original.replace('\n', '\n')
                new_text = f"{clean_original}\n\n*Ваш ответ: {pressed_button_text}*"
                bot.edit_message_text(chat_id=chat_id, message_id=call.message.message_id, text=new_text, reply_markup=None, parse_mode="Markdown")
            except Exception as e:
                print(f"--- [DEBUG] Не удалось отредактировать текст, убираем кнопки: {e}")
                try:
                    bot.edit_message_reply_markup(chat_id=chat_id, message_id=call.message.message_id, reply_markup=None)
                    bot.send_message(chat_id, f"✅ *{pressed_button_text}*", parse_mode="Markdown")
                except Exception as e2:
                    print(f"--- [DEBUG] Не удалось убрать кнопки: {e2}")
                    bot.send_message(chat_id, f"✅ *{pressed_button_text}*", parse_mode="Markdown")

            send_node_message(chat_id, next_node_id)
        except Exception:
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

        graph_data = get_current_graph()
        if not graph_data:
            bot.reply_to(message, "Сценарий временно недоступен.")
            return

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
                node_text_for_db = node.get('text', 'Текст узла не найден')
                crud.create_response(db, session_id=session_data['session_id'], node_id=current_node_id, node_text=node_text_for_db, answer_text=user_input)
                next_node_id = node.get("next_node_id")
                if next_node_id:
                    send_node_message(chat_id, next_node_id)
            finally:
                db.close()

        elif node.get("ai_enabled", False):
            # Реактивный режим ИИ (как и раньше)
            bot.send_chat_action(chat_id, 'typing')
            db = SessionLocal()
            try:
                user = crud.get_or_create_user(db, chat_id)
                options = node.get("options", [])
                if node.get("type") == "circumstance":
                    options = [{"text": node.get("option_text", "Далее")}]

                ai_persona = node.get("ai_enabled", "да")  # Берем из колонки "AI help"
                system_prompt_context = crud.build_full_context_for_ai(
                    db, session_data['session_id'], user.id,
                    node.get("text", ""), 
                    options,
                    node.get("event_type"),
                    ai_persona  # Передаем тип ИИ/роль
                )

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
                db.close()

        else:
            bot.reply_to(message, "Пожалуйста, используйте кнопки для ответа на этот вопрос.")