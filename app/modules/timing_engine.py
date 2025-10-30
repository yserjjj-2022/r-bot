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
30.10.2025 - РЕФАКТОРИНГ к примитивам: добавлена поддержка DynamicPause для typing/process
30.10.2025 - АКТИВИРОВАН progressbar режим для typing команд
30.10.2025 - ПАРСЕР typing теперь поддерживает сообщения с пробелами

DSL команды:
- timeout:15s:no_answer - интерактивный timeout с countdown (если есть кнопки)
- timeout:5s:slow - тихий timeout для драматургии (если есть pause_text)  
- typing:5s:Анализ ваших ответов...:clean - прогресс-бар 5s с preset clean (сообщение с пробелами)
- daily@09:00MSK - ежедневные уведомления (заготовка)
- remind:5m,1h,1d - система напоминаний (заготовка)  
- deadline:2h - дедлайны с предупреждениями (заготовка)
"""

import threading
import time
import re
import logging
from datetime import timedelta, datetime, date
from typing import Dict, Any, Callable, Optional, List, Set

from app.modules.database.models import ActiveTimer, utc_now
from app.modules.database import SessionLocal
from app.modules.timing_primitives.dynamic_pause import DynamicPause

TIMING_ENABLED = True
logger = logging.getLogger(__name__)

# === ВНИМАНИЕ: без отступа! Функции класса ниже объявляются внутри класса TimingEngine ===

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
        return {
            'urgent': {'countdown': "🚨 Внимание! Осталось: {time}", 'final': "🚨 Время истекло!"},
            'choice': {'countdown': "⏳ Выбор нужно сделать через: {time}", 'final': "⏰ Время выбора истекло"},
            'decision': {'countdown': "⏳ На принятие решения осталось: {time}", 'final': "⏰ Время принятия решения истекло"},
            'answer': {'countdown': "⏳ Время на ответ: {time}", 'final': "⏰ Время на ответ истекло"},
            'gentle': {'countdown': "💭 Время поделиться мыслями: {time}", 'final': "💭 Время для размышлений истекло"},
            'generic': {'countdown': "⏰ Осталось времени: {time}", 'final': "⏰ Время истекло"}
        }

    def format_countdown_time(self, seconds: int) -> str:
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
            'daily': self._parse_daily,
            'remind': self._parse_remind,
            'deadline': self._parse_deadline
        }

    def _init_executors(self) -> Dict[str, Any]:
        return {
            'pause': self._execute_pause,
            'typing': self._execute_typing,
            'process': self._execute_process,
            'timeout': self._execute_timeout,
            'daily': self._execute_daily,
            'remind': self._execute_remind,
            'deadline': self._execute_deadline
        }

    def _parse_basic_pause(self, cmd_str: str) -> Dict[str, Any]:
        m = re.match(r'^\d+(?:\.\d+)?s?$', cmd_str)
        if not m:
            return None
        duration = float(cmd_str.replace('s', ''))
        return {'type': 'pause', 'duration': duration, 'process_name': 'Пауза', 'original': cmd_str}

    def _parse_typing(self, cmd_str: str) -> Dict[str, Any]:
        """Парсинг typing команд с поддержкой сообщений с пробелами и опционального preset"""
        m = re.match(r'^typing:(\d+(?:\.\d+)?)s?(?::(.*))?$', cmd_str)
        if not m:
            return None
        duration = float(m.group(1))
        tail = m.group(2) or ''
        process_name = 'Обработка'
        preset = 'clean'
        if tail:
            if ':' in tail:
                process_name, preset = tail.split(':', 1)
            else:
                process_name = tail
            process_name = process_name.strip()
            preset = (preset or 'clean').strip()
        return {
            'type': 'typing', 'duration': duration, 'process_name': process_name, 'preset': preset,
            'exposure_time': self.presets.get(preset, self.presets['clean'])['exposure_time'],
            'anti_flicker_delay': self.presets.get(preset, self.presets['clean'])['anti_flicker_delay'],
            'action': self.presets.get(preset, self.presets['clean'])['action'],
            'show_progress': True, 'original': cmd_str
        }

    # далее остаётся остальной код класса TimingEngine (executors, helpers, public API)
