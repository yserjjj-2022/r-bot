# Task 6: Prioritize Exit Signal over Bifurcation Engine

## Описание проблемы
Логи показывают архитектурный конфликт в `pipeline.py`:
1. `Dialogue Terminator` корректно срабатывает на прощание пользователя (`[Pipeline] 🚪 EXIT SIGNAL DETECTED: task_completed`).
2. Однако, так как пользователь ответил коротко ("Спасибо, пока!"), уровень вовлеченности (TEC) падает до нуля (`[TopicTracker] TEC: 0.43 → 0.00`).
3. Падение TEC переводит Норадреналин (LC-NE) в режим `tonic` (поиск нового).
4. Режим `tonic` запускает `Bifurcation Engine`, который находит незаконченную тему ("когда надо тащиться по морозу...") и вставляет инструкцию на **смену темы**.
5. В итоге LLM получает взаимоисключающие директивы: "Заверши диалог" и "Переведи тему на мороз". В таких случаях LLM часто выбирает продолжение разговора, игнорируя прощание.

## Решение
Нам нужно **заблокировать запуск Bifurcation Engine**, если сработал `Exit Signal`. Прощание — это абсолютный приоритет. Если пользователь уходит, нам не нужно искать новые темы.

## Шаги для локального агента

### Обновление `src/r_core/pipeline.py`

Найди блок, где запускается Bifurcation Engine (Stage 3). Он выглядит примерно так:
```python
        # === Stage 3: The Bifurcation Engine ===
        # Trigger when LC mode is "tonic" (low engagement, exploration needed)
        bifurcation_candidates = []
        predicted_bifurcation_topic = None
        semantic_candidates = []
        emotional_candidates = []
        zeigarnik_candidates = []
        
        if lc_mode == "tonic":
```

Добавь в условие проверку флага завершения диалога. Условие должно стать таким:
```python
        # === Stage 3: The Bifurcation Engine ===
        # Trigger when LC mode is "tonic" (low engagement, exploration needed)
        # 🛑 CRITICAL FIX: Do NOT trigger Bifurcation if Dialogue Terminator is trying to exit
        bifurcation_candidates = []
        predicted_bifurcation_topic = None
        semantic_candidates = []
        emotional_candidates = []
        zeigarnik_candidates = []
        
        is_exiting = exit_signal.get("should_exit", False)
        
        if lc_mode == "tonic" and not is_exiting:
```

### Дополнительно: Очистка директивы
В самом низу, где формируется `final_style_instructions` (около строки 520):
```python
        # === Stage 3: Inject Bifurcation Directive into LLM Prompt ===
        bifurcation_instruction = ""
        if predicted_bifurcation_topic and not is_exiting: # <-- Добавить защиту и сюда на всякий случай
            bifurcation_instruction = (
                f"\\n\\nPROACTIVE MIRRORING (Topic Switch Recommended):\\n"
                f"- The user's engagement with the current topic is depleted (TEC={current_tec:.2f}).\\n"
                f"- Gently pivot the conversation towards: {predicted_bifurcation_topic}\\n"
                f"- Use natural transition, acknowledge the previous topic briefly, then bridge to the new one.\\n"
            )
```

Всё остальное остается без изменений. Выполни обновление `pipeline.py`.
