# -*- coding: utf-8 -*-
"""
R-Bot Timing Engine - система временных механик с preset'ами и контролем экспозиции

ОБНОВЛЕНИЯ:
05.10.2025 - ИСПРАВЛЕНА обработка timeout команд с preset'ами
05.10.2025 - Добавлено различение preset'ов от узлов назначения
05.10.2025 - Исправлено удаление кнопок при timeout
05.10.2025 - Добавлены диагностические логи

DSL команды:
- timeout:15s:no_answer - переход на узел no_answer через 15s
- timeout:5s:slow - переход на next_node_id через 5s с preset slow
- timeout:30s - переход на next_node_id через 30s с preset clean
"""

import threading
import time
import re
import logging
from datetime import timedelta
from typing import Dict, Any, Callable, Optional, List, Set

# Импорты моделей/БД
from app.modules.database.models import ActiveTimer, utc_now
from app.modules.database import SessionLocal

# Feature flag включен по умолчанию
TIMING_ENABLED = True

logger = logging.getLogger(__name__)

class TimingEngine:
    """
    Timing Engine с поддержкой preset'ов и универсальной timeout команды
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
        self.cancelled_tasks: Set[int] = set()         # Отмененные timeout задачи
        self.active_timeouts: Dict[int, threading.Thread] = {}  # Активные timeout потоки
        
        # ДОБАВЛЕНО: Простое хранение активных таймеров для отладки
        self.debug_timers: Dict[int, Dict] = {}  # session_id -> timer_info
        
        self.initialized = True

        logger.info(f"TimingEngine initialized with universal timeout command. Enabled: {self.enabled}")
        print(f"[TIMING-ENGINE] TimingEngine initialized with enabled={self.enabled}")
        print(f"[TIMING-ENGINE] Available presets: {list(self.presets.keys())}")
        print(f"[TIMING-ENGINE] Available commands: {list(self.parsers.keys())}")

        if self.enabled:
            try:
                self.restore_timers_from_db()
                self.cleanup_expired_timers()
            except Exception as e:
                logger.error(f"Failed to restore/cleanup timers on init: {e}")
                print(f"[TIMING-ENGINE] Failed to restore/cleanup timers on init: {e}")

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
                'description': 'Оставить в ленте навсегда, минимальная пауза 0.5с'
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
                'description': 'Мгновенно: сразу удалить без задержек (как раньше)'
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
            print(f"[TIMING-ENGINE] Timer saved to DB: ID={timer_record.id}, type={timer_type}")
            return timer_record.id
        except Exception as e:
            logger.error(f"Failed to save timer to DB: {e}")
            db.rollback()
            return None
        finally:
            db.close()

    def restore_timers_from_db(self):
        print("[TIMING-ENGINE] Restoring timers from database...")
        db = self._get_db_session()
        if not db:
            return
        try:
            pending_timers = db.query(ActiveTimer).filter(
                ActiveTimer.status == 'pending',
                ActiveTimer.target_timestamp > utc_now()
            ).all()
            print(f"[TIMING-ENGINE] Found {len(pending_timers)} pending timers to restore")
            
            for timer_record in pending_timers:
                remaining = (timer_record.target_timestamp - utc_now()).total_seconds()
                if remaining > 0:
                    timer_key = f"db_{timer_record.id}"
                    def create_callback(tid=timer_record.id):
                        return lambda: self._execute_db_timer(tid)
                    
                    thread_timer = threading.Timer(remaining, create_callback())
                    thread_timer.start()
                    self.active_timers[timer_key] = thread_timer
                    print(f"[TIMING-ENGINE] Restored timer {timer_record.id}: {remaining:.1f}s remaining")
                else:
                    self._execute_db_timer(timer_record.id)
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
            print(f"[TIMING-ENGINE] Executed DB timer {timer_id}: {timer_record.timer_type}")
            
            # Специальная обработка для timeout
            if timer_record.timer_type == 'timeout':
                print(f"[TIMING-ENGINE] Timeout executed: {timer_record.callback_node_id}")
            
            timer_key = f"db_{timer_id}"
            if timer_key in self.active_timers:
                del self.active_timers[timer_key]
        except Exception as e:
            logger.error(f"Failed to execute DB timer {timer_id}: {e}")
            db.rollback()
        finally:
            db.close()

    def cleanup_expired_timers(self):
        print("[TIMING-ENGINE] Cleaning up expired timers...")
        db = self._get_db_session()
        if not db:
            return
        try:
            from sqlalchemy import and_
            expired_count = db.query(ActiveTimer).filter(
                and_(ActiveTimer.status == 'pending', ActiveTimer.target_timestamp < utc_now())
            ).update({'status': 'expired'})
            db.commit()
            print(f"[TIMING-ENGINE] Marked {expired_count} timers as expired")
        except Exception as e:
            logger.error(f"Failed to cleanup expired timers: {e}")
            db.rollback()
        finally:
            db.close()

    # === Парсеры и исполнители ===
    def _init_parsers(self) -> Dict[str, Any]:
        return {
            'basic_pause': self._parse_basic_pause,
            'typing': self._parse_typing,
            'process': self._parse_process,
            'timeout': self._parse_timeout,  # УНИВЕРСАЛЬНАЯ timeout команда
            'daily': self._parse_daily,
            'remind': self._parse_remind,
            'deadline': self._parse_deadline
        }

    def _init_executors(self) -> Dict[str, Any]:
        return {
            'pause': self._execute_pause,
            'typing': self._execute_typing,
            'process': self._execute_process,
            'timeout': self._execute_timeout,  # УНИВЕРСАЛЬНЫЙ timeout исполнитель
            'daily': self._execute_daily,
            'remind': self._execute_remind,
            'deadline': self._execute_deadline
        }

    def execute_timing(self, timing_config: str, callback: Callable, **context) -> None:
        if not self.enabled:
            print(f"[TIMING-ENGINE] TimingEngine disabled, executing callback immediately")
            callback()
            return
        try:
            print(f"[TIMING-ENGINE] Processing timing: {timing_config}")
            commands = self._parse_timing_dsl(timing_config)
            print(f"[TIMING-ENGINE] Parsed commands: {commands}")
            self._execute_timing_commands(commands, callback, **context)
        except Exception as e:
            logger.error(f"TimingEngine error: {e}")
            print(f"[TIMING-ENGINE] ERROR: {e}")
            import traceback
            traceback.print_exc()
            callback()

    def _parse_timing_dsl(self, timing_config: str) -> List[Dict[str, Any]]:
        print(f"[TIMING-ENGINE] _parse_timing_dsl called with: '{timing_config}'")
        
        if not timing_config or timing_config.strip() == "":
            print(f"[TIMING-ENGINE] Empty timing config")
            return []

        command_strings = [cmd.strip() for cmd in timing_config.split(';') if cmd.strip()]
        print(f"[TIMING-ENGINE] Split into commands: {command_strings}")
        commands = []

        for cmd_str in command_strings:
            print(f"[TIMING-ENGINE] Processing command: '{cmd_str}'")
            parsed = None
            
            # Обратная совместимость: простые числа
            if re.match(r'^\d+(\.\d+)?(s)?$', cmd_str):
                parsed = self.parsers['basic_pause'](cmd_str)
                print(f"[TIMING-ENGINE] Parsed as basic_pause: {parsed}")
            # process команды
            elif cmd_str.startswith('process:'):
                parsed = self.parsers['process'](cmd_str)
                print(f"[TIMING-ENGINE] Parsed as process: {parsed}")
            # УНИВЕРСАЛЬНАЯ timeout команда  
            elif cmd_str.startswith('timeout:'):
                parsed = self.parsers['timeout'](cmd_str)
                print(f"[TIMING-ENGINE] Parsed as timeout: {parsed}")
            # typing команды с preset'ами
            elif cmd_str.startswith('typing:'):
                parsed = self.parsers['typing'](cmd_str)
                print(f"[TIMING-ENGINE] Parsed as typing: {parsed}")
            elif cmd_str.startswith('daily@'):
                parsed = self.parsers['daily'](cmd_str)
            elif cmd_str.startswith('remind:'):
                parsed = self.parsers['remind'](cmd_str)
            elif cmd_str.startswith('deadline:'):
                parsed = self.parsers['deadline'](cmd_str)

            if parsed:
                commands.append(parsed)
                print(f"[TIMING-ENGINE] Successfully parsed command: {parsed}")
            else:
                logger.warning(f"Unknown timing command: {cmd_str}")
                print(f"[TIMING-ENGINE] WARNING: Unknown timing command: {cmd_str}")

        print(f"[TIMING-ENGINE] Final parsed commands: {commands}")
        return commands

    def _execute_timing_commands(self, commands: List[Dict[str, Any]], 
                                 callback: Callable, **context) -> None:
        print(f"[TIMING-ENGINE] _execute_timing_commands called with {len(commands)} commands")
        
        if not commands:
            print(f"[TIMING-ENGINE] No timing commands to execute, calling callback immediately")
            callback()
            return

        for command in commands:
            cmd_type = command.get('type')
            print(f"[TIMING-ENGINE] Executing command type: {cmd_type}")
            
            if cmd_type in self.executors:
                print(f"[TIMING-ENGINE] Found executor for {cmd_type}, executing...")
                try:
                    self.executors[cmd_type](command, callback, **context)
                    print(f"[TIMING-ENGINE] Successfully executed {cmd_type}")
                except Exception as e:
                    print(f"[TIMING-ENGINE] ERROR executing {cmd_type}: {e}")
                    import traceback
                    traceback.print_exc()
            else:
                logger.warning(f"No executor for command type: {cmd_type}")
                print(f"[TIMING-ENGINE] WARNING: No executor for command type: {cmd_type}")

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
        """
        ИСПРАВЛЕНО: Парсинг timeout команды с различением preset'ов и узлов назначения
        
        Синтаксис:
        - timeout:15s:no_answer - переход на узел no_answer через 15s
        - timeout:5s:slow - переход на next_node_id через 5s с preset slow  
        - timeout:30s - переход на next_node_id через 30s с preset clean
        """
        print(f"[TIMING-ENGINE] _parse_timeout called with: '{cmd_str}'")
        
        # Список известных preset'ов
        known_presets = set(self.presets.keys())  # {'clean', 'keep', 'fast', 'slow', 'instant'}
        print(f"[TIMING-ENGINE] Known presets: {known_presets}")
        
        # Проверяем форматы
        pattern_with_arg = r'^timeout:(\d+(?:\.\d+)?)s:([^:]+)$'
        pattern_simple = r'^timeout:(\d+(?:\.\d+)?)s$'
        
        # Формат с аргументом: timeout:15s:xxx
        match_with_arg = re.match(pattern_with_arg, cmd_str)
        if match_with_arg:
            duration = float(match_with_arg.group(1))
            arg = match_with_arg.group(2).strip()
            
            print(f"[TIMING-ENGINE] Found arg: '{arg}', checking if it's a preset...")
            
            # Проверить, это preset или узел
            if arg in known_presets:
                # Это preset - используем next_node_id с preset настройками
                result = {
                    'type': 'timeout',
                    'duration': duration,
                    'target_node': None,              # Узел из next_node_id
                    'use_next_node_id': True,
                    'preset': arg,                    # Preset для anti-flicker
                    'show_countdown': True,
                    'original': cmd_str
                }
                print(f"[TIMING-ENGINE] _parse_timeout SUCCESS (with preset): {result}")
                return result
            else:
                # Это узел - явный переход
                result = {
                    'type': 'timeout',
                    'duration': duration,
                    'target_node': arg,               # Явно указанный узел
                    'use_next_node_id': False,
                    'preset': 'clean',                # Дефолтный preset
                    'show_countdown': True,
                    'original': cmd_str
                }
                print(f"[TIMING-ENGINE] _parse_timeout SUCCESS (with target node): {result}")
                return result
        
        # Простой формат: timeout:30s
        match_simple = re.match(pattern_simple, cmd_str)
        if match_simple:
            duration = float(match_simple.group(1))
            
            result = {
                'type': 'timeout',
                'duration': duration,
                'target_node': None,
                'use_next_node_id': True,
                'preset': 'clean',                    # Дефолтный preset
                'show_countdown': True,
                'original': cmd_str
            }
            print(f"[TIMING-ENGINE] _parse_timeout SUCCESS (simple): {result}")
            return result
        
        print(f"[TIMING-ENGINE] _parse_timeout FAILED to parse: '{cmd_str}'")
        return None

    def _parse_daily(self, cmd_str: str) -> Dict[str, Any]:
        m = re.match(r'^daily@(\d{2}):(\d{2})([A-Z]{3})?$', cmd_str)
        if m:
            return {'type': 'daily', 'hour': int(m.group(1)), 'minute': int(m.group(2)), 
                    'timezone': m.group(3) or 'UTC', 'original': cmd_str}
        return None

    def _parse_remind(self, cmd_str: str) -> Dict[str, Any]:
        m = re.match(r'^remind:(.+)$', cmd_str)
        if m:
            intervals = []
            for interval in m.group(1).split(','):
                t = interval.strip()
                tm = re.match(r'^(\d+)(h|m|s)$', t)
                if tm:
                    v = int(tm.group(1)); u = tm.group(2)
                    sec = v if u == 's' else v*60 if u == 'm' else v*3600
                    intervals.append(sec)
            return {'type': 'remind', 'intervals': intervals, 'original': cmd_str}
        return None

    def _parse_deadline(self, cmd_str: str) -> Dict[str, Any]:
        m = re.match(r'^deadline:(\d+)(h|d)$', cmd_str)
        if m:
            v = int(m.group(1)); u = m.group(2)
            sec = v*3600 if u == 'h' else v*86400
            return {'type': 'deadline', 'duration': sec, 'original': cmd_str}
        return None

    # === Исполнители ===
    def _execute_pause(self, command: Dict[str, Any], callback: Callable, **context) -> None:
        duration = command['duration']
        pause_text = context.get('pause_text') or ''
        bot = context.get('bot'); chat_id = context.get('chat_id')
        print(f"[TIMING-ENGINE] Executing simple pause: {duration}s")
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

        print(f"[TIMING-ENGINE] Executing typing progress bar: {duration}s ({process_name}) preset={preset}")

        session_id = context.get('session_id')
        if session_id:
            timer_id = self.save_timer_to_db(
                session_id=session_id, timer_type='typing',
                delay_seconds=int(duration), message_text=process_name,
                callback_data={'command': command, 'preset': preset}
            )

        bot = context.get('bot'); chat_id = context.get('chat_id')
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
                    print(f"[TIMING-ENGINE] Progress bar failed: {e}")
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

        print(f"[TIMING-ENGINE] Executing static process: {duration}s ({process_name}) preset={preset}")

        session_id = context.get('session_id')
        if session_id:
            self.save_timer_to_db(
                session_id=session_id, timer_type='process',
                delay_seconds=int(duration), message_text=process_name,
                callback_data={'command': command, 'preset': preset}
            )

        bot = context.get('bot'); chat_id = context.get('chat_id')
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
                    print(f"[TIMING-ENGINE] Static process failed: {e}")
                    callback()
            
            threading.Thread(target=show_static_process).start()
        else:
            threading.Timer(duration, callback).start()

    def _execute_timeout(self, command: Dict[str, Any], callback: Callable, **context) -> None:
        """
        ИСПРАВЛЕНО: Timeout с поддержкой preset'ов и удалением кнопок
        """
        print(f"[TIMING-ENGINE] _execute_timeout called with command: {command}")
        print(f"[TIMING-ENGINE] _execute_timeout context keys: {list(context.keys())}")
        
        duration = int(command['duration'])
        use_next_node_id = command.get('use_next_node_id', False)
        explicit_target = command.get('target_node')
        preset = command.get('preset', 'clean')
        
        print(f"[TIMING-ENGINE] Timeout config: duration={duration}, use_next_node_id={use_next_node_id}, explicit_target={explicit_target}, preset={preset}")
        
        # Получить preset конфигурацию
        preset_config = self.presets.get(preset, self.presets['clean'])
        print(f"[TIMING-ENGINE] Using preset '{preset}': {preset_config}")
        
        # Определяем целевой узел
        if use_next_node_id:
            target_node = context.get('next_node_id')
            if not target_node:
                print(f"[TIMING-ENGINE] ERROR: timeout requires next_node_id in context when use_next_node_id=True")
                callback()
                return
            print(f"[TIMING-ENGINE] Using next_node_id as target: {target_node}")
        else:
            target_node = explicit_target
            print(f"[TIMING-ENGINE] Using explicit target: {target_node}")
            
        session_id = context.get('session_id')
        bot = context.get('bot')
        chat_id = context.get('chat_id')
        
        print(f"[TIMING-ENGINE] Starting timeout: {duration}s → {target_node} (session: {session_id}) preset: {preset}")
        
        # КРИТИЧЕСКИ ВАЖНО: Установить timeout_target_node в контекст ПЕРЕД callback
        context['timeout_target_node'] = target_node
        if hasattr(callback, 'context'):
            callback.context.update(context)
        print(f"[TIMING-ENGINE] Set timeout_target_node in context: {target_node}")
        
        # Сохранить в БД
        if session_id:
            timer_id = self.save_timer_to_db(
                session_id=session_id, timer_type='timeout',
                delay_seconds=duration, message_text=f"Timeout {duration}s",
                callback_node_id=target_node,
                callback_data={'command': command, 'target_node': target_node, 'preset': preset}
            )
            if timer_id:
                print(f"[TIMING-ENGINE] Timeout saved to DB with ID: {timer_id}")
        
        # Сохранить для отладки
        self.debug_timers[session_id] = {
            'type': 'timeout',
            'duration': duration,
            'target_node': target_node,
            'preset': preset,
            'started_at': time.time(),
            'chat_id': chat_id
        }
        print(f"[TIMING-ENGINE] Timeout registered in debug_timers for session {session_id}")
        
        def timeout_handler():
            print(f"[TIMING-ENGINE] TIMEOUT FIRED for session {session_id} after {duration}s")
            
            # Проверить отмену
            if session_id in self.cancelled_tasks:
                print(f"[TIMING-ENGINE] Timeout was cancelled for session {session_id}")
                self.cancelled_tasks.discard(session_id)
                return
            
            # НОВОЕ: Сообщить о срабатывании timeout в чат
            if bot and chat_id:
                try:
                    bot.send_message(chat_id, "⏰ Время истекло! Переход к следующему этапу...")
                except Exception as e:
                    print(f"[TIMING-ENGINE] Failed to send timeout message: {e}")
            
            # НОВОЕ: Применить preset перед callback
            exposure_time = preset_config.get('exposure_time', 0)
            anti_flicker_delay = preset_config.get('anti_flicker_delay', 0)
            
            if exposure_time > 0:
                print(f"[TIMING-ENGINE] Applying exposure time: {exposure_time}s")
                time.sleep(exposure_time)
            
            print(f"[TIMING-ENGINE] Executing timeout callback → {target_node}")
            print(f"[TIMING-ENGINE] Callback context: {getattr(callback, 'context', {})}")
            
            try:
                callback()
                print(f"[TIMING-ENGINE] Timeout callback executed successfully")
            except Exception as e:
                print(f"[TIMING-ENGINE] ERROR in timeout callback: {e}")
                import traceback
                traceback.print_exc()
            
            # НОВОЕ: Anti-flicker задержка после callback
            if anti_flicker_delay > 0:
                print(f"[TIMING-ENGINE] Applying anti-flicker delay: {anti_flicker_delay}s")
                time.sleep(anti_flicker_delay)
            
            # Очистка
            if session_id in self.debug_timers:
                del self.debug_timers[session_id]
            if session_id in self.active_timeouts:
                del self.active_timeouts[session_id]
        
        print(f"[TIMING-ENGINE] Creating Timer for {duration} seconds...")
        timer = threading.Timer(duration, timeout_handler)
        timer.start()
        
        # Сохранить ссылку на таймер
        timer_key = f"timeout_{session_id}"
        self.active_timers[timer_key] = timer
        print(f"[TIMING-ENGINE] Timer started and saved with key: {timer_key}")
        
        # Показать информацию о timeout в чате
        if bot and chat_id:
            try:
                if preset == 'clean':
                    preset_desc = ""
                else:
                    preset_desc = f" (режим: {preset})"
                bot.send_message(chat_id, f"⏳ Автопереход через {duration} секунд к узлу: {target_node}{preset_desc}")
            except Exception as e:
                print(f"[TIMING-ENGINE] Failed to send countdown message: {e}")

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
                    print(f"[TIMING-ENGINE] Deleted after {exposure_time}s exposure: {process_name}")
                except Exception:
                    pass
            
            if anti_flicker_delay > 0:
                time.sleep(anti_flicker_delay)
                
        except Exception as e:
            print(f"[TIMING-ENGINE] Process with presets failed: {e}")

    def process_timing(self, user_id: int, session_id: int, node_id: str, 
                       timing_config: str, callback: Callable, **context) -> None:
        """
        ГЛАВНАЯ ФУНКЦИЯ: Обработка timing команд с диагностикой
        """
        print(f"[TIMING-ENGINE] process_timing called:")
        print(f"[TIMING-ENGINE]   - user_id: {user_id}")
        print(f"[TIMING-ENGINE]   - session_id: {session_id}")
        print(f"[TIMING-ENGINE]   - node_id: {node_id}")
        print(f"[TIMING-ENGINE]   - timing_config: '{timing_config}'")
        print(f"[TIMING-ENGINE]   - context keys: {list(context.keys())}")
        
        if not self.enabled:
            print(f"[TIMING-ENGINE] TimingEngine disabled, calling callback immediately")
            callback()
            return
            
        try:
            # Добавляем session_id в контекст
            enriched_context = dict(context)
            enriched_context['session_id'] = session_id
            
            print(f"[TIMING-ENGINE] Enriched context keys: {list(enriched_context.keys())}")
            
            # Выполняем timing
            self.execute_timing(timing_config, callback, **enriched_context)
            
        except Exception as e:
            logger.error(f"process_timing error: {e}")
            print(f"[TIMING-ENGINE] ERROR in process_timing: {e}")
            import traceback
            traceback.print_exc()
            callback()

    # === Управление timeout ===
    def cancel_timeout_task(self, session_id: int) -> bool:
        """Отменить активный timeout для сессии"""
        print(f"[TIMING-ENGINE] cancel_timeout_task called for session: {session_id}")
        
        # Отменить через cancelled_tasks
        self.cancelled_tasks.add(session_id)
        
        # Попытаться отменить таймер
        timer_key = f"timeout_{session_id}"
        if timer_key in self.active_timers:
            timer = self.active_timers[timer_key]
            timer.cancel()
            del self.active_timers[timer_key]
            print(f"[TIMING-ENGINE] Cancelled and removed timer: {timer_key}")
        
        # Очистить отладочную информацию
        if session_id in self.debug_timers:
            print(f"[TIMING-ENGINE] Removed debug timer info for session: {session_id}")
            del self.debug_timers[session_id]
        
        if session_id in self.active_timeouts:
            del self.active_timeouts[session_id]
            
        print(f"[TIMING-ENGINE] Timeout cancellation completed for session: {session_id}")
        return True

    def cleanup_timeout_tasks(self):
        """Очистка завершенных timeout задач"""
        completed = [sid for sid, thread in self.active_timeouts.items() if not thread.is_alive()]
        for session_id in completed:
            del self.active_timeouts[session_id]
            self.cancelled_tasks.discard(session_id)
        if completed:
            print(f"[TIMING-ENGINE] Removed {len(completed)} completed timeout tasks")

    # Остальные исполнители - заглушки
    def _execute_daily(self, command: Dict[str, Any], callback: Callable, **context) -> None:
        print(f"[TIMING-ENGINE] Daily scheduling not implemented yet")
        callback()

    def _execute_remind(self, command: Dict[str, Any], callback: Callable, **context) -> None:
        print(f"[TIMING-ENGINE] Reminder system not implemented yet")
        callback()

    def _execute_deadline(self, command: Dict[str, Any], callback: Callable, **context) -> None:
        print(f"[TIMING-ENGINE] Deadline system not implemented yet")
        callback()

    # Утилиты
    def cancel_user_timers(self, user_id: int) -> None:
        to_cancel = [key for key in self.active_timers.keys() if key.startswith(f"{user_id}_")]
        for key in to_cancel:
            timer = self.active_timers.pop(key)
            timer.cancel()

    def get_status(self) -> Dict[str, Any]:
        return {
            'enabled': self.enabled,
            'active_timers': len(self.active_timers),
            'active_timeouts': len(self.active_timeouts),
            'cancelled_tasks': len(self.cancelled_tasks),
            'debug_timers': len(self.debug_timers),
            'available_parsers': list(self.parsers.keys()),
            'available_executors': list(self.executors.keys()),
            'available_presets': list(self.presets.keys())
        }

    def enable(self) -> None:
        self.enabled = True
        print(f"[TIMING-ENGINE] TimingEngine ENABLED")

    def disable(self) -> None:
        self.enabled = False
        for timer in self.active_timers.values():
            timer.cancel()
        self.active_timers.clear()
        self.cancelled_tasks.clear()
        self.active_timeouts.clear()
        self.debug_timers.clear()
        print(f"[TIMING-ENGINE] TimingEngine DISABLED")

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
