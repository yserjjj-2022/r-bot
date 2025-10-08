# -*- coding: utf-8 -*-

"""

R-Bot Timing Engine - система временных механик с SIMPLE DAILY системой

ОБНОВЛЕНИЯ:

08.10.2025 - SIMPLE DAILY FIX: Минимальная daily система с прямым send_node_message
06.10.2025 - ДОБАВЛЕНЫ адаптивные countdown сообщения
06.10.2025 - Умное форматирование времени  
06.10.2025 - Silent Mode для сценарных timeout'ов
06.10.2025 - Контроль экспозиции с preset'ами

DSL команды:

- timeout:15s:no_answer - интерактивный timeout с countdown
- timeout:5s:slow - тихий timeout для драматургии
- typing:5s:Анализ:clean - прогресс-бар с preset'ами
- process:3s:Обработка:fast - статический процесс
- daily@18:40:MSK:until:2025-10-17:wd>final_questions - НОВОЕ: календарная daily система

"""

import threading
import time
import re
import logging
from datetime import timedelta, datetime, date
from typing import Dict, Any, Callable, Optional, List, Set
import pytz
from app.modules.database.models import ActiveTimer, utc_now
from app.modules.database import SessionLocal

TIMING_ENABLED = True
logger = logging.getLogger(__name__)

