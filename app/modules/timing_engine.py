# -*- coding: utf-8 -*-
"""
R-Bot Timing Engine - система временных механик для behavioral research

PHASE 1: Базовые паузы + прогресс-бар + Database Integration (ActiveTimer)
"""

import threading
import time
import re
import logging
from datetime import timedelta
from typing import Dict, Any, Callable, Optional, List

# Импорты моделей/БД
from app.modules.database.models import ActiveTimer, utc_now
# ← ИЗМЕНЕНО: используем SessionLocal вместо get_db
from app.modules.database import SessionLocal  # ← ИЗМЕНЕНО

# ИСПРАВЛЕНО: Feature flag включен по умолчанию для PHASE 1
TIMING_ENABLED = True

logger = logging.getLogger(__name__)

class TimingEngine:
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
        self.initialized = True
        
        logger.info(f"TimingEngine initialized. Enabled: {self.enabled}")
        print(f"[INIT] TimingEngine initialized with enabled={self.enabled}")
        
        if self.enabled:
            try:
                self.restore_timers_from_db()
                self.cleanup_expired_timers()
            except Exception as e:
                logger.error(f"Failed to restore/cleanup timers on init: {e}")
                print(f"[ERROR] Failed to restore/cleanup timers on init: {e}")
    
    @classmethod
    def get_instance(cls):
        return cls()
    
    # === DB helpers ===
    def _get_db_session(self):
        """Создать сессию БД через SessionLocal (единый способ по проекту)."""
        # ← ИЗМЕНЕНО: убрали get_db, используем SessionLocal()
        try:
            return SessionLocal()
        except Exception as e:
            logger.error(f"Failed to create DB session: {e}")
            print(f"[ERROR] Failed to create DB session: {e}")
            return None

    def save_timer_to_db(self, session_id: int, timer_type: str, 
                         delay_seconds: int, message_text: str = "",
                         callback_node_id: str = "", callback_data: dict = None):
        if callback_data is None:
            callback_data = {}
        db = self._get_db_session()
        if not db:
            print("[ERROR] No DB session available for saving timer")
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
            logger.info(f"Timer saved to DB: {timer_record.id}")
            return timer_record.id
        except Exception as e:
            logger.error(f"Failed to save timer to DB: {e}")
            print(f"[ERROR] Failed to save timer to DB: {e}")
            db.rollback()
            return None
        finally:
            db.close()

    def restore_timers_from_db(self):
        print("[INFO] Restoring timers from database...")
        db = self._get_db_session()
        if not db:
            print("[ERROR] No DB session available for restoring timers")
            return
        try:
            pending_timers = db.query(ActiveTimer).filter(
                ActiveTimer.status == 'pending',
                ActiveTimer.target_timestamp > utc_now()
            ).all()
            print(f"[INFO] Found {len(pending_timers)} pending timers to restore")
            logger.info(f"Found {len(pending_timers)} pending timers to restore")
            restored_count = 0
            for timer_record in pending_timers:
                remaining = (timer_record.target_timestamp - utc_now()).total_seconds()
                if remaining > 0:
                    timer_key = f"db_{timer_record.id}"
                    def create_timer_callback(timer_id=timer_record.id):
                        def callback():
                            self._execute_db_timer(timer_id)
                        return callback
                    thread_timer = threading.Timer(remaining, create_timer_callback())
                    thread_timer.start()
                    self.active_timers[timer_key] = thread_timer
                    restored_count += 1
                    print(f"[INFO] Restored timer {timer_record.id}: {remaining:.1f}s remaining")
                else:
                    print(f"[INFO] Timer {timer_record.id} expired - executing immediately")
                    self._execute_db_timer(timer_record.id)
            print(f"[SUCCESS] Restored {restored_count} timers from database")
        except Exception as e:
            logger.error(f"Failed to restore timers: {e}")
            print(f"[ERROR] Failed to restore timers: {e}")
        finally:
            db.close()

    def _execute_db_timer(self, timer_id: int):
        print(f"[INFO] Executing DB timer: {timer_id}")
        db = self._get_db_session()
        if not db:
            print(f"[ERROR] No DB session available for executing timer {timer_id}")
            return
        try:
            timer_record = db.query(ActiveTimer).filter(
                ActiveTimer.id == timer_id
            ).first()
            if not timer_record:
                logger.warning(f"Timer {timer_id} not found in DB")
                print(f"[WARNING] Timer {timer_id} not found in DB")
                return
            timer_record.status = 'executed'
            db.commit()
            print(f"[INFO] Executing DB timer {timer_id}: {timer_record.timer_type}")
            logger.info(f"Executing DB timer {timer_id}: {timer_record.timer_type}")
            # TODO: Здесь интегрировать с telegram_handler по timer_type
            if timer_record.timer_type == 'typing':
                print(f"[INFO] Completed typing process: {timer_record.message_text}")
            elif timer_record.timer_type == 'delayed_message':
                print(f"[INFO] Should send delayed message: {timer_record.message_text}")
            elif timer_record.timer_type == 'timeout':
                print(f"[INFO] Timeout reached, navigate to: {timer_record.callback_node_id}")
            else:
                print(f"[INFO] Unknown timer type: {timer_record.timer_type}")
            timer_key = f"db_{timer_id}"
            if timer_key in self.active_timers:
                del self.active_timers[timer_key]
                print(f"[INFO] Removed timer {timer_id} from active timers")
        except Exception as e:
            logger.error(f"Failed to execute DB timer {timer_id}: {e}")
            print(f"[ERROR] Failed to execute DB timer {timer_id}: {e}")
            db.rollback()
        finally:
            db.close()

    def cleanup_expired_timers(self):
        print("[INFO] Cleaning up expired timers...")
        db = self._get_db_session()
        if not db:
            print("[ERROR] No DB session available for cleanup")
            return
        try:
            from sqlalchemy import and_  # локальный импорт, чтобы не плодить глобальные
            expired_count = db.query(ActiveTimer).filter(
                and_(
                    ActiveTimer.status == 'pending',
                    ActiveTimer.target_timestamp < utc_now()
                )
            ).update({'status': 'expired'})
            db.commit()
            print(f"[INFO] Marked {expired_count} timers as expired")
            logger.info(f"Marked {expired_count} timers as expired")
        except Exception as e:
            logger.error(f"Failed to cleanup expired timers: {e}")
            print(f"[ERROR] Failed to cleanup expired timers: {e}")
            db.rollback()
        finally:
            db.close()
    
    # === Парсеры/исполнители ===
    def _init_parsers(self) -> Dict[str, Any]:
        return {
            'basic_pause': self._parse_basic_pause,
            'typing': self._parse_typing,
            'daily': self._parse_daily,
            'remind': self._parse_remind,
            'deadline': self._parse_deadline,
            'timeout': self._parse_timeout
        }
    
    def _init_executors(self) -> Dict[str, Any]:
        return {
            'pause': self._execute_pause,
            'typing': self._execute_typing,
            'daily': self._execute_daily,
            'remind': self._execute_remind,
            'deadline': self._execute_deadline,
            'timeout': self._execute_timeout
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
            if re.match(r'^\d+(\.\d+)?(s)?$', cmd_str):
                parsed = self.parsers['basic_pause'](cmd_str)
            elif cmd_str.startswith('typing:'):
                parsed = self.parsers['typing'](cmd_str)
            elif cmd_str.startswith('daily@'):
                parsed = self.parsers['daily'](cmd_str)
            elif cmd_str.startswith('remind:'):
                parsed = self.parsers['remind'](cmd_str)
            elif cmd_str.startswith('deadline:'):
                parsed = self.parsers['deadline'](cmd_str)
            elif cmd_str.startswith('timeout:'):
                parsed = self.parsers['timeout'](cmd_str)
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
    
    # --- DSL парсеры ---
    def _parse_basic_pause(self, cmd_str: str) -> Dict[str, Any]:
        match = re.match(r'^\d+(\.\d+)?(s)?$', cmd_str)
        if match:
            # Правка: match.group(1) это дробная часть; берем всю строку без 's'
            duration = float(cmd_str.replace('s', ''))
            return {'type': 'pause', 'duration': duration, 'process_name': 'Пауза', 'original': cmd_str}
        return None
    
    def _parse_typing(self, cmd_str: str) -> Dict[str, Any]:
        m = re.match(r'^typing:(\d+(?:\.\d+)?)s?(?::(.+))?$', cmd_str)
        if m:
            duration = float(m.group(1))
            process_name = m.group(2) if m.group(2) else "Обработка"
            return {'type': 'typing', 'duration': duration, 'process_name': process_name, 'original': cmd_str}
        return None
    
    def _parse_daily(self, cmd_str: str) -> Dict[str, Any]:
        m = re.match(r'^daily@(\d{2}):(\d{2})([A-Z]{3})?$', cmd_str)
        if m:
            hour = int(m.group(1)); minute = int(m.group(2)); tz = m.group(3) or 'UTC'
            return {'type': 'daily', 'hour': hour, 'minute': minute, 'timezone': tz, 'original': cmd_str}
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
    
    def _parse_timeout(self, cmd_str: str) -> Dict[str, Any]:
        m = re.match(r'^timeout:(\d+)(s|m)$', cmd_str)
        if m:
            v = int(m.group(1)); u = m.group(2)
            sec = v if u == 's' else v*60
            return {'type': 'timeout', 'duration': sec, 'original': cmd_str}
        return None
    
    # --- Исполнители ---
    def _execute_pause(self, command: Dict[str, Any], callback: Callable, **context) -> None:
        duration = command['duration']
        pause_text = context.get('pause_text') or ''
        bot = context.get('bot'); chat_id = context.get('chat_id')
        print(f"[INFO] TimingEngine: Executing simple pause: {duration}s")
        if pause_text and bot and chat_id:
            bot.send_message(chat_id, pause_text)
            print(f"[INFO] Sent pause text: {pause_text}")
        timer = threading.Timer(duration, callback)
        timer.start()

    def _execute_typing(self, command: Dict[str, Any], callback: Callable, **context) -> None:
        duration = command['duration']
        process_name = command.get('process_name', 'Обработка')
        print(f"[INFO] TimingEngine: Executing progress bar: {duration}s ({process_name})")
        session_id = context.get('session_id')
        if session_id:
            timer_id = self.save_timer_to_db(
                session_id=session_id,
                timer_type='typing',
                delay_seconds=int(duration),
                message_text=process_name,
                callback_data={'command': command}
            )
            if timer_id:
                print(f"[INFO] Typing timer saved to DB with ID: {timer_id}")
        else:
            print("[WARNING] No session_id in context - timer not saved to DB")
        bot = context.get('bot'); chat_id = context.get('chat_id')
        if bot and chat_id:
            def show_progress_and_callback():
                try:
                    self._show_progress_bar(bot, chat_id, duration, process_name)
                    callback()
                except Exception as e:
                    print(f"[ERROR] Progress bar failed: {e}")
                    callback()
            threading.Thread(target=show_progress_and_callback).start()
        else:
            threading.Timer(duration, callback).start()
    
    def _show_progress_bar(self, bot, chat_id, duration, process_name):
        try:
            msg = bot.send_message(chat_id, f"🚀 {process_name}\n⬜⬜⬜⬜⬜ 0%")
            steps = 5
            step_duration = duration / steps if steps else duration
            for i in range(1, steps + 1):
                time.sleep(step_duration)
                progress = int((i / steps) * 100)
                filled = "🟩" * i
                empty = "⬜" * (steps - i)
                try:
                    bot.edit_message_text(chat_id=chat_id, message_id=msg.message_id,
                                          text=f"🚀 {process_name}\n{filled}{empty} {progress}%")
                except Exception as e:
                    print(f"[WARNING] Failed to update progress bar: {e}")
            try:
                bot.edit_message_text(chat_id=chat_id, message_id=msg.message_id,
                                      text=f"✅ {process_name}\n🟩🟩🟩🟩🟩 100%")
            except Exception as e:
                print(f"[WARNING] Failed to show final progress: {e}")
        except Exception as e:
            print(f"[ERROR] Progress bar display failed: {e}")
            logger.error(f"Progress bar display failed: {e}")
    
    def process_timing(self, user_id: int, session_id: int, node_id: str, 
                       timing_config: str, callback: Callable, **context) -> None:
        if not self.enabled:
            print(f"[WARNING] TimingEngine disabled, executing callback immediately")
            callback(); return
        try:
            print(f"--- [TIMING] Обработка timing для узла {node_id}: {timing_config} ---")
            commands = self._parse_timing_dsl(timing_config)
            print(f"[INFO] TimingEngine: Parsed commands: {commands}")
            # Передаем session_id внутрь для сохранения таймеров
            enriched_context = dict(context)
            enriched_context['session_id'] = session_id
            self._execute_timing_commands(commands, callback, **enriched_context)
        except Exception as e:
            logger.error(f"TimingEngine error: {e}")
            print(f"[ERROR] TimingEngine error: {e}")
            callback()
    
    def _execute_daily(self, command: Dict[str, Any], callback: Callable, **context) -> None:
        print(f"[INFO] Scheduling daily task: {command['original']}")
        print(f"[WARNING] Daily scheduling not implemented yet - executing immediately")
        callback()
    
    def _execute_remind(self, command: Dict[str, Any], callback: Callable, **context) -> None:
        intervals = command['intervals']
        print(f"[INFO] Setting up reminders: {intervals}")
        print(f"[WARNING] Reminder system not implemented yet")
        callback()
    
    def _execute_deadline(self, command: Dict[str, Any], callback: Callable, **context) -> None:
        duration = command['duration']
        print(f"[INFO] Setting deadline: {duration}s")
        print(f"[WARNING] Deadline system not implemented yet")
        callback()
    
    def _execute_timeout(self, command: Dict[str, Any], callback: Callable, **context) -> None:
        duration = command['duration']
        print(f"[INFO] Setting timeout: {duration}s")
        print(f"[WARNING] Timeout system not implemented yet")
        callback()
    
    # Утилиты
    def cancel_user_timers(self, user_id: int) -> None:
        to_cancel = [key for key in self.active_timers.keys() if key.startswith(f"{user_id}_")]
        for key in to_cancel:
            timer = self.active_timers.pop(key)
            timer.cancel()
            logger.info(f"Cancelled timer: {key}")
            print(f"[INFO] Cancelled timer: {key}")
    
    def get_status(self) -> Dict[str, Any]:
        return {
            'enabled': self.enabled,
            'active_timers': len(self.active_timers),
            'available_parsers': list(self.parsers.keys()),
            'available_executors': list(self.executors.keys())
        }
    
    def enable(self) -> None:
        self.enabled = True
        print(f"[INFO] TimingEngine ENABLED")
        logger.info("TimingEngine ENABLED")
    
    def disable(self) -> None:
        self.enabled = False
        for timer in self.active_timers.values():
            timer.cancel()
        self.active_timers.clear()
        print(f"[INFO] TimingEngine DISABLED")
        logger.info("TimingEngine DISABLED")

# Глобальный экземпляр
timing_engine = TimingEngine()

# Публичные функции интеграции
def process_node_timing(user_id: int, session_id: int, node_id: str, 
                        timing_config: str, callback: Callable, **context) -> None:
    return timing_engine.process_timing(user_id, session_id, node_id, timing_config, callback, **context)

def enable_timing() -> None:
    global TIMING_ENABLED
    TIMING_ENABLED = True
    timing_engine.enable()
    status = timing_engine.get_status()
    if status['enabled']:
        print(f"🕐 Timing system activated: enabled")
    else:
        print(f"❌ Failed to activate timing system")

def disable_timing() -> None:
    global TIMING_ENABLED  
    TIMING_ENABLED = False
    timing_engine.disable()

def get_timing_status() -> Dict[str, Any]:
    return timing_engine.get_status()
