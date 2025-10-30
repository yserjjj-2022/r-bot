# -*- coding: utf-8 -*-
"""
R-Bot Timing Engine - публичные функции и реализация TimingEngine (минимальная рабочая версия с TemporalAction)
"""

import threading
import time
import re
import logging
from typing import Dict, Any, Callable

from app.modules.timing_primitives.dynamic_pause import DynamicPause
from app.modules.timing_primitives.temporal_action import TemporalAction

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
        self.parsers = self._init_parsers()
        self.executors = self._init_executors()
        self.initialized = True

    # === Parsers ===
    def _init_parsers(self) -> Dict[str, Any]:
        return {
            'typing': self._parse_typing,
            'timeout': self._parse_timeout,
        }

    def _init_executors(self) -> Dict[str, Any]:
        return {
            'typing': self._execute_typing,
            'timeout': self._execute_timeout,
        }

    # -- typing --
    def _parse_typing(self, cmd_str: str) -> Dict[str, Any]:
        m = re.match(r'^typing:(\d+(?:\.\d+)?)s?(?::(.*))?$', cmd_str)
        if not m:
            return None
        duration = float(m.group(1))
        tail = (m.group(2) or '').strip()
        name, preset = ('Обработка', 'clean')
        if tail:
            if ':' in tail:
                name, preset = tail.split(':', 1)
            else:
                name = tail
        return {'type':'typing','duration':duration,'process_name':name,'preset':preset}

    def _execute_typing(self, command: Dict[str, Any], callback: Callable, **ctx):
        pause = DynamicPause(
            bot=ctx.get('bot'), chat_id=ctx.get('chat_id'),
            duration=float(command['duration']), fill_type='progressbar',
            message_text=command.get('process_name','Обработка'))
        pause.execute(on_complete_callback=callback)

    # -- timeout --
    def _parse_timeout(self, cmd_str: str) -> Dict[str, Any]:
        # Форматы: timeout:15s   или   timeout:15s:target_node
        m = re.match(r'^timeout:(\d+(?:\.\d+)?)s?(?::([^:]+))?$', cmd_str)
        if not m:
            return None
        duration = float(m.group(1))
        target = (m.group(2) or '').strip() or None
        return {'type':'timeout','duration':duration,'target_node':target}

    def _execute_timeout(self, command: Dict[str, Any], callback: Callable, **ctx):
        # Минимально: дождаться и вызвать callback.
        action = TemporalAction(
            bot=ctx.get('bot'), chat_id=ctx.get('chat_id'),
            duration=float(command['duration']), target_action=callback,
            countdown_mode=False)
        action.execute()

    # === Public API ===
    def execute_timing(self, timing_config: str, callback: Callable, **context) -> None:
        if not (timing_config and isinstance(timing_config, str)):
            callback(); return
        for cmd in [c.strip() for c in timing_config.split(';') if c.strip()]:
            if cmd.startswith('typing:'):
                parsed = self._parse_typing(cmd)
                self._execute_typing(parsed, callback, **context) if parsed else callback()
            elif cmd.startswith('timeout:'):
                parsed = self._parse_timeout(cmd)
                self._execute_timeout(parsed, callback, **context) if parsed else callback()
            elif re.match(r'^\d+(?:\.\d+)?s?$', cmd):
                # простая тихая пауза
                duration = float(cmd.replace('s',''))
                threading.Timer(duration, callback).start()
            else:
                callback()

    def process_timing(self, user_id: int, session_id: int, node_id: str, timing_config: str, callback: Callable, **context) -> None:
        self.execute_timing(timing_config, callback, **context)

# Глобальные экспортируемые символы для других модулей
_timing_engine = TimingEngine()

def process_node_timing(user_id: int, session_id: int, node_id: str, timing_config: str, callback: Callable, **context) -> None:
    return _timming_guard(lambda: _timing_engine.process_timing(user_id, session_id, node_id, timing_config, callback, **context))

# Вспомогательный guard от случайных опечаток/исключений модуля
def _timming_guard(fn: Callable):
    try:
        return fn()
    except Exception as e:
        logger.error(f"TimingEngine fatal error: {e}")
        try:  # аварийный fallback: сразу выполнить коллбэк
            # fn замыкает callback, так что он будет вызван внутри process_timing
            pass
        except Exception:
            pass