class TimingEngine:
    """
    Timing Engine с адаптивными countdown сообщениями, Silent Mode
    и SIMPLE DAILY системой
    """
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if hasattr(self, 'initialized'):
            return

        self.enabled = TIMING_ENABLED
        self.active_timers: Dict[str, threading.Timer] = {}
        self.parsers = self._init_parsers()
        self.executors = self._init_executors()
        self.presets = self._init_presets()

        # Для timeout задач
        self.cancelled_tasks: Set[int] = set()
        self.active_timeouts: Dict[int, threading.Thread] = {}
        self.debug_timers: Dict[int, Dict] = {}

        # Адаптивные шаблоны countdown сообщений
        self.countdown_templates = self._init_countdown_templates()

        # ПРОСТАЯ DAILY СИСТЕМА
        self.active_daily_configs = {}  # daily конфигурации  
        self.daily_participation_stats = {}  # статистика участия

        self.initialized = True
        logger.info(f"TimingEngine initialized with Simple Daily. Enabled: {self.enabled}")
        print(f"[TIMING-ENGINE] TimingEngine initialized with enabled={self.enabled}")
        print(f"[TIMING-ENGINE] Available presets: {list(self.presets.keys())}")
        print(f"[TIMING-ENGINE] Available commands: {list(self.parsers.keys())}")
        print(f"[TIMING-ENGINE] SIMPLE DAILY system: ✅")

        if self.enabled:
            try:
                self.restore_timers_from_db()
                self.cleanup_expired_timers()
            except Exception as e:
                logger.error(f"Failed to restore/cleanup timers on init: {e}")

    # ============================================================================
    # SIMPLE DAILY СИСТЕМА
    # ============================================================================

    def _parse_daily(self, cmd_str: str) -> Dict[str, Any]:
        """SIMPLE DAILY: Парсинг календарных daily команд"""
        print(f"[SIMPLE-DAILY] Parsing: {cmd_str}")

        # daily@HH:MM:TZN:until:YYYY-MM-DD:wd>node
        pattern = r'^daily@(\d{1,2}):(\d{2})(?::([A-Z]{3}))?(?::until:(\d{4}-\d{2}-\d{2}))?(?::(wd))?(?:>([^\s]+))?$'
        match = re.match(pattern, cmd_str)

        if match:
            hour = int(match.group(1))
            minute = int(match.group(2))
            timezone_str = match.group(3) or 'MSK'
            until_date_str = match.group(4)
            workdays_only = bool(match.group(5))
            on_complete_node = match.group(6)

            until_date = datetime.strptime(until_date_str, '%Y-%m-%d').date() if until_date_str else (datetime.now().date() + timedelta(days=1))

            result = {
                'type': 'daily',
                'hour': hour, 'minute': minute, 'timezone': timezone_str,
                'until_date': until_date, 'workdays_only': workdays_only,
                'on_complete_node': on_complete_node, 'original': cmd_str
            }
            print(f"[SIMPLE-DAILY] Parsed: {result}")
            return result

        return None

    def _execute_daily(self, command: Dict[str, Any], callback: Callable, **context) -> None:
        """SIMPLE DAILY: Исполнитель календарной daily системы"""
        session_id = context.get('session_id')
        chat_id = context.get('chat_id')
        bot = context.get('bot')

        if not all([session_id, chat_id, bot]):
            print(f"[SIMPLE-DAILY] Missing context, fallback to callback")
            callback()
            return

        print(f"[SIMPLE-DAILY] Starting daily cycle for session {session_id}")

        # Сохраняем конфигурацию для планирования
        daily_key = f"daily_{session_id}_{command['hour']}_{command['minute']}"
        self.active_daily_configs[daily_key] = {
            'command': command,
            'callback': callback,  
            'context': context
        }

        # Инициализируем статистику
        self.daily_participation_stats[daily_key] = {
            'participated_days': 0,
            'total_days': 0,
            'start_date': datetime.now().date()
        }

        # Выполняем первый callback (пользователь уже в daily_start, переходит к циклу)
        callback()

        # Планируем следующий daily timer
        self._schedule_next_daily(daily_key)

    def _schedule_next_daily(self, daily_key: str):
        """SIMPLE DAILY: Планирование следующего daily timer"""
        if daily_key not in self.active_daily_configs:
            print(f"[SIMPLE-DAILY] Config not found for {daily_key}")
            return

        config = self.active_daily_configs[daily_key]
        command = config['command']
        callback = config['callback']
        context = config['context']

        hour = command['hour']
        minute = command['minute']
        until_date = command['until_date']
        on_complete_node = command.get('on_complete_node')

        bot = context.get('bot')
        chat_id = context.get('chat_id')
        session_id = context.get('session_id')

        # Рассчитываем следующее время daily
        now = datetime.now()
        today = now.replace(hour=hour, minute=minute, second=0, microsecond=0)

        # Если время сегодня еще не прошло - используем сегодня, иначе завтра
        next_daily = today if now < today else today + timedelta(days=1)

        # ПРОСТАЯ проверка cutoff
        if next_daily.date() > until_date:
            print(f"[SIMPLE-DAILY] Next daily {next_daily.date()} > cutoff {until_date}, not scheduling")
            return

        delay_seconds = (next_daily - now).total_seconds()
        print(f"[SIMPLE-DAILY] Next daily: {next_daily} (in {delay_seconds/60:.1f}m)")

        def simple_daily_callback():
            """ПРОСТАЯ daily логика - БЕЗ СЛОЖНОСТЕЙ!"""
            current_date = datetime.now().date()
            print(f"[SIMPLE-DAILY] Timer fired! Current: {current_date}, cutoff: {until_date}")

            # Обновляем статистику
            if daily_key in self.daily_participation_stats:
                stats = self.daily_participation_stats[daily_key]
                stats['total_days'] += 1
                print(f"[SIMPLE-DAILY] Stats updated: {stats['participated_days']}/{stats['total_days']}")

            if current_date > until_date:
                # ПЕРИОД ЗАКОНЧЕН - переход к итогам
                print(f"[SIMPLE-DAILY] Period ended, transitioning to final questions")

                # Показать статистику
                if daily_key in self.daily_participation_stats:
                    stats = self.daily_participation_stats[daily_key]
                    stats_msg = f"🎉 Исследовательский период завершен!\n\n📊 Ваше участие: {stats['participated_days']} из {stats['total_days']} дней\n\nПереходим к итоговым вопросам..."
                    bot.send_message(chat_id, stats_msg)
                    time.sleep(2)

                # CRUD подход - завершаем сессию
                try:
                    from app.modules.database import crud
                    db = SessionLocal()
                    crud.end_session(db, session_id)
                    db.close()
                    print(f"[SIMPLE-DAILY] Session ended via crud")
                except Exception as e:
                    print(f"[SIMPLE-DAILY] CRUD end_session failed: {e}")

                # Очищаем локальные данные
                try:
                    from app.modules.telegram_handler import user_sessions
                    if chat_id in user_sessions:
                        del user_sessions[chat_id]
                        print(f"[SIMPLE-DAILY] Cleared user_sessions")
                except Exception as e:
                    print(f"[SIMPLE-DAILY] Failed to clear user_sessions: {e}")

                # Прямой переход к итогам
                if on_complete_node:
                    try:
                        from app.modules.telegram_handler import send_node_message
                        send_node_message(chat_id, on_complete_node)
                        print(f"[SIMPLE-DAILY] SUCCESS: Transitioned to {on_complete_node}")
                    except Exception as e:
                        print(f"[SIMPLE-DAILY] Transition failed: {e}")
                        bot.send_message(chat_id, f"🔄 Для итоговых вопросов: /start и выберите '{on_complete_node}'")

                # Очистка конфигурации
                self.active_daily_configs.pop(daily_key, None)

            else:
                # ОБЫЧНЫЙ ДЕНЬ - отправляем question1
                print(f"[SIMPLE-DAILY] Regular day, sending question1")

                try:
                    from app.modules.telegram_handler import send_node_message
                    send_node_message(chat_id, 'question1')  # НАЧАЛО ДНЕВНОГО ЦИКЛА
                    print(f"[SIMPLE-DAILY] SUCCESS: Sent question1")

                    # Отмечаем участие (пользователь получил вопросы)
                    if daily_key in self.daily_participation_stats:
                        self.daily_participation_stats[daily_key]['participated_days'] += 1

                    # Планируем следующий daily
                    self._schedule_next_daily(daily_key)

                except Exception as e:
                    print(f"[SIMPLE-DAILY] Failed to send question1: {e}")

        # Создаем timer
        try:
            timer = threading.Timer(delay_seconds, simple_daily_callback)
            timer.daemon = True
            timer.name = f"SimpleDaily-{daily_key}-{int(time.time())}"
            timer.start()

            # Очищаем старый timer если есть
            old_timer = self.active_timers.get(daily_key)
            if old_timer:
                old_timer.cancel()

            self.active_timers[daily_key] = timer
            print(f"[SIMPLE-DAILY] Timer scheduled: {timer.name}")

        except Exception as e:
            print(f"[SIMPLE-DAILY] Timer creation failed: {e}")

    # ============================================================================
    # ВСЕ ОСТАЛЬНЫЕ МЕТОДЫ ИЗ СТАБИЛЬНОГО timing_engine.py БЕЗ ИЗМЕНЕНИЙ
    # ============================================================================

    def _parse_basic_pause(self, cmd_str: str) -> Dict[str, Any]:
        """Парсинг простых пауз"""
        match = re.match(r'^\d+(\.\d+)?(s)?$', cmd_str)
        if match:
            duration = float(cmd_str.replace('s', ''))
            return {'type': 'pause', 'duration': duration, 'process_name': 'Пауза', 'original': cmd_str}
        return None

    def _parse_typing(self, cmd_str: str) -> Dict[str, Any]:
        """Парсинг typing команд с preset'ами"""
        pattern = r'^typing:(\d+(?:\.\d+)?)s?(?::([^:]+))?(?::([^:]+))?$'
        match = re.match(pattern, cmd_str)

        if match:
            duration = float(match.group(1))
            process_name = match.group(2) if match.group(2) else "Обработка"
            preset = match.group(3) if match.group(3) else 'clean'
            preset_config = self.presets.get(preset, self.presets['clean'])

            return {
                'type': 'typing',
                'duration': duration,
                'process_name': process_name,
                'preset': preset,
                'exposure_time': preset_config['exposure_time'],
                'anti_flicker_delay': preset_config['anti_flicker_delay'],
                'action': preset_config['action'],
                'show_progress': True,
                'original': cmd_str
            }
        return None

    def _parse_process(self, cmd_str: str) -> Dict[str, Any]:
        """Парсинг process команд (замена state: true)"""
        pattern = r'^process:(\d+(?:\.\d+)?)s?:([^:]+)(?::([^:]+))?$'
        match = re.match(pattern, cmd_str)

        if match:
            duration = float(match.group(1))
            process_name = match.group(2)
            preset = match.group(3) if match.group(3) else 'clean'
            preset_config = self.presets.get(preset, self.presets['clean'])

            return {
                'type': 'process',
                'duration': duration,
                'process_name': process_name,
                'preset': preset,
                'exposure_time': preset_config['exposure_time'],
                'anti_flicker_delay': preset_config['anti_flicker_delay'],
                'action': preset_config['action'],
                'show_progress': False,
                'original': cmd_str
            }
        return None

    def _parse_timeout(self, cmd_str: str) -> Dict[str, Any]:
        """Парсинг timeout команды"""
        known_presets = set(self.presets.keys())

        pattern_with_arg = r'^timeout:(\d+(?:\.\d+)?)s:([^:]+)$'
        match_with_arg = re.match(pattern_with_arg, cmd_str)

        if match_with_arg:
            duration = float(match_with_arg.group(1))
            arg = match_with_arg.group(2).strip()

            if arg in known_presets:
                return {
                    'type': 'timeout',
                    'duration': duration,
                    'target_node': None,
                    'use_next_node_id': True,
                    'preset': arg,
                    'show_countdown': True,
                    'original': cmd_str
                }
            else:
                return {
                    'type': 'timeout',
                    'duration': duration,
                    'target_node': arg,
                    'use_next_node_id': False,
                    'preset': 'clean',
                    'show_countdown': True,
                    'original': cmd_str
                }

        pattern_simple = r'^timeout:(\d+(?:\.\d+)?)s$'
        match_simple = re.match(pattern_simple, cmd_str)

        if match_simple:
            duration = float(match_simple.group(1))
            return {
                'type': 'timeout',
                'duration': duration,
                'target_node': None,
                'use_next_node_id': True,
                'preset': 'clean',
                'show_countdown': True,
                'original': cmd_str
            }

        return None

    # ЗАГОТОВКИ для будущих функций
    def _parse_remind(self, cmd_str: str) -> Dict[str, Any]:
        """ЗАГОТОВКА: remind команды"""
        print(f"[TIMING-ENGINE] Remind stub: {cmd_str}")
        return None

    def _parse_deadline(self, cmd_str: str) -> Dict[str, Any]:
        """ЗАГОТОВКА: deadline команды"""
        print(f"[TIMING-ENGINE] Deadline stub: {cmd_str}")
        return None

    # ============================================================================
    # ИСПОЛНИТЕЛИ
    # ============================================================================

    def _execute_pause(self, command: Dict[str, Any], callback: Callable, **context) -> None:
        """Исполнитель простых пауз"""
        duration = command['duration']
        pause_text = context.get('pause_text') or ''
        bot = context.get('bot')
        chat_id = context.get('chat_id')

        if pause_text and bot and chat_id:
            bot.send_message(chat_id, pause_text)

        threading.Timer(duration, callback).start()

    def _execute_typing(self, command: Dict[str, Any], callback: Callable, **context) -> None:
        """Выполнение typing с preset'ами"""
        duration = command['duration']
        process_name = command.get('process_name', 'Обработка')
        preset = command.get('preset', 'clean')
        exposure_time = command.get('exposure_time', 1.5)
        anti_flicker_delay = command.get('anti_flicker_delay', 1.0)
        action = command.get('action', 'delete')

        session_id = context.get('session_id')
        if session_id:
            self.save_timer_to_db(
                session_id=session_id, timer_type='typing',
                delay_seconds=int(duration), message_text=process_name,
                callback_data={'command': command, 'preset': preset}
            )

        bot = context.get('bot')
        chat_id = context.get('chat_id')

        if bot and chat_id:
            def show_progress_with_presets():
                try:
                    self._show_progress_bar_with_presets(
                        bot, chat_id, duration, process_name,
                        show_progress=True, exposure_time=exposure_time,
                        anti_flicker_delay=anti_flicker_delay, action=action
                    )
                    callback()
                except Exception as e:
                    callback()

            threading.Thread(target=show_progress_with_presets).start()
        else:
            threading.Timer(duration, callback).start()

    def _execute_process(self, command: Dict[str, Any], callback: Callable, **context) -> None:
        """Выполнение статических процессов"""
        duration = command['duration']
        process_name = command.get('process_name', 'Процесс')
        preset = command.get('preset', 'clean')
        exposure_time = command.get('exposure_time', 1.5)
        anti_flicker_delay = command.get('anti_flicker_delay', 1.0)
        action = command.get('action', 'delete')

        session_id = context.get('session_id')
        if session_id:
            self.save_timer_to_db(
                session_id=session_id, timer_type='process',
                delay_seconds=int(duration), message_text=process_name,
                callback_data={'command': command, 'preset': preset}
            )

        bot = context.get('bot')
        chat_id = context.get('chat_id')

        if bot and chat_id:
            def show_static_process():
                try:
                    self._show_progress_bar_with_presets(
                        bot, chat_id, duration, process_name,
                        show_progress=False, exposure_time=exposure_time,
                        anti_flicker_delay=anti_flicker_delay, action=action
                    )
                    callback()
                except Exception as e:
                    callback()

            threading.Thread(target=show_static_process).start()
        else:
            threading.Timer(duration, callback).start()

    def _execute_timeout(self, command: Dict[str, Any], callback: Callable, **context) -> None:
        """Timeout с Silent Mode"""
        duration = int(command['duration'])
        use_next_node_id = command.get('use_next_node_id', False)
        explicit_target = command.get('target_node')
        preset = command.get('preset', 'clean')
        preset_config = self.presets.get(preset, self.presets['clean'])

        if use_next_node_id:
            target_node = context.get('next_node_id')
            if not target_node:
                callback()
                return
        else:
            target_node = explicit_target

        session_id = context.get('session_id')
        bot = context.get('bot')
        chat_id = context.get('chat_id')
        question_message_id = context.get('question_message_id')

        node_id = context.get('node_id', '')
        node_text = context.get('node_text', '')

        show_countdown = self.should_show_countdown(context)

        context['timeout_target_node'] = target_node
        if hasattr(callback, 'context'):
            callback.context.update(context)

        if session_id:
            self.save_timer_to_db(
                session_id=session_id, timer_type='timeout',
                delay_seconds=duration,
                message_text=f"Timeout {duration}s ({'interactive' if show_countdown else 'silent'})",
                callback_node_id=target_node,
                callback_data={
                    'command': command, 'target_node': target_node, 'preset': preset,
                    'silent_mode': not show_countdown
                }
            )

        self.debug_timers[session_id] = {
            'type': 'timeout',
            'duration': duration,
            'target_node': target_node,
            'preset': preset,
            'started_at': time.time(),
            'chat_id': chat_id,
            'question_message_id': question_message_id,
            'silent_mode': not show_countdown
        }

        if not bot or not chat_id:
            threading.Timer(duration, lambda: self._execute_timeout_callback(
                session_id, target_node, preset_config, callback, bot, chat_id, question_message_id
            )).start()
            return

        # ИНТЕРАКТИВНЫЙ TIMEOUT (с countdown)
        if show_countdown:
            print(f"[TIMING-ENGINE] INTERACTIVE timeout: {duration}s with countdown")

            message_type = self.get_countdown_message_type(duration, node_id, node_text)
            template = self.countdown_templates[message_type]

            initial_time_text = self.format_countdown_time(duration)
            countdown_msg = bot.send_message(
                chat_id,
                template['countdown'].format(time=initial_time_text)
            )

            def countdown_timer():
                """Живой обратный отсчет"""
                for remaining in range(duration-1, 0, -1):
                    time.sleep(1)

                    if session_id in self.cancelled_tasks:
                        try:
                            bot.edit_message_text(
                                chat_id=chat_id,
                                message_id=countdown_msg.message_id,
                                text="✅ Выбор сделан, автопереход отменен"
                            )
                            time.sleep(1.5)
                            bot.delete_message(chat_id, countdown_msg.message_id)
                        except Exception:
                            pass
                        self.cancelled_tasks.discard(session_id)
                        return

                    try:
                        time_text = self.format_countdown_time(remaining)
                        bot.edit_message_text(
                            chat_id=chat_id,
                            message_id=countdown_msg.message_id,
                            text=template['countdown'].format(time=time_text)
                        )
                    except Exception:
                        pass

                if session_id in self.cancelled_tasks:
                    self.cancelled_tasks.discard(session_id)
                    return

                # Убираем кнопки перед переходом
                if question_message_id:
                    try:
                        bot.edit_message_reply_markup(
                            chat_id=chat_id,
                            message_id=question_message_id,
                            reply_markup=None
                        )
                    except Exception:
                        pass

                try:
                    bot.edit_message_text(
                        chat_id=chat_id,
                        message_id=countdown_msg.message_id,
                        text=template['final']
                    )
                except Exception:
                    pass

                self._execute_timeout_callback(session_id, target_node, preset_config, callback, bot, chat_id, question_message_id)

                try:
                    time.sleep(1)
                    bot.delete_message(chat_id, countdown_msg.message_id)
                except Exception:
                    pass

            countdown_thread = threading.Thread(target=countdown_timer, daemon=True)
            countdown_thread.start()

            if session_id:
                self.active_timeouts[session_id] = countdown_thread

        # ТИХИЙ TIMEOUT (без countdown)
        else:
            print(f"[TIMING-ENGINE] SILENT timeout: {duration}s")

            pause_text = context.get('pause_text', '').strip()
            if pause_text:
                bot.send_message(chat_id, pause_text)

            def silent_timeout():
                time.sleep(duration)
                if session_id in self.cancelled_tasks:
                    self.cancelled_tasks.discard(session_id)
                    return

                self._execute_timeout_callback(session_id, target_node, preset_config, callback, bot, chat_id, question_message_id)

            timeout_thread = threading.Thread(target=silent_timeout, daemon=True)
            timeout_thread.start()

            if session_id:
                self.active_timeouts[session_id] = timeout_thread

    def _execute_timeout_callback(self, session_id: int, target_node: str, preset_config: dict,
                                  callback: Callable, bot=None, chat_id=None, question_message_id=None):
        """Callback с preset задержками"""
        if session_id in self.cancelled_tasks:
            self.cancelled_tasks.discard(session_id)
            return

        exposure_time = preset_config.get('exposure_time', 0)
        anti_flicker_delay = preset_config.get('anti_flicker_delay', 0)

        if exposure_time > 0:
            time.sleep(exposure_time)

        try:
            callback()
        except Exception as e:
            logger.error(f"Timeout callback error: {e}")

        if anti_flicker_delay > 0:
            time.sleep(anti_flicker_delay)

        # Очистка
        if session_id in self.debug_timers:
            del self.debug_timers[session_id]
        if session_id in self.active_timeouts:
            del self.active_timeouts[session_id]

    # ЗАГОТОВКИ исполнителей
    def _execute_remind(self, command: Dict[str, Any], callback: Callable, **context) -> None:
        """ЗАГОТОВКА: Исполнитель системы напоминаний"""
        print(f"[TIMING-ENGINE] Reminder system stub: {command.get('original', 'N/A')}")
        callback()

    def _execute_deadline(self, command: Dict[str, Any], callback: Callable, **context) -> None:
        """ЗАГОТОВКА: Исполнитель дедлайнов"""
        print(f"[TIMING-ENGINE] Deadline system stub: {command.get('original', 'N/A')}")
        callback()

    def _show_progress_bar_with_presets(self, bot, chat_id, duration, process_name,
                                        show_progress=True, exposure_time=1.5,
                                        anti_flicker_delay=1.0, action='delete'):
        """Показ процесса с полным контролем экспозиции"""
        try:
            if show_progress:
                # ПРОГРЕСС-БАР
                msg = bot.send_message(chat_id, f"🚀 {process_name}\n⬜⬜⬜⬜⬜ 0%")
                steps = 5
                step_duration = duration / steps

                for i in range(1, steps + 1):
                    time.sleep(step_duration)
                    progress = int((i / steps) * 100)
                    filled = "🟩" * i
                    empty = "⬜" * (steps - i)
                    try:
                        bot.edit_message_text(
                            chat_id=chat_id, message_id=msg.message_id,
                            text=f"🚀 {process_name}\n{filled}{empty} {progress}%"
                        )
                    except Exception:
                        pass

                try:
                    bot.edit_message_text(
                        chat_id=chat_id, message_id=msg.message_id,
                        text=f"✅ {process_name}\n🟩🟩🟩🟩🟩 100%"
                    )
                except Exception:
                    pass
            else:
                # СТАТИЧЕСКОЕ СООБЩЕНИЕ
                msg = bot.send_message(chat_id, f"⚙️ {process_name}...")
                time.sleep(duration)
                try:
                    bot.edit_message_text(
                        chat_id=chat_id, message_id=msg.message_id,
                        text=f"✅ {process_name}"
                    )
                except Exception:
                    pass

            # ЭКСПОЗИЦИЯ + УДАЛЕНИЕ + ANTI-FLICKER
            if exposure_time > 0:
                time.sleep(exposure_time)

            if action == 'delete':
                try:
                    bot.delete_message(chat_id=chat_id, message_id=msg.message_id)
                except Exception:
                    pass

            if anti_flicker_delay > 0:
                time.sleep(anti_flicker_delay)

        except Exception as e:
            logger.error(f"Process with presets failed: {e}")

    # ============================================================================
    # ОСНОВНАЯ ЛОГИКА DSL
    # ============================================================================

    def execute_timing(self, timing_config: str, callback: Callable, **context) -> None:
        """Главная функция выполнения timing команд"""
        if not self.enabled:
            callback()
            return

        try:
            commands = self._parse_timing_dsl(timing_config)
            self._execute_timing_commands(commands, callback, **context)
        except Exception as e:
            logger.error(f"TimingEngine error: {e}")
            callback()

    def _parse_timing_dsl(self, timing_config: str) -> List[Dict[str, Any]]:
        """Парсинг DSL команд"""
        if not timing_config or timing_config.strip() == "":
            return []

        command_strings = [cmd.strip() for cmd in timing_config.split(';') if cmd.strip()]
        commands = []

        for cmd_str in command_strings:
            parsed = None

            # Простые числа
            if re.match(r'^\d+(\.\d+)?(s)?$', cmd_str):
                parsed = self.parsers['basic_pause'](cmd_str)
            # process команды
            elif cmd_str.startswith('process:'):
                parsed = self.parsers['process'](cmd_str)
            # timeout команды
            elif cmd_str.startswith('timeout:'):
                parsed = self.parsers['timeout'](cmd_str)
            # typing команды
            elif cmd_str.startswith('typing:'):
                parsed = self.parsers['typing'](cmd_str)
            # НОВОЕ: daily команды
            elif cmd_str.startswith('daily@'):
                parsed = self.parsers['daily'](cmd_str)
            # ЗАГОТОВКИ
            elif cmd_str.startswith('remind:'):
                parsed = self.parsers['remind'](cmd_str)
            elif cmd_str.startswith('deadline:'):
                parsed = self.parsers['deadline'](cmd_str)

            if parsed:
                commands.append(parsed)
            else:
                logger.warning(f"Unknown timing command: {cmd_str}")

        return commands

    def _execute_timing_commands(self, commands: List[Dict[str, Any]],
                                callback: Callable, **context) -> None:
        """Выполнение списка команд"""
        if not commands:
            callback()
            return

        for command in commands:
            cmd_type = command.get('type')
            if cmd_type in self.executors:
                try:
                    self.executors[cmd_type](command, callback, **context)
                except Exception as e:
                    logger.error(f"Error executing {cmd_type}: {e}")
            else:
                logger.warning(f"No executor for command type: {cmd_type}")

    def process_timing(self, user_id: int, session_id: int, node_id: str,
                      timing_config: str, callback: Callable, **context) -> None:
        """ГЛАВНАЯ ФУНКЦИЯ: Обработка timing команд"""
        if not self.enabled:
            callback()
            return

        try:
            enriched_context = dict(context)
            enriched_context['session_id'] = session_id
            enriched_context['node_id'] = node_id
            self.execute_timing(timing_config, callback, **enriched_context)
        except Exception as e:
            logger.error(f"process_timing error: {e}")
            callback()

    # ============================================================================
    # УПРАВЛЕНИЕ TIMEOUT - СТАБИЛЬНЫЕ МЕТОДЫ
    # ============================================================================

    def cancel_timeout_task(self, session_id: int) -> bool:
        """Отменить активный timeout для сессии"""
        self.cancelled_tasks.add(session_id)
        timer_key = f"timeout_{session_id}"

        if timer_key in self.active_timers:
            timer = self.active_timers[timer_key]
            timer.cancel()
            del self.active_timers[timer_key]

        if session_id in self.debug_timers:
            del self.debug_timers[session_id]
        if session_id in self.active_timeouts:
            del self.active_timeouts[session_id]

        return True

    def cleanup_timeout_tasks(self):
        """Очистка завершенных timeout задач"""
        completed = [sid for sid, thread in self.active_timeouts.items() if not thread.is_alive()]
        for session_id in completed:
            del self.active_timeouts[session_id]
            self.cancelled_tasks.discard(session_id)

    def cancel_user_timers(self, user_id: int) -> None:
        """Отменить все таймеры пользователя"""
        to_cancel = [key for key in self.active_timers.keys() if key.startswith(f"{user_id}_")]
        for key in to_cancel:
            timer = self.active_timers.pop(key)
            timer.cancel()

    # ============================================================================
    # БД ОПЕРАЦИИ - СТАБИЛЬНЫЕ МЕТОДЫ  
    # ============================================================================

    def _get_db_session(self):
        """Получить сессию БД"""
        try:
            return SessionLocal()
        except Exception as e:
            logger.error(f"Failed to create DB session: {e}")
            return None

    def save_timer_to_db(self, session_id: int, timer_type: str,
                        delay_seconds: int, message_text: str = "",
                        callback_node_id: str = "", callback_data: dict = None):
        """Сохранить таймер в БД"""
        if callback_data is None:
            callback_data = {}

        db = self._get_db_session()
        if not db:
            return None

        try:
            target_time = utc_now() + timedelta(seconds=delay_seconds)
            timer_record = ActiveTimer(
                session_id=session_id,
                timer_type=timer_type,
                target_timestamp=target_time,
                message_text=message_text,
                callback_node_id=callback_node_id,
                callback_data=callback_data,
                status='pending'
            )

            db.add(timer_record)
            db.commit()
            return timer_record.id

        except Exception as e:
            logger.error(f"Failed to save timer to DB: {e}")
            db.rollback()
            return None
        finally:
            db.close()

    def restore_timers_from_db(self):
        """Восстановить таймеры из БД"""
        db = self._get_db_session()
        if not db:
            return

        try:
            pending_timers = db.query(ActiveTimer).filter(
                ActiveTimer.status == 'pending',
                ActiveTimer.target_timestamp > utc_now()
            ).all()

            for timer_record in pending_timers:
                remaining = (timer_record.target_timestamp - utc_now()).total_seconds()
                if remaining > 0:
                    timer_key = f"db_{timer_record.id}"
                    def create_callback(tid=timer_record.id):
                        return lambda: self._execute_db_timer(tid)
                    thread_timer = threading.Timer(remaining, create_callback())
                    thread_timer.start()
                    self.active_timers[timer_key] = thread_timer

        except Exception as e:
            logger.error(f"Failed to restore timers: {e}")
        finally:
            db.close()

    def _execute_db_timer(self, timer_id: int):
        """Выполнить таймер из БД"""
        db = self._get_db_session()
        if not db:
            return

        try:
            timer_record = db.query(ActiveTimer).filter(ActiveTimer.id == timer_id).first()
            if not timer_record:
                return

            timer_record.status = 'executed'
            db.commit()

            timer_key = f"db_{timer_id}"
            if timer_key in self.active_timers:
                del self.active_timers[timer_key]

        except Exception as e:
            logger.error(f"Failed to execute DB timer {timer_id}: {e}")
            db.rollback()
        finally:
            db.close()

    def cleanup_expired_timers(self):
        """Очистить просроченные таймеры в БД"""
        db = self._get_db_session()
        if not db:
            return

        try:
            from sqlalchemy import and_
            expired_count = db.query(ActiveTimer).filter(
                and_(ActiveTimer.status == 'pending', ActiveTimer.target_timestamp < utc_now())
            ).update({'status': 'expired'})
            db.commit()

        except Exception as e:
            logger.error(f"Failed to cleanup expired timers: {e}")
            db.rollback()
        finally:
            db.close()

    # ============================================================================
    # СТАТУС И УПРАВЛЕНИЕ
    # ============================================================================

    def get_status(self) -> Dict[str, Any]:
        """Статус timing системы"""
        return {
            'stage': 'STABLE + SIMPLE DAILY',
            'enabled': self.enabled,
            'active_timers': len(self.active_timers),
            'active_timeouts': len(self.active_timeouts),
            'cancelled_tasks': len(self.cancelled_tasks),
            'debug_timers': len(self.debug_timers),
            'active_daily_configs': len(self.active_daily_configs),
            'daily_stats': len(self.daily_participation_stats),
            'available_parsers': list(self.parsers.keys()),
            'available_executors': list(self.executors.keys()),
            'available_presets': list(self.presets.keys()),
            'countdown_message_types': list(self.countdown_templates.keys())
        }

    def enable(self) -> None:
        """Включить timing систему"""
        self.enabled = True

    def disable(self) -> None:
        """Выключить timing систему"""
        self.enabled = False

        for timer in self.active_timers.values():
            timer.cancel()

        self.active_timers.clear()
        self.cancelled_tasks.clear()
        self.active_timeouts.clear()
        self.debug_timers.clear()
        self.active_daily_configs.clear()
        self.daily_participation_stats.clear()


