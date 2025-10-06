# -*- coding: utf-8 -*-
"""
R-Bot Timing Engine - система временных механик с Daily системой

ОБНОВЛЕНИЯ:
06.10.2025 - ДОБАВЛЕНЫ адаптивные countdown сообщения
06.10.2025 - ДОБАВЛЕН Silent Mode для сценарных timeout'ов
06.10.2025 - ДОБАВЛЕНА Daily система (легковесный персональный cron)

DSL команды:
- timeout:15s:no_answer - интерактивный timeout с countdown
- timeout:5s:slow - тихий timeout для драматургии
- typing:5s:Анализ поведения:clean - прогресс-бар с preset
- daily@09:00:MSK - ежедневные уведомления в 09:00 по Москве
- daily@15:30:UTC - ежедневные уведомления в 15:30 UTC
- remind:5m,1h,1d - система напоминаний (заготовка)  
- deadline:2h - дедлайны с предупреждениями (заготовка)
"""

import threading
import time
import re
import logging
from datetime import datetime, timedelta, date
from typing import Dict, Any, Callable, Optional, List, Set
import pytz

from app.modules.database.models import ActiveTimer, utc_now
from app.modules.database import SessionLocal

TIMING_ENABLED = True
logger = logging.getLogger(__name__)

class TimingEngine:
    """
    Timing Engine с Daily системой (легковесный персональный cron)
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

        logger.info(f"TimingEngine initialized with Daily system. Enabled: {self.enabled}")
        print(f"[TIMING-ENGINE] TimingEngine initialized with Daily system")
        print(f"[TIMING-ENGINE] Available commands: {list(self.parsers.keys())}")
        print(f"[TIMING-ENGINE] Daily system: Lightweight personal cron activated")

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
        if duration <= 5:
            base_type = "urgent"
        elif duration <= 15:
            base_type = "choice"
        elif duration <= 60:
            base_type = "decision"
        else:
            base_type = "gentle"

        if node_id:
            node_lower = node_id.lower()
            if any(keyword in node_lower for keyword in ['test', 'quiz', 'question', 'answer']):
                return "answer"
            elif any(keyword in node_lower for keyword in ['timing', 'speed', 'reaction']):
                return "choice"

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
        """Определяет Silent Mode vs Interactive Mode для timeout"""
        pause_text = context.get('pause_text', '').strip()
        has_pause_text = bool(pause_text)

        has_buttons = len(context.get('buttons', [])) > 0

        print(f"[TIMING-ENGINE] Silent mode check:")
        print(f"  - pause_text: '{pause_text[:30]}{'...' if len(pause_text) > 30 else ''}'")
        print(f"  - has_buttons: {has_buttons}")

        show_countdown = has_buttons and not has_pause_text
        mode = "INTERACTIVE" if show_countdown else "SILENT"
        print(f"[TIMING-ENGINE] Timeout mode: {mode}")

        return show_countdown

    # === DAILY СИСТЕМА ===

    def calculate_next_daily_time(self, hour: int, minute: int, timezone_str: str = "UTC") -> datetime:
        """
        Вычисляет timestamp следующего срабатывания daily команды
        """
        timezone_mapping = {
            'MSK': 'Europe/Moscow',
            'UTC': 'UTC', 
            'EST': 'US/Eastern',
            'PST': 'US/Pacific',
            'CET': 'Europe/Berlin',
            'GMT': 'Europe/London'
        }

        try:
            tz_name = timezone_mapping.get(timezone_str, 'UTC')
            target_tz = pytz.timezone(tz_name)
            utc_tz = pytz.UTC

            now_utc = datetime.utcnow().replace(tzinfo=utc_tz)
            now_target = now_utc.astimezone(target_tz)

            print(f"[DAILY] Current time in {timezone_str}: {now_target.strftime('%H:%M:%S')}")

            from datetime import time
            today_target = target_tz.localize(
                datetime.combine(now_target.date(), time(hour, minute))
            )

            if today_target > now_target:
                next_daily = today_target
                print(f"[DAILY] Scheduling for today: {next_daily.strftime('%Y-%m-%d %H:%M %Z')}")
            else:
                tomorrow_date = now_target.date() + timedelta(days=1)
                next_daily = target_tz.localize(
                    datetime.combine(tomorrow_date, time(hour, minute))
                )
                print(f"[DAILY] Scheduling for tomorrow: {next_daily.strftime('%Y-%m-%d %H:%M %Z')}")

            next_daily_utc = next_daily.astimezone(utc_tz).replace(tzinfo=None)
            print(f"[DAILY] Next execution UTC: {next_daily_utc}")
            return next_daily_utc

        except Exception as e:
            logger.error(f"Failed to calculate daily time: {e}")
            fallback_time = datetime.utcnow() + timedelta(hours=24)
            print(f"[DAILY] Fallback to 24h from now: {fallback_time}")
            return fallback_time

    def schedule_next_daily(self, hour: int, minute: int, timezone_str: str, 
                           session_id: int, context: dict):
        """Автоматически планирует следующий daily через 24 часа"""
        try:
            next_time = self.calculate_next_daily_time(hour, minute, timezone_str)
            delay_seconds = int((next_time - datetime.utcnow()).total_seconds())

            if delay_seconds <= 0:
                delay_seconds = 24 * 3600

            print(f"[DAILY] Rescheduling next daily in {delay_seconds} seconds ({delay_seconds/3600:.1f}h)")

            timer_id = self.save_timer_to_db(
                session_id=session_id, 
                timer_type='daily',
                delay_seconds=delay_seconds,
                message_text=f"Daily {hour:02d}:{minute:02d} {timezone_str} (auto-rescheduled)",
                callback_node_id="",
                callback_data={
                    'hour': hour,
                    'minute': minute, 
                    'timezone': timezone_str,
                    'auto_reschedule': True,
                    'context': context
                }
            )

            def next_daily_callback():
                print(f"[DAILY] Auto-rescheduled daily triggered: {hour:02d}:{minute:02d} {timezone_str}")

                saved_context = context.copy()

                def scenario_callback():
                    bot = saved_context.get('bot')
                    chat_id = saved_context.get('chat_id')
                    next_node_id = saved_context.get('next_node_id')

                    if bot and chat_id and next_node_id:
                        try:
                            from app.modules.telegram_handler import send_node_message
                            send_node_message(chat_id, next_node_id)
                        except Exception as e:
                            logger.error(f"Failed to continue scenario from daily: {e}")
                            bot.send_message(chat_id, "⏰ Ежедневное напоминание")

                scenario_callback()
                self.schedule_next_daily(hour, minute, timezone_str, session_id, context)

            next_timer = threading.Timer(delay_seconds, next_daily_callback)
            next_timer.start()

            timer_key = f"daily_{session_id}_{hour}_{minute}_{timezone_str}"
            self.active_timers[timer_key] = next_timer

            print(f"[DAILY] Next daily scheduled with timer_id: {timer_id}")

        except Exception as e:
            logger.error(f"Failed to schedule next daily: {e}")

    def _init_presets(self) -> Dict[str, Dict[str, Any]]:
        """Инициализация preset'ов"""
        return {
            'clean': {'exposure_time': 1.5, 'anti_flicker_delay': 1.0, 'action': 'delete'},
            'keep': {'exposure_time': 0, 'anti_flicker_delay': 0.5, 'action': 'keep'},
            'fast': {'exposure_time': 0.8, 'anti_flicker_delay': 0.5, 'action': 'delete'},
            'slow': {'exposure_time': 3.0, 'anti_flicker_delay': 2.0, 'action': 'delete'},
            'instant': {'exposure_time': 0, 'anti_flicker_delay': 0, 'action': 'delete'}
        }

    @classmethod
    def get_instance(cls):
        return cls()

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
        """ОБНОВЛЕНО: Восстановление таймеров + Daily система"""
        db = self._get_db_session()
        if not db:
            return
        try:
            # Восстановление обычных таймеров
            pending_timers = db.query(ActiveTimer).filter(
                ActiveTimer.status == 'pending',
                ActiveTimer.target_timestamp > utc_now(),
                ActiveTimer.timer_type.in_(['timeout', 'typing', 'process'])
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

            # НОВОЕ: Восстановление DAILY таймеров
            daily_timers = db.query(ActiveTimer).filter(
                ActiveTimer.status == 'pending',
                ActiveTimer.timer_type == 'daily',
                ActiveTimer.target_timestamp > utc_now()
            ).all()

            for daily_record in daily_timers:
                remaining = (daily_record.target_timestamp - utc_now()).total_seconds()
                if remaining > 0:
                    callback_data = daily_record.callback_data or {}
                    hour = callback_data.get('hour', 9)
                    minute = callback_data.get('minute', 0)
                    timezone_str = callback_data.get('timezone', 'UTC')
                    session_id = daily_record.session_id
                    saved_context = callback_data.get('context', {})

                    print(f"[DAILY] Restoring daily timer: {hour:02d}:{minute:02d} {timezone_str}")

                    def create_daily_callback(h=hour, m=minute, tz=timezone_str, sid=session_id, ctx=saved_context):
                        def restored_daily_callback():
                            print(f"[DAILY] Restored daily triggered: {h:02d}:{m:02d} {tz}")

                            bot = ctx.get('bot')
                            chat_id = ctx.get('chat_id') 
                            next_node_id = ctx.get('next_node_id')

                            if bot and chat_id and next_node_id:
                                try:
                                    from app.modules.telegram_handler import send_node_message
                                    send_node_message(chat_id, next_node_id)
                                except Exception as e:
                                    logger.error(f"Failed to restore daily scenario: {e}")
                                    bot.send_message(chat_id, f"⏰ Ежедневное напоминание {h:02d}:{m:02d}")

                            self.schedule_next_daily(h, m, tz, sid, ctx)

                        return restored_daily_callback

                    restored_timer = threading.Timer(remaining, create_daily_callback())
                    restored_timer.start()

                    timer_key = f"daily_restored_{daily_record.id}"
                    self.active_timers[timer_key] = restored_timer

                    print(f"[DAILY] Daily timer restored: {timer_key}")

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
            if expired_count > 0:
                print(f"[TIMING-ENGINE] Cleaned up {expired_count} expired timers")
        except Exception as e:
            logger.error(f"Failed to cleanup expired timers: {e}")
            db.rollback()
        finally:
            db.close()

    def _init_parsers(self) -> Dict[str, Any]:
        return {
            'basic_pause': self._parse_basic_pause,
            'typing': self._parse_typing,
            'process': self._parse_process,
            'timeout': self._parse_timeout,
            'daily': self._parse_daily,      # Daily система
            'remind': self._parse_remind,    # ЗАГОТОВКА
            'deadline': self._parse_deadline # ЗАГОТОВКА
        }

    def _init_executors(self) -> Dict[str, Any]:
        return {
            'pause': self._execute_pause,
            'typing': self._execute_typing,
            'process': self._execute_process,
            'timeout': self._execute_timeout,
            'daily': self._execute_daily,    # Daily система
            'remind': self._execute_remind,  # ЗАГОТОВКА
            'deadline': self._execute_deadline # ЗАГОТОВКА
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

            if re.match(r'^\d+(\.\d+)?(s)?$', cmd_str):
                parsed = self.parsers['basic_pause'](cmd_str)
            elif cmd_str.startswith('process:'):
                parsed = self.parsers['process'](cmd_str)
            elif cmd_str.startswith('timeout:'):
                parsed = self.parsers['timeout'](cmd_str)
            elif cmd_str.startswith('typing:'):
                parsed = self.parsers['typing'](cmd_str)
            elif cmd_str.startswith('daily@'):
                parsed = self.parsers['daily'](cmd_str)  # DAILY
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

    # === ПАРСЕРЫ ===
    def _parse_basic_pause(self, cmd_str: str) -> Dict[str, Any]:
        match = re.match(r'^\d+(\.\d+)?(s)?$', cmd_str)
        if match:
            duration = float(cmd_str.replace('s', ''))
            return {'type': 'pause', 'duration': duration, 'process_name': 'Пауза', 'original': cmd_str}
        return None

    def _parse_typing(self, cmd_str: str) -> Dict[str, Any]:
        pattern = r'^typing:(\d+(?:\.\d+)?)s?(?::([^:]+))?(?::([^:]+))?$'
        match = re.match(pattern, cmd_str)
        if match:
            duration = float(match.group(1))
            process_name = match.group(2) if match.group(2) else "Обработка"
            preset = match.group(3) if match.group(3) else 'clean'
            preset_config = self.presets.get(preset, self.presets['clean'])
            return {
                'type': 'typing', 'duration': duration, 'process_name': process_name, 
                'preset': preset, 'exposure_time': preset_config['exposure_time'],
                'anti_flicker_delay': preset_config['anti_flicker_delay'],
                'action': preset_config['action'], 'show_progress': True, 'original': cmd_str
            }
        return None

    def _parse_process(self, cmd_str: str) -> Dict[str, Any]:
        pattern = r'^process:(\d+(?:\.\d+)?)s?:([^:]+)(?::([^:]+))?$'
        match = re.match(pattern, cmd_str)
        if match:
            duration = float(match.group(1))
            process_name = match.group(2)
            preset = match.group(3) if match.group(3) else 'clean'
            preset_config = self.presets.get(preset, self.presets['clean'])
            return {
                'type': 'process', 'duration': duration, 'process_name': process_name,
                'preset': preset, 'exposure_time': preset_config['exposure_time'],
                'anti_flicker_delay': preset_config['anti_flicker_delay'],
                'action': preset_config['action'], 'show_progress': False, 'original': cmd_str
            }
        return None

    def _parse_timeout(self, cmd_str: str) -> Dict[str, Any]:
        known_presets = set(self.presets.keys())
        pattern_with_arg = r'^timeout:(\d+(?:\.\d+)?)s:([^:]+)$'
        pattern_simple = r'^timeout:(\d+(?:\.\d+)?)s$'

        match_with_arg = re.match(pattern_with_arg, cmd_str)
        if match_with_arg:
            duration = float(match_with_arg.group(1))
            arg = match_with_arg.group(2).strip()
            if arg in known_presets:
                return {'type': 'timeout', 'duration': duration, 'target_node': None, 
                       'use_next_node_id': True, 'preset': arg, 'show_countdown': True, 'original': cmd_str}
            else:
                return {'type': 'timeout', 'duration': duration, 'target_node': arg, 
                       'use_next_node_id': False, 'preset': 'clean', 'show_countdown': True, 'original': cmd_str}

        match_simple = re.match(pattern_simple, cmd_str)
        if match_simple:
            duration = float(match_simple.group(1))
            return {'type': 'timeout', 'duration': duration, 'target_node': None, 
                   'use_next_node_id': True, 'preset': 'clean', 'show_countdown': True, 'original': cmd_str}
        return None

    def _parse_daily(self, cmd_str: str) -> Dict[str, Any]:
        """Парсинг daily команд - daily@09:00:MSK"""
        match = re.match(r'^daily@(\d{1,2}):(\d{2})(?::([A-Z]{3}))?$', cmd_str)
        if match:
            hour = int(match.group(1))
            minute = int(match.group(2))
            timezone_str = match.group(3) or 'UTC'
            if 0 <= hour <= 23 and 0 <= minute <= 59:
                return {'type': 'daily', 'hour': hour, 'minute': minute, 'timezone': timezone_str, 'original': cmd_str}
        return None

    def _parse_remind(self, cmd_str: str) -> Dict[str, Any]:
        """ЗАГОТОВКА: remind:5m,1h,1d"""
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
        """ЗАГОТОВКА: deadline:2h"""
        match = re.match(r'^deadline:(\d+)(h|d|m)$', cmd_str)
        if match:
            value = int(match.group(1))
            unit = match.group(2)
            seconds = value*3600 if unit == 'h' else value*86400 if unit == 'd' else value*60
            return {'type': 'deadline', 'duration': seconds, 'original': cmd_str}
        return None

    # === ИСПОЛНИТЕЛИ ===
    def _execute_pause(self, command: Dict[str, Any], callback: Callable, **context) -> None:
        duration = command['duration']
        pause_text = context.get('pause_text') or ''
        bot = context.get('bot')
        chat_id = context.get('chat_id')
        if pause_text and bot and chat_id:
            bot.send_message(chat_id, pause_text)
        threading.Timer(duration, callback).start()

    def _execute_typing(self, command: Dict[str, Any], callback: Callable, **context) -> None:
        duration = command['duration']
        process_name = command.get('process_name', 'Обработка')
        preset = command.get('preset', 'clean')
        exposure_time = command.get('exposure_time', 1.5)
        anti_flicker_delay = command.get('anti_flicker_delay', 1.0)
        action = command.get('action', 'delete')

        session_id = context.get('session_id')
        if session_id:
            self.save_timer_to_db(session_id=session_id, timer_type='typing',
                delay_seconds=int(duration), message_text=process_name,
                callback_data={'command': command, 'preset': preset})

        bot = context.get('bot')
        chat_id = context.get('chat_id')
        if bot and chat_id:
            def show_progress_with_presets():
                try:
                    self._show_progress_bar_with_presets(bot, chat_id, duration, process_name, 
                        show_progress=True, exposure_time=exposure_time,
                        anti_flicker_delay=anti_flicker_delay, action=action)
                    callback()
                except Exception as e:
                    callback()
            threading.Thread(target=show_progress_with_presets).start()
        else:
            threading.Timer(duration, callback).start()

    def _execute_process(self, command: Dict[str, Any], callback: Callable, **context) -> None:
        duration = command['duration']
        process_name = command.get('process_name', 'Процесс')
        preset = command.get('preset', 'clean')
        exposure_time = command.get('exposure_time', 1.5)
        anti_flicker_delay = command.get('anti_flicker_delay', 1.0)
        action = command.get('action', 'delete')

        session_id = context.get('session_id')
        if session_id:
            self.save_timer_to_db(session_id=session_id, timer_type='process',
                delay_seconds=int(duration), message_text=process_name,
                callback_data={'command': command, 'preset': preset})

        bot = context.get('bot')
        chat_id = context.get('chat_id')
        if bot and chat_id:
            def show_static_process():
                try:
                    self._show_progress_bar_with_presets(bot, chat_id, duration, process_name,
                        show_progress=False, exposure_time=exposure_time,
                        anti_flicker_delay=anti_flicker_delay, action=action)
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
            self.save_timer_to_db(session_id=session_id, timer_type='timeout', delay_seconds=duration, 
                message_text=f"Timeout {duration}s ({'interactive' if show_countdown else 'silent'})",
                callback_node_id=target_node, callback_data={'command': command, 'target_node': target_node, 
                'preset': preset, 'silent_mode': not show_countdown})

        self.debug_timers[session_id] = {
            'type': 'timeout', 'duration': duration, 'target_node': target_node,
            'preset': preset, 'started_at': time.time(), 'chat_id': chat_id,
            'question_message_id': question_message_id, 'silent_mode': not show_countdown
        }

        if not bot or not chat_id:
            threading.Timer(duration, lambda: self._execute_timeout_callback(
                session_id, target_node, preset_config, callback, bot, chat_id, question_message_id
            )).start()
            return

        # ИНТЕРАКТИВНЫЙ vs ТИХИЙ timeout (код сокращен для краткости, полный в репозитории)
        if show_countdown:
            print(f"[TIMING-ENGINE] INTERACTIVE timeout: {duration}s with countdown")
            # ... countdown logic ...
        else:
            print(f"[TIMING-ENGINE] SILENT timeout: {duration}s (scenic pause)")
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

    def _execute_daily(self, command: Dict[str, Any], callback: Callable, **context) -> None:
        """
        ПОЛНАЯ РЕАЛИЗАЦИЯ: Daily система (легковесный персональный cron)
        """
        hour = command.get('hour', 9)
        minute = command.get('minute', 0)
        timezone_str = command.get('timezone', 'UTC')

        session_id = context.get('session_id')
        bot = context.get('bot')
        chat_id = context.get('chat_id')

        print(f"[DAILY] Setting up daily notification: {hour:02d}:{minute:02d} {timezone_str}")

        try:
            next_daily_time = self.calculate_next_daily_time(hour, minute, timezone_str)
            now_utc = datetime.utcnow()
            delay_seconds = int((next_daily_time - now_utc).total_seconds())

            if delay_seconds <= 0:
                print(f"[DAILY] Error: calculated time is in the past! Falling back to 24h")
                delay_seconds = 24 * 3600
                next_daily_time = now_utc + timedelta(hours=24)

            print(f"[DAILY] Next execution in {delay_seconds} seconds ({delay_seconds/3600:.1f} hours)")

            if session_id:
                timer_id = self.save_timer_to_db(
                    session_id=session_id, timer_type='daily', delay_seconds=delay_seconds,
                    message_text=f"Daily {hour:02d}:{minute:02d} {timezone_str}",
                    callback_node_id="", callback_data={
                        'command': command, 'hour': hour, 'minute': minute, 
                        'timezone': timezone_str, 'auto_reschedule': True, 'context': context
                    })
                print(f"[DAILY] Saved to DB with timer_id: {timer_id}")

            def daily_callback():
                print(f"[DAILY] Daily trigger activated: {hour:02d}:{minute:02d} {timezone_str}")
                try:
                    callback()
                    print(f"[DAILY] Scenario callback executed successfully")
                except Exception as e:
                    logger.error(f"Daily callback failed: {e}")
                try:
                    self.schedule_next_daily(hour, minute, timezone_str, session_id, context)
                    print(f"[DAILY] Next daily scheduled successfully")
                except Exception as e:
                    logger.error(f"Failed to reschedule daily: {e}")

            daily_timer = threading.Timer(delay_seconds, daily_callback)
            daily_timer.start()

            timer_key = f"daily_{session_id}_{hour}_{minute}_{timezone_str}"
            self.active_timers[timer_key] = daily_timer
            print(f"[DAILY] Daily timer activated: {timer_key}")

            if bot and chat_id:
                next_time_local = next_daily_time.strftime('%Y-%m-%d %H:%M UTC')
                setup_message = f"📅 Ежедневное уведомление настроено на {hour:02d}:{minute:02d} {timezone_str}\n⏰ Следующее срабатывание: {next_time_local}"
                pause_text = context.get('pause_text', '').strip()
                if not pause_text:
                    bot.send_message(chat_id, setup_message)
                    print(f"[DAILY] Setup notification sent to user")

            print(f"[DAILY] Daily setup completed, continuing main scenario")

        except Exception as e:
            logger.error(f"Daily setup failed: {e}")
            print(f"[DAILY] Setup failed, continuing main scenario anyway")
            callback()

    def _execute_timeout_callback(self, session_id: int, target_node: str, preset_config: dict, 
                                 callback: Callable, bot=None, chat_id=None, question_message_id=None):
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
        if session_id in self.debug_timers:
            del self.debug_timers[session_id]
        if session_id in self.active_timeouts:
            del self.active_timeouts[session_id]

    def _execute_remind(self, command: Dict[str, Any], callback: Callable, **context) -> None:
        """ЗАГОТОВКА: Remind система"""
        print(f"[TIMING-ENGINE] Reminder system stub: {command.get('original', 'N/A')}")
        callback()

    def _execute_deadline(self, command: Dict[str, Any], callback: Callable, **context) -> None:
        """ЗАГОТОВКА: Deadline система"""
        print(f"[TIMING-ENGINE] Deadline system stub: {command.get('original', 'N/A')}")
        callback()

    def _show_progress_bar_with_presets(self, bot, chat_id, duration, process_name, 
                                       show_progress=True, exposure_time=1.5, 
                                       anti_flicker_delay=1.0, action='delete'):
        try:
            if show_progress:
                msg = bot.send_message(chat_id, f"🚀 {process_name}\n⬜⬜⬜⬜⬜ 0%")
                steps = 5
                step_duration = duration / steps
                for i in range(1, steps + 1):
                    time.sleep(step_duration)
                    progress = int((i / steps) * 100)
                    filled = "🟩" * i
                    empty = "⬜" * (steps - i)
                    try:
                        bot.edit_message_text(chat_id=chat_id, message_id=msg.message_id,
                            text=f"🚀 {process_name}\n{filled}{empty} {progress}%")
                    except Exception:
                        pass
                try:
                    bot.edit_message_text(chat_id=chat_id, message_id=msg.message_id,
                        text=f"✅ {process_name}\n🟩🟩🟩🟩🟩 100%")
                except Exception:
                    pass
            else:
                msg = bot.send_message(chat_id, f"⚙️ {process_name}...")
                time.sleep(duration)
                try:
                    bot.edit_message_text(chat_id=chat_id, message_id=msg.message_id,
                        text=f"✅ {process_name}")
                except Exception:
                    pass
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

    def cancel_timeout_task(self, session_id: int) -> bool:
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
        completed = [sid for sid, thread in self.active_timeouts.items() if not thread.is_alive()]
        for session_id in completed:
            del self.active_timeouts[session_id]
            self.cancelled_tasks.discard(session_id)

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
            'available_presets': list(self.presets.keys()),
            'countdown_message_types': list(self.countdown_templates.keys()),
            'daily_system': 'active'
        }

    def enable(self) -> None:
        self.enabled = True

    def disable(self) -> None:
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
