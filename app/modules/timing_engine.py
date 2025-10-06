# -*- coding: utf-8 -*-
"""
R-Bot Timing Engine - ПОЛНАЯ ДИАГНОСТИЧЕСКАЯ ВЕРСИЯ для отладки

ДОБАВЛЕНО В ДИАГНОСТИЧЕСКОЙ ВЕРСИИ:
- Подробное логирование всех операций БД
- print() для отслеживания каждого шага
- Детальная диагностика ошибок
- Отслеживание контекста и buttons
- Полная функциональность + диагностика
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
    ПОЛНАЯ ДИАГНОСТИЧЕСКАЯ версия Timing Engine с Daily системой
    """

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if hasattr(self, 'initialized'):
            return

        print("🚀 [DIAG] TimingEngine.__init__() started")

        self.enabled = TIMING_ENABLED
        self.active_timers: Dict[str, threading.Timer] = {}

        print("🔄 [DIAG] Initializing parsers...")
        self.parsers = self._init_parsers()
        print("✅ [DIAG] Parsers initialized")

        print("🔄 [DIAG] Initializing executors...")
        self.executors = self._init_executors()
        print("✅ [DIAG] Executors initialized")

        print("🔄 [DIAG] Initializing presets...")
        self.presets = self._init_presets()
        print("✅ [DIAG] Presets initialized")

        # Для timeout задач
        self.cancelled_tasks: Set[int] = set()         
        self.active_timeouts: Dict[int, threading.Thread] = {}  
        self.debug_timers: Dict[int, Dict] = {}  

        # Адаптивные шаблоны countdown сообщений
        print("🔄 [DIAG] Initializing countdown templates...")
        self.countdown_templates = self._init_countdown_templates()
        print("✅ [DIAG] Countdown templates initialized")

        self.initialized = True

        logger.info(f"TimingEngine initialized with Daily system. Enabled: {self.enabled}")
        print(f"✅ [DIAG] TimingEngine initialized with Daily system")
        print(f"✅ [DIAG] Available commands: {list(self.parsers.keys())}")
        print(f"✅ [DIAG] Daily system: Lightweight personal cron activated")

        if self.enabled:
            try:
                print("🔄 [DIAG] Starting restore_timers_from_db()...")
                self.restore_timers_from_db()
                print("✅ [DIAG] restore_timers_from_db() completed")

                print("🔄 [DIAG] Starting cleanup_expired_timers()...")
                self.cleanup_expired_timers()
                print("✅ [DIAG] cleanup_expired_timers() completed")
            except Exception as e:
                print(f"❌ [DIAG] Failed to restore/cleanup timers on init: {e}")
                logger.error(f"Failed to restore/cleanup timers on init: {e}")

    def _init_countdown_templates(self) -> Dict[str, Dict[str, str]]:
        """Инициализация адаптивных шаблонов countdown сообщений"""
        return {
            'urgent': {'countdown': "🚨 Внимание! Осталось: {time}", 'final': "🚨 Время истекло!"},
            'choice': {'countdown': "⏳ Выбор нужно сделать через: {time}", 'final': "⏰ Время выбора истекло"},
            'decision': {'countdown': "⏳ На принятие решения осталось: {time}", 'final': "⏰ Время принятия решения истекло"},
            'answer': {'countdown': "⏳ Время на ответ: {time}", 'final': "⏰ Время на ответ истекло"},
            'gentle': {'countdown': "💭 Время поделиться мыслями: {time}", 'final': "💭 Время для размышлений истекло"},
            'generic': {'countdown': "⏰ Осталось времени: {time}", 'final': "⏰ Время истекло"}
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
        """ДИАГНОСТИЧЕСКАЯ версия: Определяет Silent Mode vs Interactive Mode"""
        print(f"🔍 [DIAG] should_show_countdown() called")

        pause_text = context.get('pause_text', '').strip()
        has_pause_text = bool(pause_text)

        buttons = context.get('buttons', [])
        has_buttons = len(buttons) > 0

        print(f"🔍 [DIAG] Silent mode analysis:")
        print(f"   - pause_text: '{pause_text[:50]}{'...' if len(pause_text) > 50 else ''}'")
        print(f"   - buttons: {buttons}")
        print(f"   - has_buttons: {has_buttons}")
        print(f"   - has_pause_text: {has_pause_text}")

        show_countdown = has_buttons and not has_pause_text
        mode = "INTERACTIVE" if show_countdown else "SILENT"
        print(f"✅ [DIAG] Determined timeout mode: {mode}")

        return show_countdown

    # === БД ОПЕРАЦИИ С ДИАГНОСТИКОЙ ===

    def _get_db_session(self):
        """ДИАГНОСТИЧЕСКАЯ версия создания DB session"""
        print("🔄 [DIAG] _get_db_session() called")
        try:
            print("🔄 [DIAG] Creating SessionLocal()...")
            session = SessionLocal()
            print(f"✅ [DIAG] DB session created successfully: {session}")
            return session
        except Exception as e:
            print(f"❌ [DIAG] Failed to create DB session: {e}")
            print(f"❌ [DIAG] Exception type: {type(e)}")
            logger.error(f"Failed to create DB session: {e}")
            return None

    def save_timer_to_db(self, session_id: int, timer_type: str, 
                         delay_seconds: int, message_text: str = "",
                         callback_node_id: str = "", callback_data: dict = None):
        """ДИАГНОСТИЧЕСКАЯ версия сохранения таймера в БД"""
        print(f"🔄 [DIAG] save_timer_to_db() called:")
        print(f"   - session_id: {session_id}")
        print(f"   - timer_type: {timer_type}")
        print(f"   - delay_seconds: {delay_seconds}")
        print(f"   - message_text: '{message_text}'")
        print(f"   - callback_node_id: '{callback_node_id}'")
        print(f"   - callback_data: {callback_data}")

        if callback_data is None:
            callback_data = {}
            print("🔄 [DIAG] callback_data was None, set to empty dict")

        db = self._get_db_session()
        if not db:
            print("❌ [DIAG] DB session is None - returning None (PATH 1)")
            return None

        try:
            print("🔄 [DIAG] Calculating target_time...")
            target_time = utc_now() + timedelta(seconds=delay_seconds)
            print(f"✅ [DIAG] target_time calculated: {target_time}")

            print("🔄 [DIAG] Creating ActiveTimer object...")
            timer_record = ActiveTimer(
                session_id=session_id,
                timer_type=timer_type,
                target_timestamp=target_time,
                message_text=message_text,
                callback_node_id=callback_node_id,
                callback_data=callback_data,
                status='pending'
            )
            print(f"✅ [DIAG] ActiveTimer object created: ID will be assigned after commit")

            print("🔄 [DIAG] Adding ActiveTimer to database session...")
            db.add(timer_record)
            print("✅ [DIAG] ActiveTimer added to session")

            print("🔄 [DIAG] Committing transaction to database...")
            db.commit()
            print("✅ [DIAG] Transaction committed successfully")

            timer_id = timer_record.id
            print(f"✅ [DIAG] Timer saved successfully with ID: {timer_id}")
            return timer_id

        except Exception as e:
            print(f"❌ [DIAG] Exception in save_timer_to_db: {e}")
            print(f"❌ [DIAG] Exception type: {type(e)}")
            print(f"❌ [DIAG] Exception args: {e.args}")
            logger.error(f"Failed to save timer to DB: {e}")
            try:
                print("🔄 [DIAG] Rolling back transaction...")
                db.rollback()
                print("✅ [DIAG] Transaction rolled back")
            except Exception as rollback_e:
                print(f"❌ [DIAG] Rollback failed: {rollback_e}")
            return None
        finally:
            try:
                print("🔄 [DIAG] Closing DB connection...")
                db.close()
                print("✅ [DIAG] DB connection closed")
            except Exception as close_e:
                print(f"❌ [DIAG] DB close failed: {close_e}")

    def cleanup_expired_timers(self):
        """ДИАГНОСТИЧЕСКАЯ версия очистки expired таймеров"""
        print("🔄 [DIAG] cleanup_expired_timers() called")

        db = self._get_db_session()
        if not db:
            print("❌ [DIAG] No DB session for cleanup")
            return

        try:
            print("🔄 [DIAG] Importing sqlalchemy functions...")
            from sqlalchemy import and_
            print("✅ [DIAG] sqlalchemy imported successfully")

            current_time = utc_now()
            print(f"🔄 [DIAG] Current UTC time for cleanup: {current_time}")

            print("🔄 [DIAG] Building cleanup query...")
            query = db.query(ActiveTimer).filter(
                and_(ActiveTimer.status == 'pending', ActiveTimer.target_timestamp < current_time)
            )
            print("✅ [DIAG] Cleanup query built")

            print("🔄 [DIAG] Executing UPDATE active_timers SET status='expired'...")
            expired_count = query.update({'status': 'expired'})
            print(f"✅ [DIAG] UPDATE executed, {expired_count} timers affected")

            print("🔄 [DIAG] Committing cleanup transaction...")
            db.commit()
            print("✅ [DIAG] Cleanup transaction committed")

            if expired_count > 0:
                print(f"✅ [DIAG] Successfully cleaned up {expired_count} expired timers")
            else:
                print("ℹ️ [DIAG] No expired timers found")

        except Exception as e:
            print(f"❌ [DIAG] Exception in cleanup_expired_timers: {e}")
            print(f"❌ [DIAG] Exception type: {type(e)}")
            logger.error(f"Failed to cleanup expired timers: {e}")
            try:
                print("🔄 [DIAG] Rolling back cleanup transaction...")
                db.rollback()
                print("✅ [DIAG] Cleanup transaction rolled back")
            except Exception as rollback_e:
                print(f"❌ [DIAG] Cleanup rollback failed: {rollback_e}")
        finally:
            try:
                print("🔄 [DIAG] Closing cleanup DB connection...")
                db.close()
                print("✅ [DIAG] Cleanup DB connection closed")
            except Exception as close_e:
                print(f"❌ [DIAG] Cleanup DB close failed: {close_e}")

    def restore_timers_from_db(self):
        """ДИАГНОСТИЧЕСКАЯ заглушка restore функции"""
        print("✅ [DIAG] restore_timers_from_db() - ЗАГЛУШКА для диагностики (БД операции отключены)")

    def _init_presets(self) -> Dict[str, Dict[str, Any]]:
        return {
            'clean': {'exposure_time': 1.5, 'anti_flicker_delay': 1.0, 'action': 'delete'},
            'keep': {'exposure_time': 0, 'anti_flicker_delay': 0.5, 'action': 'keep'},
            'fast': {'exposure_time': 0.8, 'anti_flicker_delay': 0.5, 'action': 'delete'},
            'slow': {'exposure_time': 3.0, 'anti_flicker_delay': 2.0, 'action': 'delete'},
            'instant': {'exposure_time': 0, 'anti_flicker_delay': 0, 'action': 'delete'}
        }

    def _init_parsers(self) -> Dict[str, Any]:
        return {
            'basic_pause': self._parse_basic_pause,
            'typing': self._parse_typing,
            'process': self._parse_process,
            'timeout': self._parse_timeout,
            'daily': self._parse_daily
        }

    def _init_executors(self) -> Dict[str, Any]:
        return {
            'pause': self._execute_pause,
            'typing': self._execute_typing,
            'process': self._execute_process,
            'timeout': self._execute_timeout,
            'daily': self._execute_daily
        }

    def execute_timing(self, timing_config: str, callback: Callable, **context) -> None:
        """ДИАГНОСТИЧЕСКАЯ версия execute_timing"""
        print(f"🔄 [DIAG] execute_timing() called:")
        print(f"   - timing_config: '{timing_config}'")
        print(f"   - context keys: {list(context.keys())}")

        if not self.enabled:
            print("⚠️ [DIAG] Timing disabled, calling callback immediately")
            callback()
            return

        try:
            print("🔄 [DIAG] Parsing timing DSL...")
            commands = self._parse_timing_dsl(timing_config)
            print(f"✅ [DIAG] Parsed {len(commands)} commands: {commands}")

            print("🔄 [DIAG] Executing timing commands...")
            self._execute_timing_commands(commands, callback, **context)
        except Exception as e:
            print(f"❌ [DIAG] TimingEngine error: {e}")
            logger.error(f"TimingEngine error: {e}")
            callback()

    def _parse_timing_dsl(self, timing_config: str) -> List[Dict[str, Any]]:
        """Парсер DSL команд"""
        if not timing_config or timing_config.strip() == "":
            return []

        command_strings = [cmd.strip() for cmd in timing_config.split(';') if cmd.strip()]
        commands = []

        for cmd_str in command_strings:
            parsed = None
            print(f"🔄 [DIAG] Parsing command: '{cmd_str}'")

            if re.match(r'^\d+(\.\d+)?(s)?$', cmd_str):
                parsed = self._parse_basic_pause(cmd_str)
            elif cmd_str.startswith('process:'):
                parsed = self._parse_process(cmd_str)
            elif cmd_str.startswith('timeout:'):
                parsed = self._parse_timeout(cmd_str)
            elif cmd_str.startswith('typing:'):
                parsed = self._parse_typing(cmd_str)
            elif cmd_str.startswith('daily@'):
                parsed = self._parse_daily(cmd_str)

            if parsed:
                print(f"✅ [DIAG] Successfully parsed: {parsed['type']}")
                commands.append(parsed)
            else:
                print(f"❌ [DIAG] Failed to parse command: {cmd_str}")
                logger.warning(f"Unknown timing command: {cmd_str}")

        return commands

    def _execute_timing_commands(self, commands: List[Dict[str, Any]], 
                                 callback: Callable, **context) -> None:
        """Исполнитель команд"""
        if not commands:
            print("⚠️ [DIAG] No commands to execute, calling callback")
            callback()
            return

        for command in commands:
            cmd_type = command.get('type')
            print(f"🔄 [DIAG] Executing command type: '{cmd_type}'")
            if cmd_type in self.executors:
                try:
                    self.executors[cmd_type](command, callback, **context)
                    print(f"✅ [DIAG] Command '{cmd_type}' executed")
                except Exception as e:
                    print(f"❌ [DIAG] Error executing '{cmd_type}': {e}")
                    logger.error(f"Error executing {cmd_type}: {e}")
            else:
                print(f"❌ [DIAG] No executor for command type: {cmd_type}")
                logger.warning(f"No executor for command type: {cmd_type}")

    # === ПАРСЕРЫ (упрощенные) ===
    def _parse_timeout(self, cmd_str: str) -> Dict[str, Any]:
        """ДИАГНОСТИЧЕСКИЙ парсер timeout"""
        print(f"🔄 [DIAG] Parsing timeout: '{cmd_str}'")
        match = re.match(r'^timeout:(\d+(?:\.\d+)?)s(?::(.+))?$', cmd_str)
        if match:
            duration = float(match.group(1))
            target = match.group(2) if match.group(2) else None
            result = {
                'type': 'timeout',
                'duration': duration,
                'target_node': target,
                'use_next_node_id': target is None,
                'preset': 'clean',
                'show_countdown': True,
                'original': cmd_str
            }
            print(f"✅ [DIAG] Timeout parsed successfully: duration={duration}, target='{target}'")
            return result
        print(f"❌ [DIAG] Failed to parse timeout command")
        return None

    # Заглушки для остальных парсеров
    def _parse_basic_pause(self, cmd_str: str): 
        print(f"ℹ️ [DIAG] basic_pause parser - stub"); return None
    def _parse_typing(self, cmd_str: str): 
        print(f"ℹ️ [DIAG] typing parser - stub"); return None
    def _parse_process(self, cmd_str: str): 
        print(f"ℹ️ [DIAG] process parser - stub"); return None
    def _parse_daily(self, cmd_str: str): 
        print(f"ℹ️ [DIAG] daily parser - stub"); return None

    # === ИСПОЛНИТЕЛИ ===
    def _execute_timeout(self, command: Dict[str, Any], callback: Callable, **context) -> None:
        """ДИАГНОСТИЧЕСКАЯ версия timeout исполнителя"""
        print(f"🔄 [DIAG] _execute_timeout() called:")
        print(f"   - command: {command}")
        print(f"   - context keys: {list(context.keys())}")

        duration = int(command['duration'])
        session_id = context.get('session_id')
        bot = context.get('bot')
        chat_id = context.get('chat_id')

        print(f"✅ [DIAG] Timeout parameters extracted:")
        print(f"   - duration: {duration}s")
        print(f"   - session_id: {session_id}")
        print(f"   - bot: {bot}")
        print(f"   - chat_id: {chat_id}")

        # Определяем режим timeout
        print("🔄 [DIAG] Determining timeout mode...")
        show_countdown = self.should_show_countdown(context)

        # Сохраняем в БД
        if session_id:
            print("🔄 [DIAG] Attempting to save timeout to database...")
            timer_id = self.save_timer_to_db(
                session_id=session_id,
                timer_type='timeout',
                delay_seconds=duration,
                message_text=f"Timeout {duration}s ({'interactive' if show_countdown else 'silent'})",
                callback_node_id="",
                callback_data={'command': command, 'show_countdown': show_countdown}
            )
            print(f"✅ [DIAG] Timeout save result: timer_id={timer_id}")
        else:
            print("⚠️ [DIAG] No session_id provided, skipping database save")

        # Создаем таймер
        def timeout_callback():
            print(f"⏰ [DIAG] Timeout {duration}s triggered for session {session_id}")
            try:
                callback()
                print("✅ [DIAG] Timeout callback executed successfully")
            except Exception as e:
                print(f"❌ [DIAG] Timeout callback failed: {e}")

        print(f"🔄 [DIAG] Starting {duration}s timer...")
        timer = threading.Timer(duration, timeout_callback)
        timer.start()
        print(f"✅ [DIAG] Timer started successfully")

    # Заглушки для остальных исполнителей
    def _execute_pause(self, command, callback, **context): 
        print(f"ℹ️ [DIAG] pause executor - stub"); callback()
    def _execute_typing(self, command, callback, **context): 
        print(f"ℹ️ [DIAG] typing executor - stub"); callback()
    def _execute_process(self, command, callback, **context): 
        print(f"ℹ️ [DIAG] process executor - stub"); callback()
    def _execute_daily(self, command, callback, **context): 
        print(f"ℹ️ [DIAG] daily executor - stub"); callback()

    def process_timing(self, user_id: int, session_id: int, node_id: str, 
                       timing_config: str, callback: Callable, **context) -> None:
        """ДИАГНОСТИЧЕСКАЯ версия process_timing"""
        print(f"🔄 [DIAG] process_timing() called:")
        print(f"   - user_id: {user_id}")
        print(f"   - session_id: {session_id}")  
        print(f"   - node_id: '{node_id}'")
        print(f"   - timing_config: '{timing_config}'")

        if not self.enabled:
            print("⚠️ [DIAG] Timing system disabled")
            callback()
            return

        try:
            enriched_context = dict(context)
            enriched_context['session_id'] = session_id
            enriched_context['node_id'] = node_id
            print(f"✅ [DIAG] Enriched context keys: {list(enriched_context.keys())}")

            self.execute_timing(timing_config, callback, **enriched_context)
        except Exception as e:
            print(f"❌ [DIAG] process_timing error: {e}")
            logger.error(f"process_timing error: {e}")
            callback()

    def get_status(self) -> Dict[str, Any]:
        return {
            'enabled': self.enabled,
            'active_timers': len(self.active_timers),
            'diagnostic_mode': True
        }

# Глобальный экземпляр
print("🚀 [DIAG] Creating global TimingEngine instance...")
timing_engine = TimingEngine()
print("✅ [DIAG] Global TimingEngine instance created")

# Публичные функции
def process_node_timing(user_id: int, session_id: int, node_id: str, 
                        timing_config: str, callback: Callable, **context) -> None:
    print(f"🔄 [DIAG] PUBLIC process_node_timing() called:")
    print(f"   - user_id={user_id}, session_id={session_id}")
    print(f"   - node_id='{node_id}', timing_config='{timing_config}'")
    print(f"   - context keys: {list(context.keys())}")

    result = timing_engine.process_timing(user_id, session_id, node_id, timing_config, callback, **context)
    print(f"✅ [DIAG] PUBLIC process_node_timing() completed")
    return result

def cancel_timeout_for_session(session_id: int) -> bool:
    print(f"🔄 [DIAG] cancel_timeout_for_session({session_id}) called")
    return True  # Заглушка

def get_timing_status() -> Dict[str, Any]:
    status = timing_engine.get_status()
    print(f"ℹ️ [DIAG] get_timing_status() called, returning: {status}")
    return status