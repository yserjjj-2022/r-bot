# -*- coding: utf-8 -*-
"""
R-Bot Timing Engine - система временных механик с адаптивными countdown сообщениями и Silent Mode

ОБНОВЛЕНИЯ:
06.10.2025 - ДОБАВЛЕНЫ адаптивные countdown сообщения (без технических узлов)
06.10.2025 - Умное форматирование времени (только ненулевые разряды) 
06.10.2025 - Контекстный выбор шаблонов сообщений
06.10.2025 - Удаление кнопок при timeout
06.10.2025 - ДОБАВЛЕН Silent Mode для сценарных timeout'ов
06.10.2025 - ВОССТАНОВЛЕНЫ заглушки для daily/remind/deadline (для будущих спринтов)

DSL команды:
- timeout:15s:no_answer - интерактивный timeout с countdown (если есть кнопки)
- timeout:5s:slow - тихий timeout для драматургии (если есть pause_text)  
- typing:5s:Анализ поведения:clean - прогресс-бар 5s с preset clean
- daily@09:00MSK - ежедневные уведомления (заготовка)
- remind:5m,1h,1d - система напоминаний (заготовка)  
- deadline:2h - дедлайны с предупреждениями (заготовка)
"""

import threading
import time
import re
import logging
from datetime import timedelta
from typing import Dict, Any, Callable, Optional, List, Set

from app.modules.database.models import ActiveTimer, utc_now
from app.modules.database import SessionLocal

TIMING_ENABLED = True
logger = logging.getLogger(__name__)

