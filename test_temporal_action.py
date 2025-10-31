# Шаг 2 тестирования TemporalAction (локальный вспомогательный скрипт)
# Этот файл НЕ используется приложением и служит только для локальной проверки поведения примитива.
# Запускать вручную: `python test_temporal_action.py`

import time
from app.modules.timing_primitives.temporal_action import TemporalAction

class DummyBot:
    def send_message(self, chat_id, text):
        print(f"[DummyBot] send_message: {text}")
        class M: pass
        m = M(); m.message_id = 1; return m
    def edit_message_text(self, chat_id, message_id, text):
        print(f"[DummyBot] edit_message_text: {text}")
    def delete_message(self, chat_id, message_id):
        print(f"[DummyBot] delete_message: id={message_id}")

if __name__ == "__main__":
    bot = DummyBot()
    print("\n=== Test beforeend (timeout with countdown) ===")
    ta1 = TemporalAction(bot=bot, chat_id=123, duration=3, target_action=lambda: print("[TA1] action fired"), triggermode='beforeend')
    ta1.execute()
    time.sleep(2)
    # ta1.cancel()  # раскомментируйте, чтобы проверить отмену
    time.sleep(3)

    print("\n=== Test afterstart (reminder) ===")
    ta2 = TemporalAction(bot=bot, chat_id=123, duration=2, target_action=lambda: print("[TA2] reminder fired"), triggermode='afterstart')
    ta2.execute()
    time.sleep(3)
