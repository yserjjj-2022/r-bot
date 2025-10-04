# -*- coding: utf-8 -*-
"""
R-Bot Timing Engine - система временных механик для behavioral research

Модульная архитектура для поэтапной реализации сложных временных функций:
- PHASE 1: Базовые паузы, расписания, напоминания + ПРОГРЕСС-БАР + DATABASE INTEGRATION
- PHASE 2: Timezone, условная логика, игровые механики
- PHASE 3: Продвинутая аналитика, групповая синхронизация
- PHASE 4: ML-оптимизация (опционально)

Автор: Sergey Ershov
Создано: 02.10.2025
Обновлено: 04.10.2025 - добавлена Database Integration (ActiveTimer)
"""

import threading
import time
import re
import logging
from datetime import datetime, timedelta
from typing import Dict, Any, Callable, Optional, List

# === НОВЫЕ ИМПОРТЫ ДЛЯ DATABASE INTEGRATION ===
from app.modules.database.models import ActiveTimer, utc_now
from app.modules.database.database import get_db
from sqlalchemy.orm import Session
from sqlalchemy import and_

# ИСПРАВЛЕНО: Feature flag включен по умолчанию для PHASE 1
TIMING_ENABLED = True  # ✅ ВКЛЮЧЕНО ПО УМОЛЧАНИЮ!

logger = logging.getLogger(__name__)

