# app/modules/timing_primitives/dynamic_pause.py
# ВЕРСИЯ 2.0 (30.10.2025): Полная реализация визуальной паузы с прогресс-баром

import time
import threading

class DynamicPause:
    """
    Примитив динамической паузы.
    Поддерживаемые режимы:
    - silent: простая задержка без визуализации
    - progressbar: прогресс-бар 5 шагов с подписью
    """
    def __init__(self, bot, chat_id: int, duration: float, fill_type: str = 'silent', message_text: str = "Обработка..."):
        self.bot = bot
        self.chat_id = chat_id
        self.duration = float(duration or 0)
        self.fill_type = (fill_type or 'silent').lower()
        self.message_text = message_text or "Обработка..."
        self._on_complete = None

    def execute(self, on_complete_callback: callable):
        """Запустить паузу. Не блокирует основной поток."""
        self._on_complete = on_complete_callback
        t = threading.Thread(target=self._run, daemon=True)
        t.start()

    # --- internal ---
    def _run(self):
        try:
            if self.fill_type == 'progressbar':
                self._run_progress_bar()
            else:
                self._run_silent()
        finally:
            try:
                if callable(self._on_complete):
                    self._on_complete()
            except Exception:
                pass

    def _run_silent(self):
        time.sleep(self.duration)

    def _run_progress_bar(self):
        if not self.bot or not self.chat_id:
            time.sleep(self.duration)
            return
        
        # Начальное сообщение
        try:
            msg = self.bot.send_message(self.chat_id, f"⏳ {self.message_text}\n⬜️⬜️⬜️⬜️⬜️ 0%")
        except Exception:
            time.sleep(self.duration)
            return

        steps = 5
        step_duration = max(self.duration / steps, 0.05)
        for i in range(1, steps + 1):
            time.sleep(step_duration)
            percent = int(i * 100 / steps)
            filled = "🟩" * i
            empty = "⬜️" * (steps - i)
            try:
                self.bot.edit_message_text(chat_id=self.chat_id, message_id=msg.message_id,
                                           text=f"⏳ {self.message_text}\n{filled}{empty} {percent}%")
            except Exception:
                # Игнорируем ошибки редактирования (например, если сообщение уже удалено)
                pass
        
        # Финальная фиксация и мягкое удаление
        try:
            self.bot.edit_message_text(chat_id=self.chat_id, message_id=msg.message_id,
                                       text=f"✅ {self.message_text}")
            time.sleep(1.0)
            self.bot.delete_message(self.chat_id, msg.message_id)
        except Exception:
            pass