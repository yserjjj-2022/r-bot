# -*- coding: utf-8 -*-
"""
R-Bot Timing Engine - система временных механик для behavioral research

Модульная архитектура для поэтапной реализации сложных временных функций:
- PHASE 1: Базовые паузы, расписания, напоминания  
- PHASE 2: Timezone, условная логика, игровые механики
- PHASE 3: Продвинутая аналитика, групповая синхронизация
- PHASE 4: ML-оптимизация (опционально)

Автор: Sergey Ershov
Создано: 02.10.2025
Исправлено: 02.10.2025 - включен по умолчанию + логирование
"""

import threading
import time
import re
import logging
from datetime import datetime, timedelta
from typing import Dict, Any, Callable, Optional, List

# ИСПРАВЛЕНО: Feature flag включен по умолчанию для PHASE 1
TIMING_ENABLED = True  # ✅ ВКЛЮЧЕНО ПО УМОЛЧАНИЮ!

logger = logging.getLogger(__name__)

class TimingEngine:
    """
    Основной движок обработки временных механик R-Bot
    
    Поддерживает DSL синтаксис для описания сложных временных сценариев:
    - Простые паузы: "3", "1.5s", "typing:5s"
    - Расписания: "daily@09:00", "weekly@Mon:10:00"  
    - Напоминания: "remind:2h,6h,24h"
    - Дедлайны: "deadline:24h", "timeout:30s"
    - Комбинированные: "daily@09:00; remind:4h,8h; deadline:24h"
    """
    
    def __init__(self):
        self.enabled = TIMING_ENABLED
        self.active_timers: Dict[str, threading.Timer] = {}
        self.parsers = self._init_parsers()
        self.executors = self._init_executors()
        
        logger.info(f"TimingEngine initialized. Enabled: {self.enabled}")
        print(f"[INIT] TimingEngine initialized with enabled={self.enabled}")  # ✅ ДОБАВЛЕНО
    
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
    
    def process_timing(self, 
                      user_id: int, 
                      session_id: int, 
                      node_id: str, 
                      timing_config: str,
                      callback: Callable,
                      **context) -> None:
        """
        Основная функция обработки timing DSL
        
        Args:
            user_id: ID пользователя
            session_id: ID сессии  
            node_id: ID узла сценария
            timing_config: DSL строка (например "daily@09:00; remind:4h,8h")
            callback: Функция для вызова после timing события
            **context: Дополнительный контекст (переменные состояния)
        """
        if not self.enabled:
            # Если timing отключен - просто вызываем callback
            print(f"[WARNING] TimingEngine disabled, executing callback immediately")
            logger.info(f"TimingEngine disabled, executing callback immediately")
            callback()
            return
        
        try:
            print(f"--- [TIMING] Обработка timing для узла {node_id}: {timing_config} ---")  # ✅ ДОБАВЛЕНО
            
            # Парсим DSL строку
            commands = self._parse_timing_dsl(timing_config)
            print(f"[INFO] TimingEngine: Parsed commands: {commands}")  # ✅ ДОБАВЛЕНО
            
            # Выполняем команды
            self._execute_timing_commands(
                commands, user_id, session_id, node_id, callback, **context
            )
            
        except Exception as e:
            logger.error(f"TimingEngine error: {e}")
            print(f"[ERROR] TimingEngine error: {e}")  # ✅ ДОБАВЛЕНО
            # Graceful degradation - если timing не работает, просто продолжаем
            callback()
    
    def _parse_timing_dsl(self, timing_config: str) -> List[Dict[str, Any]]:
        """
        Парсинг DSL строки в структурированные команды
        
        Поддерживает:
        - Обратная совместимость: "3" -> {"type": "pause", "duration": 3}
        - Простые команды: "typing:5s" -> {"type": "typing", "duration": 5}
        - Комбинированные: "daily@09:00; remind:4h,8h" -> [{"type": "daily"...}, {"type": "remind"...}]
        """
        if not timing_config or timing_config.strip() == "":
            return []
        
        # Разделяем на отдельные команды (по точке с запятой)
        command_strings = [cmd.strip() for cmd in timing_config.split(';') if cmd.strip()]
        commands = []
        
        for cmd_str in command_strings:
            # Пробуем каждый парсер по очереди
            parsed = None
            
            # 1. Обратная совместимость: простые числа
            if re.match(r'^\d+(\.\d+)?(s)?$', cmd_str):
                parsed = self.parsers['basic_pause'](cmd_str)
            
            # 2. Typing команды
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
                print(f"[WARNING] Unknown timing command: {cmd_str}")  # ✅ ДОБАВЛЕНО
        
        return commands
    
    def _execute_timing_commands(self, 
                                commands: List[Dict[str, Any]], 
                                user_id: int, 
                                session_id: int, 
                                node_id: str, 
                                callback: Callable,
                                **context) -> None:
        """Выполнение списка timing команд"""
        
        if not commands:
            print(f"[INFO] No timing commands to execute, calling callback immediately")
            callback()
            return
        
        # Для PHASE 1 выполняем команды последовательно
        # В PHASE 2-3 здесь будет более сложная логика координации
        
        for command in commands:
            cmd_type = command.get('type')
            
            if cmd_type in self.executors:
                print(f"[INFO] Executing command: {command}")  # ✅ ДОБАВЛЕНО
                self.executors[cmd_type](
                    command, user_id, session_id, node_id, callback, **context
                )
            else:
                logger.warning(f"No executor for command type: {cmd_type}")
                print(f"[WARNING] No executor for command type: {cmd_type}")
    
    # =================================================================
    # DSL ПАРСЕРЫ (PHASE 1)  
    # =================================================================
    
    def _parse_basic_pause(self, cmd_str: str) -> Dict[str, Any]:
        """Парсинг простых пауз: "3" или "1.5s" """
        match = re.match(r'^(\d+(?:\.\d+)?)s?$', cmd_str)
        if match:
            duration = float(match.group(1))
            return {
                'type': 'pause',
                'duration': duration,
                'original': cmd_str
            }
        return None
    
    def _parse_typing(self, cmd_str: str) -> Dict[str, Any]:
        """Парсинг typing команд: "typing:5s" """
        match = re.match(r'^typing:(\d+(?:\.\d+)?)s?$', cmd_str)
        if match:
            duration = float(match.group(1))
            return {
                'type': 'typing',
                'duration': duration,
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
                # Парсим интервал: "2h", "30m", "24h"
                time_match = re.match(r'^(\d+)(h|m|s)$', interval)
                if time_match:
                    value = int(time_match.group(1))
                    unit = time_match.group(2)
                    
                    # Конвертируем в секунды
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
            
            # Конвертируем в секунды
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
            
            # Конвертируем в секунды
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
    # ИСПОЛНИТЕЛИ КОМАНД (PHASE 1)
    # =================================================================
    
    def _execute_pause(self, command: Dict[str, Any], user_id: int, session_id: int, 
                      node_id: str, callback: Callable, **context) -> None:
        """Выполнение простой паузы"""
        duration = command['duration']
        print(f"[INFO] TimingEngine: Executing pause: {duration}s for user {user_id}")  # ✅ ИСПРАВЛЕНО
        logger.info(f"Executing pause: {duration}s for user {user_id}")
        
        # Создаем таймер для отложенного вызова callback
        timer = threading.Timer(duration, callback)
        timer.start()
        
        # Сохраняем таймер для возможной отмены
        timer_key = f"{user_id}_{node_id}_pause"
        self.active_timers[timer_key] = timer
    
    def _execute_typing(self, command: Dict[str, Any], user_id: int, session_id: int,
                    node_id: str, callback: Callable, **context) -> None:
        """Выполнение typing анимации"""
        duration = command['duration']
        print(f"[INFO] TimingEngine: Executing typing animation: {duration}s for user {user_id}")
        logger.info(f"Executing typing animation: {duration}s for user {user_id}")
        
        # ИСПРАВЛЕНО: ДОБАВЛЯЕМ РЕАЛЬНУЮ РЕАЛИЗАЦИЮ
        
        # Получаем chat_id из context
        chat_id = context.get('chat_id')
        bot = context.get('bot')  # Нужно передавать bot из telegram_handler
        
        def send_typing_action():
            """Отправляет typing action в Telegram"""
            if bot and chat_id:
                try:
                    bot.send_chat_action(chat_id, 'typing')
                    print(f"[TYPING] Sent typing action to chat {chat_id}")
                except Exception as e:
                    print(f"[ERROR] Failed to send typing action: {e}")
        
        def finish_typing():
            """Завершает typing анимацию и вызывает callback"""
            print(f"[INFO] TimingEngine: Typing animation completed for user {user_id}")
            callback()  # ← ЭТО ВАЖНО!
        
        # Отправляем typing action сразу
        send_typing_action()
        
        # Если анимация длинная, повторяем typing каждые 4 секунды  
        if duration > 4:
            def repeat_typing():
                remaining = duration
                while remaining > 4:
                    threading.Timer(4, send_typing_action).start()
                    remaining -= 4
            repeat_typing()
        
        # ГЛАВНОЕ: Запускаем основной таймер для завершения
        timer = threading.Timer(duration, finish_typing)
        timer.start()
        
        # Сохраняем timer для возможной отмены
        timer_key = f"{user_id}_{session_id}_{node_id}_typing"
        self.active_timers[timer_key] = timer
    
    def _execute_daily(self, command: Dict[str, Any], user_id: int, session_id: int,
                      node_id: str, callback: Callable, **context) -> None:
        """Выполнение daily расписания"""
        print(f"[INFO] Scheduling daily task: {command['original']} for user {user_id}")
        logger.info(f"Scheduling daily task: {command['original']} for user {user_id}")
        
        # TODO: PHASE 2 - интеграция с APScheduler
        # Пока просто логируем и вызываем callback
        print(f"[WARNING] Daily scheduling not implemented yet - executing immediately")
        logger.warning("Daily scheduling not implemented yet - executing immediately")
        callback()
    
    def _execute_remind(self, command: Dict[str, Any], user_id: int, session_id: int,
                       node_id: str, callback: Callable, **context) -> None:
        """Выполнение системы напоминаний"""
        intervals = command['intervals']
        print(f"[INFO] Setting up reminders: {intervals} for user {user_id}")
        logger.info(f"Setting up reminders: {intervals} for user {user_id}")
        
        # TODO: PHASE 2 - полная система напоминаний
        # Пока просто логируем
        print(f"[WARNING] Reminder system not implemented yet")
        logger.warning("Reminder system not implemented yet")
        callback()
    
    def _execute_deadline(self, command: Dict[str, Any], user_id: int, session_id: int,
                         node_id: str, callback: Callable, **context) -> None:
        """Выполнение дедлайна"""
        duration = command['duration']
        print(f"[INFO] Setting deadline: {duration}s for user {user_id}")
        logger.info(f"Setting deadline: {duration}s for user {user_id}")
        
        # TODO: PHASE 2 - система дедлайнов с базой данных
        # Пока просто вызываем callback
        print(f"[WARNING] Deadline system not implemented yet")
        logger.warning("Deadline system not implemented yet")
        callback()
    
    def _execute_timeout(self, command: Dict[str, Any], user_id: int, session_id: int,
                        node_id: str, callback: Callable, **context) -> None:
        """Выполнение timeout"""
        duration = command['duration']
        print(f"[INFO] Setting timeout: {duration}s for user {user_id}")
        logger.info(f"Setting timeout: {duration}s for user {user_id}")
        
        # TODO: PHASE 2 - система таймаутов с автопереходом
        print(f"[WARNING] Timeout system not implemented yet")
        logger.warning("Timeout system not implemented yet")
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
        """Включить timing систему (для поэтапного развертывания)"""
        self.enabled = True
        print(f"[INFO] TimingEngine ENABLED")  # ✅ ДОБАВЛЕНО
        logger.info("TimingEngine ENABLED")
    
    def disable(self) -> None:
        """Отключить timing систему"""
        self.enabled = False
        # Отменить все активные таймеры
        for timer in self.active_timers.values():
            timer.cancel()
        self.active_timers.clear()
        print(f"[INFO] TimingEngine DISABLED")  # ✅ ДОБАВЛЕНО
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
    
    # ✅ ИСПРАВЛЕНО: Проверяем что активация прошла успешно
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
    
    print("🧪 TESTING TIMING DSL PARSER:")
    
    test_cases = [
        "3",  # простая пауза  
        "typing:5s",  # анимация печати
        "daily@09:00MSK",  # ежедневное расписание
        "remind:2h,6h,24h",  # напоминания
        "deadline:24h",  # дедлайн
        "timeout:30s",  # таймаут
        "daily@09:00; remind:4h,8h; deadline:24h"  # комбинированная команда
    ]
    
    for test_case in test_cases:
        print(f"\nТест: '{test_case}'")
        try:
            commands = test_engine._parse_timing_dsl(test_case)
            for cmd in commands:
                print(f"  → {cmd}")
        except Exception as e:
            print(f"  ❌ Ошибка: {e}")
    
    print("\n✅ Базовая архитектура TimingEngine готова!")
    print("🚀 Следующий шаг: интеграция в telegram_handler.py")
