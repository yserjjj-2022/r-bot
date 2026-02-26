# Task 3: Dialogue Terminator Implementation Details

## Обзор
Нам нужно добавить модуль `DialogueTerminator`, который будет прерывать паттерн "вечного собеседника" и инициировать завершение диалога. Этот модуль должен встраиваться в `pipeline.py` и использовать LLM для анализа контекста.

## Шаги для локального агента

### 1. Создание файла `src/r_core/terminator.py`
Создай новый файл, содержащий класс `DialogueTerminator`.
```python
import json
from dataclasses import dataclass
from typing import Dict, List, Optional
from datetime import datetime

@dataclass
class ExitSignal:
    should_exit: bool
    exit_type: str  # "graceful" | "hard" | "silent" | "none"
    reason: str
    suggested_message: str

class DialogueTerminator:
    def __init__(self, llm_client):
        self.llm = llm_client

    async def evaluate(
        self, 
        current_tec: float, 
        intent_category: str,
        phatic_loop_count: int,
        user_message: str,
        chat_history: List[Dict]
    ) -> ExitSignal:
        """
        Оценивает необходимость завершения диалога.
        Эвристики для раннего выхода без LLM:
        - Если TEC > 0.6 и intent_category не Phatic, возвращаем none.
        - Если юзер явно прощается (regex: "пока", "до завтра", "спокойной ночи"), можно сразу вернуть graceful/hard.
        
        Если эвристики не дали четкого ответа, вызываем LLM-классификатор.
        """
        # 1. Быстрые проверки (Эвристики)
        text_lower = user_message.lower()
        explicit_exit_markers = ["пока", "до встречи", "до завтра", "спокойной ночи", "пойду спать", "мне пора", "спасибо, я всё"]
        
        if any(marker in text_lower for marker in explicit_exit_markers):
            return ExitSignal(
                should_exit=True,
                exit_type="graceful",
                reason="explicit_exit_intent",
                suggested_message="Попрощайся с пользователем, пожелай удачи и закрой текущую тему."
            )

        # Если разговор активен, не прерываем
        if current_tec > 0.5 and intent_category not in ["Phatic", "Task"]:
            return ExitSignal(False, "none", "", "")

        # 2. LLM Analysis для сложных случаев (застревание в фатической петле, решение задачи)
        # Отправляем последние 3-4 сообщения
        recent_history = "\\n".join([f"{msg['role']}: {msg['content']}" for msg in chat_history[-4:]])
        
        prompt = f"""
Ты - Dialogue Terminator, модуль контроля завершения диалога.
Проанализируй текущий контекст и реши, нужно ли боту инициировать завершение беседы.

Context:
- User Intent: {intent_category}
- Topic Engagement (TEC): {current_tec:.2f} (0.0=bored, 1.0=engaged)
- Phatic Loop Count: {phatic_loop_count} (кол-во коротких/пустых ответов подряд)
- Recent Dialogue:
{recent_history}
- User's last message: "{user_message}"

Signals to check for termination:
1. Task completed (user got what they wanted).
2. Phatic loop exhaustion (repetitive "ok", "yeah", "ага").
3. Emotional burnout (frustration, giving up).

Return ONLY JSON:
{{
    "should_exit": true/false,
    "exit_type": "graceful" (polite suggestion) or "none",
    "reason": "task_completed" / "phatic_loop" / "none",
    "suggested_message": "Instruction for the bot on how to politely end the conversation. Keep it brief."
}}
"""
        try:
            response = await self.llm.complete(prompt)
            cleaned = response.replace("```json", "").replace("```", "").strip()
            data = json.loads(cleaned)
            
            if data.get("should_exit"):
                return ExitSignal(
                    should_exit=True,
                    exit_type=data.get("exit_type", "graceful"),
                    reason=data.get("reason", "unknown"),
                    suggested_message=data.get("suggested_message", "Пора закругляться.")
                )
        except Exception as e:
            print(f"[Terminator] LLM Evaluation failed: {e}")
            
        return ExitSignal(False, "none", "", "")
```

### 2. Интеграция в `src/r_core/pipeline.py`

**В `__init__`:**
Импортируй класс: `from .terminator import DialogueTerminator`
Инициализируй его: `self.terminator = DialogueTerminator(self.llm)`

В `self.current_topic_state` добавь счетчик `phatic_loop_count`: 0 (чтобы передавать его в Терминатор).

**В `process_message`:**
В блоке `TopicTracker Update`, когда ты проверяешь `is_short_or_phatic`, обновляй счетчик:
```python
if is_short_or_phatic:
    self.current_topic_state["phatic_loop_count"] += 1
else:
    self.current_topic_state["phatic_loop_count"] = 0
```

Сразу ПОСЛЕ блока TopicTracker Update (и HIPPOCAMPUS TRIGGER) вызови Терминатор:
```python
# === 3.5 DIALOGUE TERMINATOR ===
exit_instruction = ""
try:
    exit_signal = await self.terminator.evaluate(
        current_tec=self.current_topic_state["tec"],
        intent_category=self.current_topic_state["intent_category"],
        phatic_loop_count=self.current_topic_state.get("phatic_loop_count", 0),
        user_message=message.text,
        chat_history=context.get("chat_history", [])
    )
    
    if exit_signal.should_exit:
        print(f"[Terminator] Triggered! Type: {exit_signal.exit_type}, Reason: {exit_signal.reason}")
        if exit_signal.exit_type == "graceful":
            exit_instruction = (
                f"\\n\\nCONVERSATIONAL EXIT DIRECTIVE:\\n"
                f"- The dialogue has reached a natural conclusion ({exit_signal.reason}).\\n"
                f"- Follow this instruction to close: {exit_signal.suggested_message}\\n"
                f"- Do NOT start new topics or ask open-ended questions.\\n"
            )
except Exception as e:
    print(f"[Terminator] Error: {e}")
```

Затем добавь `exit_instruction` к `final_style_instructions` перед генерацией ответа (там, где добавляется `bifurcation_instruction`).

В `internal_stats` добавь:
`"termination_triggered": exit_signal.should_exit if 'exit_signal' in locals() else False`

## Правила
Перепиши файлы целиком. Убедись, что Terminator не блокирует генерацию, а именно добавляет директиву в промпт для мягкого выхода.
