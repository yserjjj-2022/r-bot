# app/modules/timing_primitives/temporal_action.py
# ВЕРСИЯ 2.0 (31.10.2025): Расширенная поддержка triggermode + улучшенное логирование

import time
import threading
import logging

logger = logging.getLogger(__name__)

class TemporalAction:
    """
    Универсальный примитив для действий по истечении времени.
    Поддерживает два режима работы (triggermode):
    - 'beforeend': таймаут с обратным отсчетом и возможностью отмены
    - 'afterstart': простое напоминание через заданное время
    """
    
    def __init__(self, bot, chat_id: int, duration: float, target_action: callable,
                 triggermode: str = 'beforeend', countdown_mode: bool = None, 
                 countdown_text: str = "Осталось: {sec} сек"):
        """
        Инициализация TemporalAction.
        
        Args:
            bot: экземпляр Telegram бота
            chat_id: ID чата для отправки сообщений
            duration: длительность в секундах
            target_action: функция, которая будет вызвана по истечении времени
            triggermode: режим работы ('beforeend' или 'afterstart')
            countdown_mode: показывать ли обратный отсчет (если None, определяется по triggermode)
            countdown_text: шаблон текста для обратного отсчета
        """
        self.bot = bot
        self.chat_id = chat_id
        self.duration = int(float(duration or 0))
        self.target_action = target_action
        self.triggermode = triggermode
        self.countdown_text = countdown_text
        
        # Автоопределение countdown_mode по triggermode, если не задано явно
        if countdown_mode is None:
            self.countdown_mode = (triggermode == 'beforeend')
        else:
            self.countdown_mode = countdown_mode
            
        self._cancel_event = threading.Event()
        self._thread = None
        self._msg_id = None
        
        # Логирование создания объекта
        logger.info(f"[TemporalAction] Created: duration={self.duration}s, triggermode={self.triggermode}, countdown={self.countdown_mode}")

    def execute(self, on_complete_callback: callable = None):
        """Запуск в отдельном потоке."""
        logger.info(f"[TemporalAction] Starting execution: triggermode={self.triggermode}")
        self._thread = threading.Thread(target=self._run, args=(on_complete_callback,), daemon=True)
        self._thread.start()

    def cancel(self):
        """Мягкая отмена счётчика."""
        logger.info(f"[TemporalAction] Cancel requested: triggermode={self.triggermode}")
        self._cancel_event.set()

    # --- internal ---
    def _run(self, on_complete_callback):
        try:
            if self.triggermode == 'beforeend':
                self._run_beforeend_mode(on_complete_callback)
            elif self.triggermode == 'afterstart':
                self._run_afterstart_mode(on_complete_callback)
            else:
                logger.error(f"[TemporalAction] Unknown triggermode: {self.triggermode}")
                if on_complete_callback and callable(on_complete_callback):
                    on_complete_callback()
        except Exception as e:
            logger.error(f"[TemporalAction] Runtime error: {e}")

    def _run_beforeend_mode(self, on_complete_callback):
        """Режим 'beforeend': таймаут с обратным отсчетом и возможностью отмены."""
        logger.info(f"[TemporalAction] Running in 'beforeend' mode: {self.duration}s")
        
        # Показываем обратный отсчет, если включен
        if self.countdown_mode and self.bot and self.chat_id:
            try:
                m = self.bot.send_message(self.chat_id, self.countdown_text.format(sec=self.duration))
                self._msg_id = getattr(m, 'message_id', None)
                logger.debug(f"[TemporalAction] Countdown message sent: msg_id={self._msg_id}")
            except Exception as e:
                logger.warning(f"[TemporalAction] Failed to send countdown message: {e}")
                self.countdown_mode = False

        # Обратный отсчет по секундам
        for remaining in range(self.duration - 1, -1, -1):
            if self._cancel_event.is_set():
                logger.info(f"[TemporalAction] Cancelled during countdown at {remaining}s")
                self._notify_cancelled()
                return
            
            if self.countdown_mode and self._msg_id:
                try:
                    self.bot.edit_message_text(
                        chat_id=self.chat_id,
                        message_id=self._msg_id,
                        text=self.countdown_text.format(sec=max(remaining, 0))
                    )
                except Exception as e:
                    logger.debug(f"[TemporalAction] Failed to update countdown: {e}")
            
            time.sleep(1)

        # Проверяем отмену перед выполнением действия
        if self._cancel_event.is_set():
            logger.info(f"[TemporalAction] Cancelled just before action execution")
            self._notify_cancelled()
            return

        # Выполняем целевое действие
        logger.info(f"[TemporalAction] Executing target_action (beforeend mode)")
        if callable(self.target_action):
            self.target_action()

        if on_complete_callback and callable(on_complete_callback):
            on_complete_callback()

    def _run_afterstart_mode(self, on_complete_callback):
        """Режим 'afterstart': простое напоминание через заданное время."""
        logger.info(f"[TemporalAction] Running in 'afterstart' mode: {self.duration}s")
        
        # Простое ожидание без визуального отсчета
        for remaining in range(self.duration):
            if self._cancel_event.is_set():
                logger.info(f"[TemporalAction] Cancelled during sleep in 'afterstart' mode")
                return
            time.sleep(1)

        # Проверяем отмену перед выполнением
        if self._cancel_event.is_set():
            logger.info(f"[TemporalAction] Cancelled just before action execution (afterstart mode)")
            return

        # Выполняем целевое действие
        logger.info(f"[TemporalAction] Executing target_action (afterstart mode)")
        if callable(self.target_action):
            self.target_action()

        if on_complete_callback and callable(on_complete_callback):
            on_complete_callback()

    def _notify_cancelled(self):
        """Уведомление об отмене (только для режима beforeend)."""
        if self.countdown_mode and self._msg_id and self.bot:
            try:
                self.bot.edit_message_text(
                    chat_id=self.chat_id,
                    message_id=self._msg_id,
                    text="✅ Ответ получен, таймер отменен."
                )
                time.sleep(1)
                self.bot.delete_message(self.chat_id, self._msg_id)
                logger.info(f"[TemporalAction] Cancellation notification sent and cleaned up")
            except Exception as e:
                logger.debug(f"[TemporalAction] Failed to notify cancellation: {e}")