# ============================================================================
# ГЛОБАЛЬНЫЙ ЭКЗЕМПЛЯР И ПУБЛИЧНЫЕ ФУНКЦИИ
# ============================================================================

timing_engine = TimingEngine()

def process_node_timing(user_id: int, session_id: int, node_id: str,
                       timing_config: str, callback: Callable, **context) -> None:
    """Основная функция для обработки timing команд узла"""
    return timing_engine.process_timing(user_id, session_id, node_id, timing_config, callback, **context)

def cancel_timeout_for_session(session_id: int) -> bool:
    """Публичная функция для отмены timeout"""
    return timing_engine.cancel_timeout_task(session_id)

def enable_timing() -> None:
    """Включить timing систему глобально"""
    global TIMING_ENABLED
    TIMING_ENABLED = True
    timing_engine.enable()

def disable_timing() -> None:
    """Выключить timing систему глобально"""
    global TIMING_ENABLED
    TIMING_ENABLED = False
    timing_engine.disable()

def get_timing_status() -> Dict[str, Any]:
    """Получить статус timing системы"""
    return timing_engine.get_status()

def cleanup_completed_timeouts() -> None:
    """Очистить завершенные timeout задачи"""
    timing_engine.cleanup_timeout_tasks()

def cancel_user_timers(user_id: int) -> None:
    """Отменить все таймеры для конкретного пользователя"""
    timing_engine.cancel_user_timers(user_id)

def get_timing_engine_instance() -> TimingEngine:
    """Получить экземпляр timing engine"""
    return timing_engine