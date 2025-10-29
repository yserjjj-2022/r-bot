# -*- coding: utf-8 -*-
# app/modules/timing_primitives/dynamic_pause.py

import threading

class DynamicPause:
    """
    Примитив Динамической Паузы.
    Отвечает за все виды задержек с визуальным сопровождением или без него.
    На первом этапе реализуем только 'silent' (молчаливая пауза) как безопасный каркас.
    """
    def __init__(self, bot, chat_id, duration: float, fill_type: str = 'silent', message_text: str = ''):
        self.bot = bot
        self.chat_id = chat_id
        self.duration = duration
        self.fill_type = fill_type
        self.message_text = message_text

    def execute(self, on_complete_callback: callable):
        """
        Запускает выполнение паузы в отдельном потоке.
        Пока для всех типов исполняется безопасная молчаливая пауза.
        """
        print(f"[DynamicPause] Запуск: {self.duration}s, тип: {self.fill_type}")

        # TODO: добавить реализацию typing/progressbar/countdown на следующих шагах
        thread = threading.Timer(self.duration, on_complete_callback)
        thread.daemon = True
        thread.start()
