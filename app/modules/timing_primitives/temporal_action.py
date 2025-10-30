# app/modules/timing_primitives/temporal_action.py
# ВЕРСИЯ 1.0 (30.10.2025): Базовая заглушка для безопасной интеграции

import time
import threading

class TemporalAction:
    """
    Примитив для выполнения действий по истечении времени с возможностью отмены.
    
    Основные возможности:
    - Таймауты на ответы пользователя
    - Драматургические задержки с переходами
    - Система напоминаний (планируется)
    - Дедлайны с предупреждениями (планируется)
    """
    
    def __init__(self, bot, chat_id: int, duration: float, target_action: callable, 
                 countdown_mode: bool = False, countdown_text: str = ""):
        self.bot = bot
        self.chat_id = chat_id
        self.duration = float(duration or 0)
        self.target_action = target_action
        self.countdown_mode = countdown_mode
        self.countdown_text = countdown_text or "Осталось времени: {time}"
        self._timer_thread = None
        self._cancelled = False

    def execute(self, on_complete_callback: callable = None):
        """Запустить таймер. Не блокирует основной поток."""
        if self._cancelled:
            return
            
        self._timer_thread = threading.Thread(target=self._run, daemon=True)
        self._timer_thread.start()

    def cancel(self):
        """Отменить выполнение таймера."""
        self._cancelled = True
        if self._timer_thread and self._timer_thread.is_alive():
            # В будущих версиях здесь будет более элегантная отмена
            pass

    # --- internal ---
    def _run(self):
        """Внутренняя логика выполнения таймера."""
        # ЭТАП 1: Пока просто безопасная пауза
        time.sleep(self.duration)
        
        if not self._cancelled and callable(self.target_action):
            try:
                self.target_action()
            except Exception as e:
                print(f"[TemporalAction] Ошибка выполнения target_action: {e}")