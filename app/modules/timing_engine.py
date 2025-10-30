# -*- coding: utf-8 -*-
"""
R-Bot Timing Engine - публичные функции и реализация TimingEngine
"""

# Реальная логика расположена ниже в файле. Этот заголовок только для ориентира.

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
        self.presets = self._init_presets()
        self.cancelled_tasks: Set[int] = set()
        self.active_timeouts: Dict[int, threading.Thread] = {}
        self.debug_timers: Dict[int, Dict] = {}
        self.countdown_templates = self._init_countdown_templates()
        self.initialized = True

    # === Parsers / Executors (укорочено для фикса импорта) ===
    def _init_parsers(self) -> Dict[str, Any]:
        return {'typing': self._parse_typing}

    def _init_executors(self) -> Dict[str, Any]:
        return {'typing': self._execute_typing}

    def _init_presets(self) -> Dict[str, Dict[str, Any]]:
        return {'clean': {'exposure_time': 1.5, 'anti_flicker_delay': 1.0, 'action': 'delete'}}

    def _init_countdown_templates(self) -> Dict[str, Dict[str, str]]:
        return {'generic': {'countdown': '⏰ Осталось времени: {time}', 'final': '⏰ Время истекло'}}

    def _parse_typing(self, cmd_str: str) -> Dict[str, Any]:
        m = re.match(r'^typing:(\d+(?:\.\d+)?)s?(?::(.*))?$', cmd_str)
        if not m:
            return None
        duration = float(m.group(1))
        tail = (m.group(2) or '').strip()
        process_name = 'Обработка'
        preset = 'clean'
        if tail:
            if ':' in tail:
                process_name, preset = tail.split(':', 1)
            else:
                process_name = tail
        pc = self.presets.get(preset, self.presets['clean'])
        return {'type': 'typing', 'duration': duration, 'process_name': process_name, 'preset': preset,
                'exposure_time': pc['exposure_time'], 'anti_flicker_delay': pc['anti_flicker_delay'], 'action': pc['action']}

    def _execute_typing(self, command: Dict[str, Any], callback: Callable, **context) -> None:
        bot = context.get('bot'); chat_id = context.get('chat_id')
        duration = float(command.get('duration', 0)); name = command.get('process_name', 'Обработка')
        pause = DynamicPause(bot=bot, chat_id=chat_id, duration=duration, fill_type='progressbar', message_text=name)
        pause.execute(on_complete_callback=callback)

    def execute_timing(self, timing_config: str, callback: Callable, **context) -> None:
        commands = [timing_config] if isinstance(timing_config, str) else []
        for cmd in commands:
            if cmd.startswith('typing:'):
                self._execute_typing(self._parse_typing(cmd), callback, **context)
            else:
                callback()

    def process_timing(self, user_id: int, session_id: int, node_id: str, timing_config: str, callback: Callable, **context) -> None:
        enriched = dict(context); enriched['session_id'] = session_id; enriched['node_id'] = node_id
        self.execute_timing(timing_config, callback, **enriched)

# Глобальный экземпляр и ПУБЛИЧНЫЕ ФУНКЦИИ (они нужны для импорта из telegram_handler)
timing_engine = TimingEngine()

def process_node_timing(user_id: int, session_id: int, node_id: str, timing_config: str, callback: Callable, **context) -> None:
    return timing_engine.process_timing(user_id, session_id, node_id, timing_config, callback, **context)

def get_timing_status() -> Dict[str, Any]:
    return {'enabled': timing_engine.enabled}