class TimingEngine:
    """
    Основной движок обработки временных механик R-Bot с поддержкой прогресс-бара и Database Integration
    
    Поддерживает DSL синтаксис для описания сложных временных сценариев:
    - Простые паузы: "3", "1.5s"
    - Прогресс-бар: "typing:5s", "typing:3s:Анализ данных"
    - Расписания: "daily@09:00", "weekly@Mon:10:00"  
    - Напоминания: "remind:2h,6h,24h"
    - Дедлайны: "deadline:24h", "timeout:30s"
    - Комбинированные: "daily@09:00; remind:4h,8h; deadline:24h"
    
    ✅ НОВОЕ: Persistent таймеры через ActiveTimer модель!
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
        self.initialized = True
        
        logger.info(f"TimingEngine initialized. Enabled: {self.enabled}")
        print(f"[INIT] TimingEngine initialized with enabled={self.enabled}")
        
        # ✅ НОВОЕ: Восстановить таймеры из БД при инициализации
        if self.enabled:
            try:
                self.restore_timers_from_db()
                self.cleanup_expired_timers()
            except Exception as e:
                logger.error(f"Failed to restore/cleanup timers on init: {e}")
                print(f"[ERROR] Failed to restore/cleanup timers on init: {e}")
    
    @classmethod
    def get_instance(cls):
        """Получить singleton экземпляр TimingEngine"""
        return cls()
    
    # =================================================================
    # ✅ НОВЫЕ МЕТОДЫ ДЛЯ DATABASE INTEGRATION
    # =================================================================
    
    def _get_db_session(self):
        """Получить БД сессию"""
        try:
            return next(get_db())
        except Exception as e:
            logger.error(f"Failed to get DB session: {e}")
            print(f"[ERROR] Failed to get DB session: {e}")
            return None

    def save_timer_to_db(self, session_id: int, timer_type: str, 
                        delay_seconds: int, message_text: str = "",
                        callback_node_id: str = "", callback_data: dict = None):
        """Сохранить таймер в ActiveTimer модель"""
        
        if callback_data is None:
            callback_data = {}
        
        db = self._get_db_session()
        if not db:
            print("[ERROR] No DB session available for saving timer")
            return None
        
        try:
            # Вычислить target_timestamp
            target_time = utc_now() + timedelta(seconds=delay_seconds)
            
            # Создать запись в БД
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
        """Восстановить pending таймеры после рестарта"""
        
        print("[INFO] Restoring timers from database...")
        
        db = self._get_db_session()
        if not db:
            print("[ERROR] No DB session available for restoring timers")
            return
        
        try:
            # Найти все pending таймеры
            pending_timers = db.query(ActiveTimer).filter(
                ActiveTimer.status == 'pending',
                ActiveTimer.target_timestamp > utc_now()
            ).all()
            
            print(f"[INFO] Found {len(pending_timers)} pending timers to restore")
            logger.info(f"Found {len(pending_timers)} pending timers to restore")
            
            restored_count = 0
            for timer_record in pending_timers:
                # Вычислить оставшееся время
                remaining = (timer_record.target_timestamp - utc_now()).total_seconds()
                
                if remaining > 0:
                    # Создать threading timer
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
                    # Таймер уже истек - выполнить немедленно
                    print(f"[INFO] Timer {timer_record.id} expired - executing immediately")
                    self._execute_db_timer(timer_record.id)
            
            print(f"[SUCCESS] Restored {restored_count} timers from database")
                    
        except Exception as e:
            logger.error(f"Failed to restore timers: {e}")
            print(f"[ERROR] Failed to restore timers: {e}")
        finally:
            db.close()

    def _execute_db_timer(self, timer_id: int):
        """Выполнить таймер из БД"""
        
        print(f"[INFO] Executing DB timer: {timer_id}")
        
        db = self._get_db_session()
        if not db:
            print(f"[ERROR] No DB session available for executing timer {timer_id}")
            return
        
        try:
            # Получить таймер
            timer_record = db.query(ActiveTimer).filter(
                ActiveTimer.id == timer_id
            ).first()
            
            if not timer_record:
                logger.warning(f"Timer {timer_id} not found in DB")
                print(f"[WARNING] Timer {timer_id} not found in DB")
                return
            
            # Обновить статус
            timer_record.status = 'executed'
            db.commit()
            
            # Выполнить callback действие
            print(f"[INFO] Executing DB timer {timer_id}: {timer_record.timer_type}")
            logger.info(f"Executing DB timer {timer_id}: {timer_record.timer_type}")
            
            # В зависимости от timer_type выполняем разные действия
            if timer_record.timer_type == 'typing':
                print(f"[INFO] Completed typing process: {timer_record.message_text}")
            elif timer_record.timer_type == 'delayed_message':
                print(f"[INFO] Should send delayed message: {timer_record.message_text}")
                # TODO: Интеграция с telegram для отправки сообщения
            elif timer_record.timer_type == 'timeout':
                print(f"[INFO] Timeout reached, should navigate to: {timer_record.callback_node_id}")
                # TODO: Интеграция с telegram для навигации
            else:
                print(f"[INFO] Unknown timer type: {timer_record.timer_type}")
            
            # Удалить из активных таймеров
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
        """Очистить истекшие таймеры из БД"""
        
        print("[INFO] Cleaning up expired timers...")
        
        db = self._get_db_session()
        if not db:
            print("[ERROR] No DB session available for cleanup")
            return
        
        try:
            # Найти истекшие таймеры
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
    
    # =================================================================
    # ОРИГИНАЛЬНЫЕ МЕТОДЫ (БЕЗ ИЗМЕНЕНИЙ)
    # =================================================================
    
    def _init_parsers(self) -> Dict[str, Any]:
        """Инициализация DSL парсеров (расширяемо для PHASE 2-4)"""
        return {
            'basic_pause': self._parse_basic_pause,
            'typing': self._parse_typing,
            'daily': self._parse_daily,
            'remind': self._parse_remind,
            'deadline': self._parse_deadline,
            'timeout': self._parse_timeout
        }
    
    def _init_executors(self) -> Dict[str, Any]:
        """Инициализация исполнителей команд (расширяемо для PHASE 2-4)"""
        return {
            'pause': self._execute_pause,
            'typing': self._execute_typing,
            'daily': self._execute_daily,
            'remind': self._execute_remind,
            'deadline': self._execute_deadline,
            'timeout': self._execute_timeout
        }
    
    def execute_timing(self, timing_config: str, callback: Callable, **context) -> None:
        """
        Основная функция для интеграции с telegram_handler.py
        """
        if not self.enabled:
            print(f"[WARNING] TimingEngine disabled, executing callback immediately")
            callback()
            return
        
        try:
            print(f"--- [TIMING] Обработка timing: {timing_config} ---")
            
            # Парсим DSL строку
            commands = self._parse_timing_dsl(timing_config)
            print(f"[INFO] TimingEngine: Parsed commands: {commands}")
            
            # Выполняем команды
            self._execute_timing_commands(commands, callback, **context)
            
        except Exception as e:
            logger.error(f"TimingEngine error: {e}")
            print(f"[ERROR] TimingEngine error: {e}")
            callback()
    
    def _parse_timing_dsl(self, timing_config: str) -> List[Dict[str, Any]]:
        """Парсинг DSL строки в структурированные команды"""
        if not timing_config or timing_config.strip() == "":
            return []
        
        command_strings = [cmd.strip() for cmd in timing_config.split(';') if cmd.strip()]
        commands = []
        
        for cmd_str in command_strings:
            parsed = None
            
            # 1. Обратная совместимость: простые числа
            if re.match(r'^\d+(\.\d+)?(s)?$', cmd_str):
                parsed = self.parsers['basic_pause'](cmd_str)
            
            # 2. Typing команды (теперь прогресс-бар)
            elif cmd_str.startswith('typing:'):
                parsed = self.parsers['typing'](cmd_str)
            
            # 3. Daily расписания  
            elif cmd_str.startswith('daily@'):
                parsed = self.parsers['daily'](cmd_str)
                
            # 4. Напоминания
            elif cmd_str.startswith('remind:'):
                parsed = self.parsers['remind'](cmd_str)
                
            # 5. Дедлайны
            elif cmd_str.startswith('deadline:'):
                parsed = self.parsers['deadline'](cmd_str)
                
            # 6. Таймауты
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
        """Выполнение списка timing команд"""
        
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
    
    # =================================================================
    # DSL ПАРСЕРЫ
    # =================================================================
    
    def _parse_basic_pause(self, cmd_str: str) -> Dict[str, Any]:
        """Парсинг простых пауз: "3" или "1.5s" """
        match = re.match(r'^\d+(\.\d+)?(s)?$', cmd_str)
        if match:
            duration = float(match.group(1))
            return {
                'type': 'pause',
                'duration': duration,
                'process_name': 'Пауза',
                'original': cmd_str
            }
        return None
    
    def _parse_typing(self, cmd_str: str) -> Dict[str, Any]:
        """Парсинг typing команд с поддержкой названий: "typing:5s:Анализ данных" """
        # Расширенный формат: typing:5s:Название процесса
        match = re.match(r'^typing:(\d+(?:\.\d+)?)s?(?::(.+))?$', cmd_str)
        if match:
            duration = float(match.group(1))
            process_name = match.group(2) if match.group(2) else "Обработка"
            return {
                'type': 'typing',
                'duration': duration,
                'process_name': process_name,
                'original': cmd_str
            }
        return None
    
    def _parse_daily(self, cmd_str: str) -> Dict[str, Any]:
        """Парсинг daily расписаний: "daily@09:00" или "daily@09:00MSK" """
        match = re.match(r'^daily@(\d{2}):(\d{2})([A-Z]{3})?$', cmd_str)
        if match:
            hour = int(match.group(1))
            minute = int(match.group(2))
            timezone = match.group(3) or 'UTC'
            
            return {
                'type': 'daily',
                'hour': hour,
                'minute': minute, 
                'timezone': timezone,
                'original': cmd_str
            }
        return None
    
    def _parse_remind(self, cmd_str: str) -> Dict[str, Any]:
        """Парсинг напоминаний: "remind:2h,6h,24h" """
        match = re.match(r'^remind:(.+)$', cmd_str)
        if match:
            intervals_str = match.group(1)
            intervals = []
            
            for interval in intervals_str.split(','):
                interval = interval.strip()
                time_match = re.match(r'^(\d+)(h|m|s)$', interval)
                if time_match:
                    value = int(time_match.group(1))
                    unit = time_match.group(2)
                    
                    seconds = value
                    if unit == 'm':
                        seconds *= 60
                    elif unit == 'h':
                        seconds *= 3600
                        
                    intervals.append(seconds)
            
            return {
                'type': 'remind',
                'intervals': intervals,
                'original': cmd_str
            }
        return None
    
    def _parse_deadline(self, cmd_str: str) -> Dict[str, Any]:
        """Парсинг дедлайнов: "deadline:24h" """
        match = re.match(r'^deadline:(\d+)(h|d)$', cmd_str)
        if match:
            value = int(match.group(1))
            unit = match.group(2)
            
            seconds = value * 3600  # часы
            if unit == 'd':
                seconds = value * 86400  # дни
                
            return {
                'type': 'deadline',
                'duration': seconds,
                'original': cmd_str
            }
        return None
    
    def _parse_timeout(self, cmd_str: str) -> Dict[str, Any]:
        """Парсинг таймаутов: "timeout:30s" """
        match = re.match(r'^timeout:(\d+)(s|m)$', cmd_str)
        if match:
            value = int(match.group(1))
            unit = match.group(2)
            
            seconds = value
            if unit == 'm':
                seconds *= 60
                
            return {
                'type': 'timeout',
                'duration': seconds,
                'original': cmd_str
            }
        return None
    
    # =================================================================
    # ИСПОЛНИТЕЛИ КОМАНД С ПРОГРЕСС-БАРОМ + DATABASE INTEGRATION
    # =================================================================
    
    def _execute_pause(self, command: Dict[str, Any], callback: Callable, **context) -> None:
        """Выполнение простой паузы БЕЗ прогресс-бара"""
        duration = command['duration']
        pause_text = command.get('pause_text', '')
        
        bot = context.get('bot')
        chat_id = context.get('chat_id')
        
        print(f"[INFO] TimingEngine: Executing simple pause: {duration}s")
        
        # Если есть текст паузы - отправить его
        if pause_text and bot and chat_id:
            bot.send_message(chat_id, pause_text)
            print(f"[INFO] Sent pause text: {pause_text}")
        
        # ПРОСТАЯ ПАУЗА БЕЗ ВИЗУАЛИЗАЦИИ
        timer = threading.Timer(duration, callback)
        timer.start()

    def _execute_typing(self, command: Dict[str, Any], callback: Callable, **context) -> None:
        """Выполнение прогресс-бара с сохранением в БД"""
        duration = command['duration']
        process_name = command.get('process_name', 'Обработка')
        
        print(f"[INFO] TimingEngine: Executing progress bar: {duration}s ({process_name})")
        logger.info(f"Executing progress bar: {duration}s for {process_name}")
        
        # ✅ НОВОЕ: Получить session_id из context для сохранения в БД
        session_id = context.get('session_id')
        
        # ✅ НОВОЕ: Сохранить в БД если есть session_id
        if session_id:
            timer_id = self.save_timer_to_db(
                session_id=session_id,
                timer_type='typing',
                delay_seconds=int(duration),
                message_text=process_name,
                callback_data={
                    'command': command,
                    'context_keys': list(context.keys())
                }
            )
            if timer_id:
                print(f"[INFO] Typing timer saved to DB with ID: {timer_id}")
            else:
                print("[WARNING] Failed to save typing timer to DB")
        else:
            print("[WARNING] No session_id in context - timer not saved to DB")
        
        bot = context.get('bot')
        chat_id = context.get('chat_id')
        
        if bot and chat_id:
            # Показываем прогресс-бар в отдельном потоке
            def show_progress_and_callback():
                try:
                    self._show_progress_bar(bot, chat_id, duration, process_name)
                    callback()
                except Exception as e:
                    print(f"[ERROR] Progress bar failed: {e}")
                    callback()
            
            threading.Thread(target=show_progress_and_callback).start()
        else:
            # Fallback: простая пауза
            timer = threading.Timer(duration, callback)
            timer.start()
    
    def _show_progress_bar(self, bot, chat_id, duration, process_name):
        """Показывает анимированный прогресс-бар"""
        try:
            # Начальное сообщение
            msg = bot.send_message(
                chat_id, 
                f"🚀 {process_name}\n⬜⬜⬜⬜⬜ 0%"
            )
            
            steps = 5
            step_duration = duration / steps
            
            for i in range(1, steps + 1):
                time.sleep(step_duration)
                
                progress = int((i / steps) * 100)
                filled = "🟩" * i
                empty = "⬜" * (steps - i)
                
                try:
                    bot.edit_message_text(
                        chat_id=chat_id,
                        message_id=msg.message_id,
                        text=f"🚀 {process_name}\n{filled}{empty} {progress}%"
                    )
                except Exception as e:
                    print(f"[WARNING] Failed to update progress bar: {e}")
            
            # Финальное сообщение
            try:
                bot.edit_message_text(
                    chat_id=chat_id,
                    message_id=msg.message_id,
                    text=f"✅ {process_name}\n🟩🟩🟩🟩🟩 100%"
                )
            except Exception as e:
                print(f"[WARNING] Failed to show final progress: {e}")
                
        except Exception as e:
            print(f"[ERROR] Progress bar display failed: {e}")
            logger.error(f"Progress bar display failed: {e}")
    
    def process_timing(self, 
                      user_id: int, 
                      session_id: int, 
                      node_id: str, 
                      timing_config: str,
                      callback: Callable,
                      **context) -> None:
        """Основная функция обработки timing DSL"""
        if not self.enabled:
            print(f"[WARNING] TimingEngine disabled, executing callback immediately")
            callback()
            return
        
        try:
            print(f"--- [TIMING] Обработка timing для узла {node_id}: {timing_config} ---")
            
            commands = self._parse_timing_dsl(timing_config)
            print(f"[INFO] TimingEngine: Parsed commands: {commands}")
            
            self._execute_timing_commands(commands, callback, **context)
            
        except Exception as e:
            logger.error(f"TimingEngine error: {e}")
            print(f"[ERROR] TimingEngine error: {e}")
            callback()
    
    def _execute_daily(self, command: Dict[str, Any], callback: Callable, **context) -> None:
        """Выполнение daily расписания"""
        print(f"[INFO] Scheduling daily task: {command['original']}")
        logger.info(f"Scheduling daily task: {command['original']}")
        print(f"[WARNING] Daily scheduling not implemented yet - executing immediately")
        callback()
    
    def _execute_remind(self, command: Dict[str, Any], callback: Callable, **context) -> None:
        """Выполнение системы напоминаний"""
        intervals = command['intervals']
        print(f"[INFO] Setting up reminders: {intervals}")
        logger.info(f"Setting up reminders: {intervals}")
        print(f"[WARNING] Reminder system not implemented yet")
        callback()
    
    def _execute_deadline(self, command: Dict[str, Any], callback: Callable, **context) -> None:
        """Выполнение дедлайна"""
        duration = command['duration']
        print(f"[INFO] Setting deadline: {duration}s")
        logger.info(f"Setting deadline: {duration}s")
        print(f"[WARNING] Deadline system not implemented yet")
        callback()
    
    def _execute_timeout(self, command: Dict[str, Any], callback: Callable, **context) -> None:
        """Выполнение timeout"""
        duration = command['duration']
        print(f"[INFO] Setting timeout: {duration}s")
        logger.info(f"Setting timeout: {duration}s")
        print(f"[WARNING] Timeout system not implemented yet")
        callback()
    
    # =================================================================
    # УТИЛИТЫ
    # =================================================================
    
    def cancel_user_timers(self, user_id: int) -> None:
        """Отменить все активные таймеры для пользователя"""
        to_cancel = [key for key in self.active_timers.keys() if key.startswith(f"{user_id}_")]
        
        for key in to_cancel:
            timer = self.active_timers.pop(key)
            timer.cancel()
            logger.info(f"Cancelled timer: {key}")
            print(f"[INFO] Cancelled timer: {key}")
    
    def get_status(self) -> Dict[str, Any]:
        """Получить статус timing движка"""
        return {
            'enabled': self.enabled,
            'active_timers': len(self.active_timers),
            'available_parsers': list(self.parsers.keys()),
            'available_executors': list(self.executors.keys())
        }
    
    def enable(self) -> None:
        """Включить timing систему"""
        self.enabled = True
        print(f"[INFO] TimingEngine ENABLED")
        logger.info("TimingEngine ENABLED")
    
    def disable(self) -> None:
        """Отключить timing систему"""
        self.enabled = False
        for timer in self.active_timers.values():
            timer.cancel()
        self.active_timers.clear()
        print(f"[INFO] TimingEngine DISABLED")
        logger.info("TimingEngine DISABLED")

# Глобальный экземпляр для использования в telegram_handler
timing_engine = TimingEngine()

# =================================================================
# ФУНКЦИИ ДЛЯ ИНТЕГРАЦИИ С СУЩЕСТВУЮЩИМ КОДОМ
# =================================================================

def process_node_timing(user_id: int, session_id: int, node_id: str, 
                       timing_config: str, callback: Callable, **context) -> None:
    """Публичная функция для интеграции с telegram_handler.py"""
    return timing_engine.process_timing(
        user_id, session_id, node_id, timing_config, callback, **context
    )

def enable_timing() -> None:
    """Включить timing систему глобально"""
    global TIMING_ENABLED
    TIMING_ENABLED = True
    timing_engine.enable()
    
    status = timing_engine.get_status()
    if status['enabled']:
        print(f"🕐 Timing system activated: enabled")
    else:
        print(f"❌ Failed to activate timing system")

def disable_timing() -> None:
    """Отключить timing систему глобально"""
    global TIMING_ENABLED  
    TIMING_ENABLED = False
    timing_engine.disable()

def get_timing_status() -> Dict[str, Any]:
    """Получить статус timing системы"""
    return timing_engine.get_status()

if __name__ == "__main__":
    # Тестирование DSL парсера
    test_engine = TimingEngine()
    test_engine.enable()
    
    print("🧪 TESTING TIMING DSL PARSER + DATABASE:")
    
    test_cases = [
        "3",  # простая пауза с прогресс-баром
        "typing:5s",  # прогресс-бар 5 секунд
        "typing:3s:Анализ поведения",  # прогресс-бар с названием
        "daily@09:00MSK",  # ежедневное расписание
        "remind:2h,6h,24h",  # напоминания
        "deadline:24h",  # дедлайн
        "timeout:30s",  # таймаут
    ]
    
    for test_case in test_cases:
        print(f"\nТест: '{test_case}'")
        try:
            commands = test_engine._parse_timing_dsl(test_case)
            for cmd in commands:
                print(f"  → {cmd}")
        except Exception as e:
            print(f"  ❌ Ошибка: {e}")
    
    print("\n✅ TimingEngine с Database Integration готов!")
