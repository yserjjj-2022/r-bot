# Task 3: Dialogue Terminator Implementation Details

## Обзор
Нам нужно реализовать механизм завершения диалога (Dialogue Terminator), который будет прерывать паттерн "вечного собеседника".
Чтобы не плодить лишние файлы и дополнительные LLM-вызовы (экономия токенов и latency), мы интегрируем анализ необходимости завершения диалога **прямо в `_perception_stage` (Volitional Detection)**.

Волевой анализатор (который уже анализирует контекст) теперь будет дополнительно возвращать объект `exit_signal`, если диалог пора заканчивать.

## Шаги для локального агента

### 1. Обновление промпта в `src/r_core/infrastructure/llm.py`
В методе `detect_volitional_pattern` нужно обновить `prompt`, чтобы он просил LLM помимо волевого паттерна анализировать и возможность естественного завершения диалога.

Обновите инструкцию и JSON-схему:
```python
        prompt = f"""
Ты - аналитик волевой сферы (Volitional Analyst) и контроллер диалога.
Твои задачи:
1. Найти в диалоге следы волевого конфликта/стремления (Trigger, Impulse, Target, Resolution Strategy, Intensity, Fuel).
2. Оценить, не подошел ли диалог к логическому или эмоциональному завершению (Exit Signal).

Диалог:
{history_str}
Текущее сообщение пользователя: {message_text}

Критерии для завершения диалога (should_exit = true):
- Явное прощание ("пока", "до завтра", "спокойной ночи").
- Выполнение задачи (пользователь получил, что хотел, и благодарит).
- Застревание в пустых ответах (Phatic loop: "ок", "ага").
- Эмоциональное выгорание/сопротивление общению.

Инструкция:
- Анализируй в основном реплики USER.
- Поля Volitional Pattern оставь null/пустыми, если волевого акта нет.
- Если диалог нужно завершить, предложи короткую директиву (suggested_message), как боту следует мягко попрощаться.

Верни JSON формат:
{{
  "volitional_pattern": {{
    "trigger": "...",
    "impulse": "...",
    "target": "...",
    "resolution_strategy": "...",
    "intensity": 0.7,
    "fuel": 0.5
  }},
  "exit_signal": {{
    "should_exit": true,
    "exit_type": "graceful",
    "reason": "task_completed",
    "suggested_message": "Попрощайся с пользователем, пожелай удачи и закрой текущую тему."
  }}
}}
"""
```

*Обратите внимание: метод `detect_volitional_pattern` должен возвращать теперь весь распарсенный JSON (словарь с ключами `volitional_pattern` и `exit_signal`), а не только паттерн.*

### 2. Изменения в `src/r_core/pipeline.py`

**В `_perception_stage`:**
Сейчас волевой скан пропускается с помощью `self.volition_check_counter % 5 == 0`.
Поскольку теперь нам нужно детектировать выход, нам нужно **изменить логику пропуска**:
- Если сообщение пользователя короткое (меньше 3 слов) или явно содержит слова "пока/спасибо", мы **должны** запустить скан вне очереди (чтобы поймать прощание).
- Метод `_perception_stage` должен возвращать оба объекта.

Пример обновления `_perception_stage`:
```python
    async def _perception_stage(self, message: IncomingMessage, chat_history: List[Dict]) -> Dict:
        history_lines = [f"{m['role']}: {m['content']}" for m in chat_history[-6:]]
        history_str = "\\n".join(history_lines)
        
        volitional_pattern = None
        exit_signal = None
        
        self.volition_check_counter += 1
        
        # Эвристика: форсируем проверку, если юзер пишет прощание
        explicit_exit_markers = ["пока", "до встречи", "до завтра", "спокойной ночи", "спасибо, я всё"]
        text_lower = message.text.lower() if message.text else ""
        force_check = any(marker in text_lower for marker in explicit_exit_markers)
        
        if len(chat_history) >= 2 and (force_check or self.volition_check_counter % 5 == 0):
             print(f"[Pipeline] Scanning for volitional patterns & exit signals (Turn {self.volition_check_counter})...")
             perception_result = await self.llm.detect_volitional_pattern(message.text, history_str)
             if perception_result:
                 volitional_pattern = perception_result.get("volitional_pattern")
                 exit_signal = perception_result.get("exit_signal")
                 if volitional_pattern and volitional_pattern.get('trigger'):
                     print(f"[Pipeline] Pattern DETECTED: {volitional_pattern.get('trigger')} -> {volitional_pattern.get('impulse')}")
                 if exit_signal and exit_signal.get("should_exit"):
                     print(f"[Terminator] Exit Intent DETECTED: {exit_signal.get('reason')}")
        else:
             print(f"[Pipeline] Volition & Exit scan skipped (Turn {self.volition_check_counter})")
        
        return {
            "triples": [], 
            "anchors": [{"raw_text": message.text, "emotion_score": 0.5, "tags": ["auto"]}], 
            "volitional_pattern": volitional_pattern,
            "exit_signal": exit_signal
        }
```

**В `process_message` (Применение директивы выхода):**
После вызова `extraction_result = await self._perception_stage(...)`:
Извлеки `exit_signal`: `exit_signal = extraction_result.get("exit_signal")`

В блоке подготовки промптов (там, где создается `final_style_instructions`, около строки 500):
```python
        exit_instruction = ""
        if exit_signal and exit_signal.get("should_exit"):
            if exit_signal.get("exit_type") == "graceful":
                suggested = exit_signal.get("suggested_message", "Пора заканчивать беседу.")
                exit_instruction = (
                    f"\\n\\nCONVERSATIONAL EXIT DIRECTIVE:\\n"
                    f"- The dialogue has reached a natural conclusion ({exit_signal.get('reason', 'unknown')}).\\n"
                    f"- Follow this instruction to close: {suggested}\\n"
                    f"- Do NOT start new topics or ask open-ended questions.\\n"
                )
```
Затем добавь `exit_instruction` к переменной `final_style_instructions`.

**В логгере (internal_stats):**
Добавь: `"termination_triggered": exit_signal.get("should_exit") if exit_signal else False`

## Инструкции по выполнению
Выполняй изменения, перезаписывая файлы. Не ломай существующую логику Council Debate и генерации.
