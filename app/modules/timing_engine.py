# -*- coding: utf-8 -*-
"""
R-Bot Timing Engine - система временных механик с preset'ами и контролем экспозиции

ОБНОВЛЕНИЯ:
05.10.2025 - Добавлены preset'ы для контроля экспозиции и anti-flicker
05.10.2025 - Объединение state и timing в единый механизм
05.10.2025 - timeout_task переименован в timeout (универсальная команда)
05.10.2025 - timeout поддерживает переходы из next_node_id и переопределения

DSL команды:
- process:5s:Название:preset - статические сообщения (замена state: true)
- typing:5s:Название:preset - прогресс-бары с preset'ами
- timeout:30s - универсальные таймеры (переход из next_node_id)
- timeout:30s:override_node - универсальные таймеры (переопределение перехода)

Preset'ы:
- clean (по умолчанию): 1.5s экспозиция + 1s пауза + удалить
- keep: 0s экспозиция + 0.5s пауза + оставить в ленте
- fast: 0.8s экспозиция + 0.5s пауза + удалить
- slow: 3s экспозиция + 2s пауза + удалить  
- instant: 0s экспозиция + 0s пауза + мгновенно удалить

timeout использование:
- С кнопками: временные ограничения на выбор (отменяется при нажатии)
- Без кнопок: автопереход через время (не отменяется)
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
        
        self.initialized = True

        logger.info(f"TimingEngine initialized with universal timeout command. Enabled: {self.enabled}")
        print(f"[INIT] TimingEngine initialized with enabled={self.enabled}")
        print(f"[INIT] Available presets: {list(self.presets.keys())}")
        print(f"[INIT] Available commands: {list(self.parsers.keys())}")

        if self.enabled:
            try:
                self.restore_timers_from_db()
                self.cleanup_expired_timers()
            except Exception as e:
                logger.error(f"Failed to restore/cleanup timers on init: {e}")
                print(f"[ERROR] Failed to restore/cleanup timers on init: {e}")

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
            print(f"[INFO] Timer saved to DB: ID={timer_record.id}, type={timer_type}")
            return timer_record.id
        except Exception as e:
            logger.error(f"Failed to save timer to DB: {e}")
            db.rollback()
            return None
        finally:
            db.close()

    def restore_timers_from_db(self):
        print("[INFO] Restoring timers from database...")
        db = self._get_db_session()
        if not db:
            return
        try:
            pending_timers = db.query(ActiveTimer).filter(
                ActiveTimer.status == 'pending',
                ActiveTimer.target_timestamp > utc_now()
            ).all()
            print(f"[INFO] Found {len(pending_timers)} pending timers to restore")
            
            for timer_record in pending_timers:
                remaining = (timer_record.target_timestamp - utc_now()).total_seconds()
                if remaining > 0:
                    timer_key = f"db_{timer_record.id}"
                    def create_callback(tid=timer_record.id):
                        return lambda: self._execute_db_timer(tid)
                    
                    thread_timer = threading.Timer(remaining, create_callback())
                    thread_timer.start()
                    self.active_timers[timer_key] = thread_timer
                    print(f"[INFO] Restored timer {timer_record.id}: {remaining:.1f}s remaining")
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
            print(f"[INFO] Executed DB timer {timer_id}: {timer_record.timer_type}")
            
            # Специальная обработка для timeout
            if timer_record.timer_type == 'timeout':
                print(f"[INFO] Timeout executed: {timer_record.callback_node_id}")
            
            timer_key = f"db_{timer_id}"
            if timer_key in self.active_timers:
                del self.active_timers[timer_key]
        except Exception as e:
            logger.error(f"Failed to execute DB timer {timer_id}: {e}")
            db.rollback()
        finally:
            db.close()

    def cleanup_expired_timers(self):
        print("[INFO] Cleaning up expired timers...")
        db = self._get_db_session()
        if not db:
            return
        try:
            from sqlalchemy import and_
            expired_count = db.query(ActiveTimer).filter(
                and_(ActiveTimer.status == 'pending', ActiveTimer.target_timestamp < utc_now())
            ).update({'status': 'expired'})
            db.commit()
            print(f"[INFO] Marked {expired_count} timers as expired")
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
            print(f"[WARNING] TimingEngine disabled, executing callback immediately")
            callback()
            return
        try:
            print(f"--- [TIMING] Обработка timing: {timing_config} ---")
            commands = self._parse_timing_dsl(timing_config)
            print(f"[INFO] TimingEngine: Parsed commands: {commands}")
            self._execute_timing_commands(commands, callback, **context)
        except Exception as e:
            logger.error(f"TimingEngine error: {e}")
            print(f"[ERROR] TimingEngine error: {e}")
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
                print(f"[WARNING] Unknown timing command: {cmd_str}")

        return commands

    def _execute_timing_commands(self, commands: List[Dict[str, Any]], 
                                 callback: Callable, **context) -> None:
        if not commands:
            print(f"[INFO] No timing commands to execute, calling callback immediately")
            callback()
            return

        for command in commands:
            cmd_type = command.get('type')
            if cmd_type in self.executors:
                print(f"[INFO] Executing command: {command}")
                self.executors[cmd_type](command, callback, **context)
            else:
                logger.warning(f"No executor for command type: {cmd_type}")
                print(f"[WARNING] No executor for command type: {cmd_type}")

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
        ОБНОВЛЕНО: Парсинг универсальной timeout команды
        
        Синтаксис:
        - timeout:30s - переход к узлу из next_node_id (основной случай 90%)
        - timeout:30s:override_node - переход к override_node (переопределение 10%)
        
        Применение:
        - С кнопками: временные ограничения на выбор (отменяется при нажатии)
        - Без кнопок: автопереход через время (принудительный переход)
        """
        # Проверяем оба формата
        pattern_with_node = r'^timeout:(\d+(?:\.\d+)?)s:([^:]+)$'
        pattern_simple = r'^timeout:(\d+(?:\.\d+)?)s$'
        
        # Формат с переопределением узла: timeout:30s:override_node
        match_with_node = re.match(pattern_with_node, cmd_str)
        if match_with_node:
            duration = float(match_with_node.group(1))
            target_node = match_with_node.group(2)
            
            return {
                'type': 'timeout',
                'duration': duration,
                'target_node': target_node,        # Явно указанный узел
                'use_next_node_id': False,        # НЕ использовать next_node_id
                'show_countdown': True,
                'original': cmd_str
            }
        
        # Простой формат: timeout:30s (переход из next_node_id)
        match_simple = re.match(pattern_simple, cmd_str)
        if match_simple:
            duration = float(match_simple.group(1))
            
            return {
                'type': 'timeout',
                'duration': duration,
                'target_node': None,              # Узел НЕ указан
                'use_next_node_id': True,        # Использовать next_node_id
                'show_countdown': True,
                'original': cmd_str
            }
        
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
        print(f"[INFO] TimingEngine: Executing simple pause: {duration}s")
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

        print(f"[INFO] TimingEngine: Executing typing progress bar: {duration}s ({process_name}) preset={preset}")

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
                    print(f"[ERROR] Progress bar failed: {e}")
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

        print(f"[INFO] TimingEngine: Executing static process: {duration}s ({process_name}) preset={preset}")

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
                    print(f"[ERROR] Static process failed: {e}")
                    callback()
            
            threading.Thread(target=show_static_process).start()
        else:
            threading.Timer(duration, callback).start()

    def _execute_timeout(self, command: Dict[str, Any], callback: Callable, **context) -> None:
        """
        ОБНОВЛЕНО: Универсальный timeout исполнитель
        
        Логика:
        - timeout:30s → переход к узлу из context['next_node_id']  
        - timeout:30s:override → переход к override узлу
        - С кнопками: отменяется при нажатии кнопки
        - Без кнопок: принудительный автопереход
        """
        duration = int(command['duration'])
        use_next_node_id = command.get('use_next_node_id', False)
        explicit_target = command.get('target_node')
        
        # Определяем целевой узел
        if use_next_node_id:
            target_node = context.get('next_node_id')
            if not target_node:
                print(f"[ERROR] timeout:30s requires next_node_id in context")
                callback()
                return
        else:
            target_node = explicit_target
            
        session_id = context.get('session_id')
        bot = context.get('bot')
        chat_id = context.get('chat_id')
        
        print(f"[INFO] Starting timeout: {duration}s → {target_node} (session: {session_id})")
        
        # Сохранить в БД
        if session_id:
            timer_id = self.save_timer_to_db(
                session_id=session_id, timer_type='timeout',
                delay_seconds=duration, message_text=f"Timeout {duration}s",
                callback_node_id=target_node,
                callback_data={'command': command, 'target_node': target_node}
            )
            if timer_id:
                print(f"[INFO] Timeout saved to DB with ID: {timer_id}")
        
        if not bot or not chat_id:
            print("[WARNING] No bot/chat_id for timeout, using simple timer")
            threading.Timer(duration, callback).start()
            return
            
        # Показать обратный отсчет
        countdown_msg = bot.send_message(chat_id, f"⏳ Автопереход через: {duration} секунд")
        
        def countdown_timer():
            """Поток обратного отсчета с проверкой отмены"""
            for remaining in range(duration-1, 0, -1):
                time.sleep(1)
                
                # Проверить отмену (только если есть кнопки)
                if session_id and session_id in self.cancelled_tasks:
                    try:
                        bot.edit_message_text(
                            chat_id=chat_id, message_id=countdown_msg.message_id,
                            text="✅ Ответ получен, переход отменен!"
                        )
                        time.sleep(1)
                        bot.delete_message(chat_id, countdown_msg.message_id)
                    except Exception as e:
                        print(f"[WARNING] Failed to update cancelled timeout: {e}")
                    
                    self.cancelled_tasks.discard(session_id)
                    print(f"[INFO] Timeout cancelled by user (session: {session_id})")
                    return
                
                # Обновить счетчик
                try:
                    bot.edit_message_text(
                        chat_id=chat_id, message_id=countdown_msg.message_id,
                        text=f"⏳ Автопереход через: {remaining} {'секунду' if remaining == 1 else 'секунд'}"
                    )
                except Exception as e:
                    print(f"[WARNING] Failed to update countdown: {e}")
            
            # Финальная проверка на отмену
            if session_id and session_id in self.cancelled_tasks:
                self.cancelled_tasks.discard(session_id)
                return
            
            # Время истекло - автопереход
            try:
                bot.edit_message_text(
                    chat_id=chat_id, message_id=countdown_msg.message_id, 
                    text="⏰ Переход выполнен!"
                )
                time.sleep(1)
                bot.delete_message(chat_id, countdown_msg.message_id)
            except Exception as e:
                print(f"[WARNING] Failed to show transition message: {e}")
            
            # Установить target для перехода
            context['timeout_target_node'] = target_node
            print(f"[INFO] Timeout expired → target: {target_node}")
            callback()
            
            # Очистить активный timeout
            if session_id in self.active_timeouts:
                del self.active_timeouts[session_id]
        
        # Запустить поток
        countdown_thread = threading.Thread(target=countdown_timer)
        countdown_thread.daemon = True
        countdown_thread.start()
        
        # Сохранить ссылку
        if session_id:
            self.active_timeouts[session_id] = countdown_thread

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
                    print(f"[CLEANUP] Deleted after {exposure_time}s exposure: {process_name}")
                except Exception:
                    pass
            
            if anti_flicker_delay > 0:
                time.sleep(anti_flicker_delay)
                
        except Exception as e:
            print(f"[ERROR] Process with presets failed: {e}")

    def process_timing(self, user_id: int, session_id: int, node_id: str, 
                       timing_config: str, callback: Callable, **context) -> None:
        if not self.enabled:
            callback(); return
        try:
            print(f"--- [TIMING] Обработка timing для узла {node_id}: {timing_config} ---")
            commands = self._parse_timing_dsl(timing_config)
            enriched_context = dict(context)
            enriched_context['session_id'] = session_id
            self._execute_timing_commands(commands, callback, **enriched_context)
        except Exception as e:
            logger.error(f"TimingEngine error: {e}")
            callback()

    # === Управление timeout ===
    def cancel_timeout_task(self, session_id: int) -> bool:
        """Отменить активный timeout для сессии"""
        if session_id in self.active_timeouts:
            print(f"[INFO] Cancelling timeout for session: {session_id}")
            self.cancelled_tasks.add(session_id)
            return True
        return False

    def cleanup_timeout_tasks(self):
        """Очистка завершенных timeout задач"""
        completed = [sid for sid, thread in self.active_timeouts.items() if not thread.is_alive()]
        for session_id in completed:
            del self.active_timeouts[session_id]
            self.cancelled_tasks.discard(session_id)
        if completed:
            print(f"[CLEANUP] Removed {len(completed)} completed timeout tasks")

    # Остальные исполнители - заглушки
    def _execute_daily(self, command: Dict[str, Any], callback: Callable, **context) -> None:
        print(f"[WARNING] Daily scheduling not implemented yet")
        callback()

    def _execute_remind(self, command: Dict[str, Any], callback: Callable, **context) -> None:
        print(f"[WARNING] Reminder system not implemented yet")
        callback()

    def _execute_deadline(self, command: Dict[str, Any], callback: Callable, **context) -> None:
        print(f"[WARNING] Deadline system not implemented yet")
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
            'available_parsers': list(self.parsers.keys()),
            'available_executors': list(self.executors.keys()),
            'available_presets': list(self.presets.keys())
        }

    def enable(self) -> None:
        self.enabled = True
        print(f"[INFO] TimingEngine ENABLED")

    def disable(self) -> None:
        self.enabled = False
        for timer in self.active_timers.values():
            timer.cancel()
        self.active_timers.clear()
        self.cancelled_tasks.clear()
        self.active_timeouts.clear()
        print(f"[INFO] TimingEngine DISABLED")

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

if __name__ == "__main__":
    # Тестирование универсальной timeout команды
    test_engine = TimingEngine()
    
    print("🧪 TESTING UNIVERSAL TIMEOUT COMMAND:")
    
    test_cases = [
        # Простые timeout (используют next_node_id)
        "timeout:30s",
        "timeout:60s",
        
        # timeout с переопределением
        "timeout:30s:no_answer",
        "timeout:15s:time_expired", 
        
        # Комбинированные
        "typing:5s:Подготовка:fast; timeout:30s",
        "process:3s:Загрузка:clean; timeout:60s:survey_timeout"
    ]
    
    for test_case in test_cases:
        print(f"\nТест: '{test_case}'")
        try:
            commands = test_engine._parse_timing_dsl(test_case)
            for cmd in commands:
                if cmd['type'] == 'timeout':
                    if cmd.get('use_next_node_id'):
                        print(f"  → timeout: {cmd['duration']}s (переход из next_node_id)")
                    else:
                        print(f"  → timeout: {cmd['duration']}s → {cmd['target_node']}")
                else:
                    print(f"  → {cmd['type']}: {cmd}")
        except Exception as e:
            print(f"  ❌ Ошибка: {e}")
    
    print("\n✅ Универсальная timeout команда готова!")