class TimingEngine:
    """
    Timing Engine с адаптивными countdown сообщениями, Silent Mode 
    и готовой инфраструктурой для расширения функций
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

        self.initialized = True

        logger.info(f"TimingEngine initialized with Silent Mode. Enabled: {self.enabled}")
        print(f"[TIMING-ENGINE] TimingEngine initialized with enabled={self.enabled}")
        print(f"[TIMING-ENGINE] Available presets: {list(self.presets.keys())}")
        print(f"[TIMING-ENGINE] Available commands: {list(self.parsers.keys())}")
        print(f"[TIMING-ENGINE] Adaptive message types: {list(self.countdown_templates.keys())}")
        print(f"[TIMING-ENGINE] Silent Mode activated for scenic timeouts")

        if self.enabled:
            try:
                self.restore_timers_from_db()
                self.cleanup_expired_timers()
            except Exception as e:
                logger.error(f"Failed to restore/cleanup timers on init: {e}")

    def _init_countdown_templates(self) -> Dict[str, Dict[str, str]]:
        """Инициализация адаптивных шаблонов countdown сообщений"""
        return {
            'urgent': {
                'countdown': "🚨 Внимание! Осталось: {time}",
                'final': "🚨 Время истекло!"
            },
            'choice': {
                'countdown': "⏳ Выбор нужно сделать через: {time}",
                'final': "⏰ Время выбора истекло"
            },
            'decision': {
                'countdown': "⏳ На принятие решения осталось: {time}",
                'final': "⏰ Время принятия решения истекло"
            },
            'answer': {
                'countdown': "⏳ Время на ответ: {time}",
                'final': "⏰ Время на ответ истекло"
            },
            'gentle': {
                'countdown': "💭 Время поделиться мыслями: {time}",
                'final': "💭 Время для размышлений истекло"
            },
            'generic': {
                'countdown': "⏰ Осталось времени: {time}",
                'final': "⏰ Время истекло"
            }
        }

    def format_countdown_time(self, seconds: int) -> str:
        """Форматирует время для countdown в человекочитаемый вид"""
        if seconds <= 0:
            return "время истекло"

        hours = seconds // 3600
        minutes = (seconds % 3600) // 60
        secs = seconds % 60

        parts = []
        if hours > 0:
            form = "час" if hours == 1 else ("часа" if 2 <= hours <= 4 else "часов")
            parts.append(f"{hours} {form}")
        if minutes > 0:
            form = "минуту" if minutes == 1 else ("минуты" if 2 <= minutes <= 4 else "минут")
            parts.append(f"{minutes} {form}")
        if secs > 0 or not parts:
            form = "секунду" if secs == 1 else ("секунды" if 2 <= secs <= 4 else "секунд")
            parts.append(f"{secs} {form}")

        return " ".join(parts)

    def get_countdown_message_type(self, duration: int, node_id: str = "", node_text: str = "") -> str:
        """Адаптивный выбор типа сообщения по контексту"""

        # Правило 1: По длительности (базовая логика)
        if duration <= 5:
            base_type = "urgent"
        elif duration <= 15:
            base_type = "choice"
        elif duration <= 60:
            base_type = "decision"
        else:
            base_type = "gentle"

        # Правило 2: Переопределение по node_id
        if node_id:
            node_lower = node_id.lower()
            if any(keyword in node_lower for keyword in ['test', 'quiz', 'question', 'answer']):
                return "answer"
            elif any(keyword in node_lower for keyword in ['timing', 'speed', 'reaction']):
                return "choice"

        # Правило 3: По содержанию текста
        if node_text:
            text_lower = node_text.lower()
            if any(word in text_lower for word in ['настроение', 'чувство', 'ощущение']):
                return "gentle"
            elif any(word in text_lower for word in ['быстро', 'срочно', 'скорее']):
                return "urgent"
            elif any(word in text_lower for word in ['тест', 'вопрос', 'ответ']):
                return "answer"

        return base_type

    def should_show_countdown(self, context: dict) -> bool:
        """
        НОВОЕ: Определяет, нужно ли показывать countdown сообщения

        ЛОГИКА:
        - Есть pause_text → ТИХИЙ timeout (сценарная пауза) 
        - Есть кнопки И нет pause_text → ИНТЕРАКТИВНЫЙ timeout (countdown)
        - НЕТ кнопок И НЕТ pause_text → ТИХИЙ timeout
        """
        pause_text = context.get('pause_text', '').strip()
        has_pause_text = bool(pause_text)

        has_buttons = len(context.get('buttons', [])) > 0

        print(f"[TIMING-ENGINE] Silent mode check:")
        print(f"  - pause_text: '{pause_text[:30]}{'...' if len(pause_text) > 30 else ''}'")
        print(f"  - has_buttons: {has_buttons}")

        # Показывать countdown только для интерактивных timeout'ов
        show_countdown = has_buttons and not has_pause_text
        mode = "INTERACTIVE" if show_countdown else "SILENT"
        print(f"[TIMING-ENGINE] Timeout mode: {mode}")

        return show_countdown

    def _init_presets(self) -> Dict[str, Dict[str, Any]]:
        """Инициализация preset'ов для контроля экспозиции и anti-flicker"""
        return {
            'clean': {
                'exposure_time': 1.5,
                'anti_flicker_delay': 1.0,
                'action': 'delete',
                'description': 'Стандарт: показать результат 1.5с, пауза 1с, удалить'
            },
            'keep': {
                'exposure_time': 0,
                'anti_flicker_delay': 0.5,
                'action': 'keep',
                'description': 'Оставить в ленте навсегда'
            },
            'fast': {
                'exposure_time': 0.8,
                'anti_flicker_delay': 0.5,
                'action': 'delete',
                'description': 'Быстро: показать 0.8с, пауза 0.5с, удалить'
            },
            'slow': {
                'exposure_time': 3.0,
                'anti_flicker_delay': 2.0,
                'action': 'delete',
                'description': 'Медленно: показать 3с, пауза 2с, удалить'
            },
            'instant': {
                'exposure_time': 0,
                'anti_flicker_delay': 0,
                'action': 'delete',
                'description': 'Мгновенно: сразу удалить'
            }
        }

    @classmethod
    def get_instance(cls):
        return cls()

    # === DB helpers ===
    def _get_db_session(self):
        try:
            return SessionLocal()
        except Exception as e:
            logger.error(f"Failed to create DB session: {e}")
            return None

    def save_timer_to_db(self, session_id: int, timer_type: str, 
                         delay_seconds: int, message_text: str = "",
                         callback_node_id: str = "", callback_data: dict = None):
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

    # === Парсеры и исполнители ===
    def _init_parsers(self) -> Dict[str, Any]:
        """Инициализация парсеров DSL команд"""
        return {
            'basic_pause': self._parse_basic_pause,
            'typing': self._parse_typing,
            'process': self._parse_process,
            'timeout': self._parse_timeout,  # УНИВЕРСАЛЬНАЯ timeout команда
            'daily': self._parse_daily,      # ЗАГОТОВКА: ежедневные уведомления
            'remind': self._parse_remind,    # ЗАГОТОВКА: система напоминаний
            'deadline': self._parse_deadline # ЗАГОТОВКА: дедлайны
        }

    def _init_executors(self) -> Dict[str, Any]:
        """Инициализация исполнителей команд"""
        return {
            'pause': self._execute_pause,
            'typing': self._execute_typing,
            'process': self._execute_process,
            'timeout': self._execute_timeout,  # УНИВЕРСАЛЬНЫЙ timeout исполнитель
            'daily': self._execute_daily,      # ЗАГОТОВКА: исполнитель daily
            'remind': self._execute_remind,    # ЗАГОТОВКА: исполнитель remind
            'deadline': self._execute_deadline # ЗАГОТОВКА: исполнитель deadline
        }

    def execute_timing(self, timing_config: str, callback: Callable, **context) -> None:
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
        if not timing_config or timing_config.strip() == "":
            return []

        command_strings = [cmd.strip() for cmd in timing_config.split(';') if cmd.strip()]
        commands = []

        for cmd_str in command_strings:
            parsed = None

            # Обратная совместимость: простые числа
            if re.match(r'^\d+(\.\d+)?(s)?$', cmd_str):
                parsed = self.parsers['basic_pause'](cmd_str)
            # process команды
            elif cmd_str.startswith('process:'):
                parsed = self.parsers['process'](cmd_str)
            # УНИВЕРСАЛЬНАЯ timeout команда  
            elif cmd_str.startswith('timeout:'):
                parsed = self.parsers['timeout'](cmd_str)
            # typing команды с preset'ами
            elif cmd_str.startswith('typing:'):
                parsed = self.parsers['typing'](cmd_str)
            # ЗАГОТОВКИ для будущих функций
            elif cmd_str.startswith('daily@'):
                parsed = self.parsers['daily'](cmd_str)
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

    # === DSL парсеры ===
    def _parse_basic_pause(self, cmd_str: str) -> Dict[str, Any]:
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
        """Парсинг timeout команды с различением preset'ов и узлов назначения"""
        known_presets = set(self.presets.keys())

        # Форматы timeout команд
        pattern_with_arg = r'^timeout:(\d+(?:\.\d+)?)s:([^:]+)$'
        pattern_simple = r'^timeout:(\d+(?:\.\d+)?)s$'

        # timeout:15s:xxx
        match_with_arg = re.match(pattern_with_arg, cmd_str)
        if match_with_arg:
            duration = float(match_with_arg.group(1))
            arg = match_with_arg.group(2).strip()

            if arg in known_presets:
                # Preset - используем next_node_id
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
                # Узел - явный переход
                return {
                    'type': 'timeout',
                    'duration': duration,
                    'target_node': arg,
                    'use_next_node_id': False,
                    'preset': 'clean',
                    'show_countdown': True,
                    'original': cmd_str
                }

        # timeout:30s
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

    # ЗАГОТОВКИ парсеров для будущих функций
    def _parse_daily(self, cmd_str: str) -> Dict[str, Any]:
        """ЗАГОТОВКА: Парсинг daily команд - daily@09:00MSK"""
        match = re.match(r'^daily@(\d{2}):(\d{2})([A-Z]{3})?$', cmd_str)
        if match:
            return {
                'type': 'daily', 
                'hour': int(match.group(1)), 
                'minute': int(match.group(2)), 
                'timezone': match.group(3) or 'UTC', 
                'original': cmd_str
            }
        return None

    def _parse_remind(self, cmd_str: str) -> Dict[str, Any]:
        """ЗАГОТОВКА: Парсинг remind команд - remind:5m,1h,1d"""
        match = re.match(r'^remind:(.+)$', cmd_str)
        if match:
            intervals = []
            for interval in match.group(1).split(','):
                interval_str = interval.strip()
                time_match = re.match(r'^(\d+)(h|m|s)$', interval_str)
                if time_match:
                    value = int(time_match.group(1))
                    unit = time_match.group(2)
                    seconds = value if unit == 's' else value*60 if unit == 'm' else value*3600
                    intervals.append(seconds)
            return {'type': 'remind', 'intervals': intervals, 'original': cmd_str}
        return None

    def _parse_deadline(self, cmd_str: str) -> Dict[str, Any]:
        """ЗАГОТОВКА: Парсинг deadline команд - deadline:2h"""
        match = re.match(r'^deadline:(\d+)(h|d|m)$', cmd_str)
        if match:
            value = int(match.group(1))
            unit = match.group(2)
            seconds = value*3600 if unit == 'h' else value*86400 if unit == 'd' else value*60
            return {'type': 'deadline', 'duration': seconds, 'original': cmd_str}
        return None

    # === Исполнители ===
    def _execute_pause(self, command: Dict[str, Any], callback: Callable, **context) -> None:
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
        """Выполнение статических процессов (замена state: true)"""
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
        """ОБНОВЛЕНО: Timeout с Silent Mode для сценарных пауз"""

        duration = int(command['duration'])
        use_next_node_id = command.get('use_next_node_id', False)
        explicit_target = command.get('target_node')
        preset = command.get('preset', 'clean')

        preset_config = self.presets.get(preset, self.presets['clean'])

        # Определяем целевой узел
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

        # Получаем контекст для адаптивных сообщений
        node_id = context.get('node_id', '')
        node_text = context.get('node_text', '')

        # НОВОЕ: Проверяем режим timeout
        show_countdown = self.should_show_countdown(context)

        context['timeout_target_node'] = target_node
        if hasattr(callback, 'context'):
            callback.context.update(context)

        # Сохранить в БД с отметкой режима
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

        # Сохранить для отладки
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

        # === РЕЖИМ 1: ИНТЕРАКТИВНЫЙ TIMEOUT (с countdown) ===
        if show_countdown:
            print(f"[TIMING-ENGINE] INTERACTIVE timeout: {duration}s with countdown")

            message_type = self.get_countdown_message_type(duration, node_id, node_text)
            template = self.countdown_templates[message_type]

            # Адаптивное начальное сообщение
            initial_time_text = self.format_countdown_time(duration)
            countdown_msg = bot.send_message(
                chat_id, 
                template['countdown'].format(time=initial_time_text)
            )

            def countdown_timer():
                """Живой обратный отсчет с адаптивными сообщениями"""

                for remaining in range(duration-1, 0, -1):
                    time.sleep(1)

                    # Проверить отмену
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

                    # Обновить с адаптивным форматированием времени
                    try:
                        time_text = self.format_countdown_time(remaining)
                        bot.edit_message_text(
                            chat_id=chat_id, 
                            message_id=countdown_msg.message_id,
                            text=template['countdown'].format(time=time_text)
                        )
                    except Exception:
                        pass

                # Финальная проверка на отмену
                if session_id in self.cancelled_tasks:
                    self.cancelled_tasks.discard(session_id)
                    return

                # Убрать кнопки из исходного сообщения ПЕРЕД переходом
                if question_message_id:
                    try:
                        bot.edit_message_reply_markup(
                            chat_id=chat_id, 
                            message_id=question_message_id, 
                            reply_markup=None
                        )
                    except Exception:
                        pass

                # Показать адаптивное финальное сообщение
                try:
                    bot.edit_message_text(
                        chat_id=chat_id, 
                        message_id=countdown_msg.message_id, 
                        text=template['final']
                    )
                except Exception:
                    pass

                # Выполнить callback с preset задержками
                self._execute_timeout_callback(session_id, target_node, preset_config, callback, bot, chat_id, question_message_id)

                # Удалить служебные сообщения
                try:
                    time.sleep(1)
                    bot.delete_message(chat_id, countdown_msg.message_id)
                except Exception:
                    pass

            # Запустить поток обратного отсчета
            countdown_thread = threading.Thread(target=countdown_timer, daemon=True)
            countdown_thread.start()

            if session_id:
                self.active_timeouts[session_id] = countdown_thread

        # === РЕЖИМ 2: ТИХИЙ TIMEOUT (без countdown) ===
        else:
            print(f"[TIMING-ENGINE] SILENT timeout: {duration}s (scenic pause)")

            # Показать pause_text если есть
            pause_text = context.get('pause_text', '').strip()
            if pause_text:
                bot.send_message(chat_id, pause_text)
                print(f"[TIMING-ENGINE] Sent pause_text: '{pause_text[:50]}...'")

            def silent_timeout():
                """Тихий timeout без countdown сообщений"""
                time.sleep(duration)

                if session_id in self.cancelled_tasks:
                    self.cancelled_tasks.discard(session_id)
                    return

                print(f"[TIMING-ENGINE] Silent timeout completed: {duration}s")
                self._execute_timeout_callback(session_id, target_node, preset_config, callback, bot, chat_id, question_message_id)

            timeout_thread = threading.Thread(target=silent_timeout, daemon=True)
            timeout_thread.start()
            if session_id:
                self.active_timeouts[session_id] = timeout_thread

    def _execute_timeout_callback(self, session_id: int, target_node: str, preset_config: dict, 
                                 callback: Callable, bot=None, chat_id=None, question_message_id=None):
        """Выполнить callback с применением preset задержек"""

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

    # ЗАГОТОВКИ исполнителей для будущих функций  
    def _execute_daily(self, command: Dict[str, Any], callback: Callable, **context) -> None:
        """ЗАГОТОВКА: Исполнитель ежедневных уведомлений"""
        print(f"[TIMING-ENGINE] Daily scheduling stub: {command.get('original', 'N/A')}")
        callback()

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

    # === Управление timeout ===
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

    def get_status(self) -> Dict[str, Any]:
        """Статус timing системы"""
        return {
            'enabled': self.enabled,
            'active_timers': len(self.active_timers),
            'active_timeouts': len(self.active_timeouts),
            'cancelled_tasks': len(self.cancelled_tasks),
            'debug_timers': len(self.debug_timers),
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

# Глобальный экземпляр
timing_engine = TimingEngine()

# Публичные функции
def process_node_timing(user_id: int, session_id: int, node_id: str, 
                        timing_config: str, callback: Callable, **context) -> None:
    return timing_engine.process_timing(user_id, session_id, node_id, timing_config, callback, **context)

def cancel_timeout_for_session(session_id: int) -> bool:
    """Публичная функция для отмены timeout"""
    return timing_engine.cancel_timeout_task(session_id)

def enable_timing() -> None:
    global TIMING_ENABLED
    TIMING_ENABLED = True
    timing_engine.enable()

def disable_timing() -> None:
    global TIMING_ENABLED  
    TIMING_ENABLED = False
    timing_engine.disable()

def get_timing_status() -> Dict[str, Any]:
    return timing_engine.get_status()
