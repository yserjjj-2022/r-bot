# app/modules/timing_primitives/temporal_action.py
# ВЕРСИЯ 1.1 (30.10.2025): Визуальный обратный отсчёт + отмена

import time
import threading

class TemporalAction:
    """
    Примитив для действий по истечении времени с возможностью отмены и визуальным обратным отсчётом.
    """
    def __init__(self, bot, chat_id: int, duration: float, target_action: callable,
                 countdown_mode: bool = True, countdown_text: str = "Осталось: {sec} сек"):
        self.bot = bot
        self.chat_id = chat_id
        self.duration = int(float(duration or 0))
        self.target_action = target_action
        self.countdown_mode = countdown_mode
        self.countdown_text = countdown_text
        self._cancel_event = threading.Event()
        self._thread = None
        self._msg_id = None

    def execute(self, on_complete_callback: callable = None):
        """Запуск в отдельном потоке."""
        self._thread = threading.Thread(target=self._run, args=(on_complete_callback,), daemon=True)
        self._thread.start()

    def cancel(self):
        """Мягкая отмена счётчика."""
        self._cancel_event.set()

    # --- internal ---
    def _run(self, on_complete_callback):
        try:
            if self.countdown_mode and self.bot and self.chat_id:
                try:
                    m = self.bot.send_message(self.chat_id, self.countdown_text.format(sec=self.duration))
                    self._msg_id = getattr(m, 'message_id', None)
                except Exception:
                    self.countdown_mode = False

            for remaining in range(self.duration - 1, -1, -1):
                if self._cancel_event.is_set():
                    self._notify_cancelled()
                    return
                if self.countdown_mode and self._msg_id:
                    try:
                        self.bot.edit_message_text(
                            chat_id=self.chat_id,
                            message_id=self._msg_id,
                            text=self.countdown_text.format(sec=max(remaining, 0))
                        )
                    except Exception:
                        pass
                time.sleep(1)

            # Таймер истёк
            if self._cancel_event.is_set():
                self._notify_cancelled()
                return

            if callable(self.target_action):
                self.target_action()

            if on_complete_callback and callable(on_complete_callback):
                on_complete_callback()
        except Exception as e:
            print(f"[TemporalAction] error: {e}")

    def _notify_cancelled(self):
        if self.countdown_mode and self._msg_id and self.bot:
            try:
                self.bot.edit_message_text(
                    chat_id=self.chat_id,
                    message_id=self._msg_id,
                    text="✅ Ответ получен, таймер отменен."
                )
                time.sleep(1)
                self.bot.delete_message(self.chat_id, self._msg_id)
            except Exception:
                pass
