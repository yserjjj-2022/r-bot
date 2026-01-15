# -*- coding: utf-8 -*-
"""
R-Bot Timing Engine - публичные функции и реализация TimingEngine (с поддержкой БД-хранения таймеров)
"""

import threading
import time
import re
import logging
from datetime import timedelta
from typing import Dict, Any, Callable, Optional

from app.modules.timing_primitives.dynamic_pause import DynamicPause
# TemporalAction больше не нужен для таймаутов, так как они теперь в БД.
# Но если он нужен для чего-то другого, можно оставить. В данном случае убираем зависимость для timeout.
# from app.modules.timing_primitives.temporal_action import TemporalAction 

from app.modules.database.database import SessionLocal
from app.modules.database import crud, models

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
        
        # Ссылка на бота и обработчик событий (устанавливаются извне)
        self.bot = None
        self.event_handler = None
        
        # Запуск фонового потока проверки таймеров
        self._stop_event = threading.Event()
        self._check_thread = threading.Thread(target=self._background_worker, daemon=True)
        self._check_thread.start()
        
        self.initialized = True

    def register_bot(self, bot):
        """Регистрирует экземпляр бота для использования в фоновом потоке."""
        self.bot = bot

    def register_event_handler(self, handler: Callable[[Any, Any], None]):
        """
        Регистрирует функцию-обработчик срабатывания таймера.
        Сигнатура: handler(timer_obj, bot)
        """
        self.event_handler = handler

    # === Parsers ===
    def _init_parsers(self) -> Dict[str, Any]:
        return {
            'typing': self._parse_typing,
            'timeout': self._parse_timeout,
            'remind': self._parse_remind,
        }

    def _init_executors(self) -> Dict[str, Any]:
        return {
            'typing': self._execute_typing,
            'timeout': self._execute_timeout,
            'remind': self._execute_remind,
        }

    # -- typing -- (Остается без изменений, работает in-memory)
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
        return {'type': 'typing', 'duration': duration, 'process_name': name, 'preset': preset}

    def _execute_typing(self, command: Dict[str, Any], callback: Callable, **ctx):
        pause = DynamicPause(
            bot=ctx.get('bot'), chat_id=ctx.get('chat_id'),
            duration=float(command['duration']), fill_type='progressbar',
            message_text=command.get('process_name', 'Обработка')
        )
        pause.execute(on_complete_callback=callback)

    # -- timeout -- (Перевод на БД)
    def _parse_timeout(self, cmd_str: str) -> Dict[str, Any]:
        # timeout:15s или timeout:15s:target_node
        m = re.match(r'^timeout:(\d+(?:\.\d+)?)s?(?::([^:]+))?$', cmd_str)
        if not m:
            return None
        duration = float(m.group(1))
        target = (m.group(2) or '').strip() or None
        return {'type': 'timeout', 'duration': duration, 'target_node': target}

    def _execute_timeout(self, command: Dict[str, Any], callback: Callable, **ctx):
        session_id = ctx.get('session_id')
        if not session_id:
            logger.warning("Attempt to set timeout without session_id")
            return

        duration = command['duration']
        target_node = command['target_node']
        end_time = models.utc_now() + timedelta(seconds=duration)

        with SessionLocal() as db:
            # 1. Удаляем старые таймауты для этой сессии (логика "один активный таймаут")
            crud.delete_timers_by_session_and_type(db, session_id, 'timeout')
            
            # 2. Создаем новый
            crud.create_timer(
                db=db,
                session_id=session_id,
                timer_type='timeout',
                end_time=end_time,
                target_node_id=target_node,
                payload={}
            )
        # Обратите внимание: мы НЕ блокируем выполнение здесь и НЕ вызываем callback сразу.
        # Callback 'callback' из process_timing обычно продолжает цепочку СРАЗУ.
        # Но timeout - это отложенное событие.
        # В старой логике (TemporalAction) оно запускалось параллельно.
        # В новой логике мы просто записали в БД. Поток выполнения сценария здесь завершается (или продолжается, если это не блокирующий узел).
        # Обычно timeout ставится на узле Input/Menu и ждет.
        
    # -- remind -- (Новая команда)
    def _parse_remind(self, cmd_str: str) -> Dict[str, Any]:
        # remind:60s:Текст напоминания
        m = re.match(r'^remind:(\d+(?:\.\d+)?)s?:(.*)$', cmd_str)
        if not m:
            return None
        duration = float(m.group(1))
        text = (m.group(2) or '').strip()
        return {'type': 'remind', 'duration': duration, 'text': text}

    def _execute_remind(self, command: Dict[str, Any], callback: Callable, **ctx):
        session_id = ctx.get('session_id')
        if not session_id: return

        duration = command['duration']
        text = command['text']
        end_time = models.utc_now() + timedelta(seconds=duration)

        with SessionLocal() as db:
            crud.create_timer(
                db=db,
                session_id=session_id,
                timer_type='remind',
                end_time=end_time,
                target_node_id=None,
                payload={'text': text}
            )

    # === Background Worker ===
    def _background_worker(self):
        """Фоновый процесс проверки таймеров."""
        while not self._stop_event.is_set():
            try:
                self._process_due_timers()
            except Exception as e:
                logger.error(f"Error in timing background worker: {e}")
            time.sleep(2)  # Проверка каждые 2 секунды

    def _process_due_timers(self):
        if not self.bot or not self.event_handler:
            return

        with SessionLocal() as db:
            due_timers = crud.get_active_timers_by_time(db, check_time=models.utc_now())
            
            for timer in due_timers:
                try:
                    # Вызываем внешний обработчик
                    self.event_handler(timer, self.bot)
                    
                    # После успешной обработки удаляем таймер
                    crud.delete_timer(db, timer.id)
                except Exception as e:
                    logger.error(f"Failed to process timer {timer.id}: {e}")
                    # Можно добавить логику retry или пометить как ошибочный, но пока удаляем, чтобы не зациклиться
                    crud.delete_timer(db, timer.id)

    # === Public API ===
    def execute_timing(self, timing_config: str, callback: Callable, **context) -> None:
        if not (timing_config and isinstance(timing_config, str)):
            callback(); return
        
        # Если есть typing, выполняем его синхронно (через callback chain), потом остальные команды
        commands = [c.strip() for c in timing_config.split(';') if c.strip()]
        
        # Простая логика: ищем typing, если есть - выполняем первым.
        # Остальные (timeout, remind) - "стреляем и забываем" (в БД).
        
        typing_cmd = next((c for c in commands if c.startswith('typing:')), None)
        other_cmds = [c for c in commands if not c.startswith('typing:') and not re.match(r'^\d', c)] # исключаем простые числа (sleep)
        simple_sleep = next((c for c in commands if re.match(r'^\d+(?:\.\d+)?s?$', c)), None)

        def run_others():
            for cmd in other_cmds:
                if cmd.startswith('timeout:'):
                    p = self._parse_timeout(cmd)
                    if p: self._execute_timeout(p, lambda: None, **context)
                elif cmd.startswith('remind:'):
                    p = self._parse_remind(cmd)
                    if p: self._execute_remind(p, lambda: None, **context)
            
            # Если был простой sleep (без typing), выполним его тут (через threading.Timer для совместимости)
            # Но если был typing, sleep обычно не нужен.
            if simple_sleep and not typing_cmd:
                duration = float(simple_sleep.replace('s', ''))
                threading.Timer(duration, callback).start()
            else:
                # Если не было sleep, вызываем callback (переход дальше по сценарию)
                callback()

        if typing_cmd:
            parsed = self._parse_typing(typing_cmd)
            # Передаем run_others как callback, чтобы продолжить после typing
            self._execute_typing(parsed, run_others, **context)
        else:
            run_others()

    def process_timing(self, user_id: int, session_id: int, node_id: str, timing_config: str, callback: Callable, **context) -> None:
        context = dict(context)
        context.update({'session_id': session_id, 'user_id': user_id, 'chat_id': context.get('chat_id')})
        self.execute_timing(timing_config, callback, **context)

    # === Cancel API ===
    def cancel_timeout(self, session_id: int) -> bool:
        """Отмена таймаута через БД."""
        try:
            with SessionLocal() as db:
                crud.delete_timers_by_session_and_type(db, session_id, 'timeout')
            return True
        except Exception as e:
            logger.error(f"Error canceling timeout: {e}")
            return False

# Глобальный экземпляр
_timing_engine = TimingEngine()

def process_node_timing(user_id: int, session_id: int, node_id: str, timing_config: str, callback: Callable, **context) -> None:
    return _timing_engine.process_timing(user_id, session_id, node_id, timing_config, callback, **context)

def cancel_timeout_for_session(session_id: int) -> bool:
    return _timing_engine.cancel_timeout(session_id)

def init_timing_engine(bot, handler):
    """Инициализация engine с ботом и обработчиком событий"""
    _timing_engine.register_bot(bot)
    _timing_engine.register_event_handler(handler)
