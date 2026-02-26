# Task 5: Fix Pydantic Validation Error in Volitional Pattern

## Описание проблемы
В логах видно, что `Dialogue Terminator` отработал ИДЕАЛЬНО:
`[Pipeline] 🚪 EXIT SIGNAL DETECTED: task_completed - Спокойной ночи, Сережа...`

Однако произошел краш (в Streamlit) на этапе сохранения памяти:
`5 validation errors for VolitionalPattern: trigger Input should be a valid string... input_value=None`.

Это произошло потому, что LLM вернула:
```json
{
  "volitional_pattern": null,
  "exit_signal": {"should_exit": true, ...}
}
```
Метод `detect_volitional_pattern` вернул `volitional_pattern=None`.
Затем `pipeline.py` передал `extraction_result` в метод `await self.memory.memorize_event(...)`, который, в свою очередь, попытался сохранить `volitional_pattern` в базу данных. В этот момент Pydantic попытался провалидировать словарь, где ключи оказались `None`, и упал.

## Шаги для локального агента

### 1. Фикс в `src/r_core/infrastructure/llm.py`
В методе `detect_volitional_pattern` нужно жестко обрабатывать случай, когда `volitional_pattern` приходит как `None`. Мы не должны пытаться заполнять его дефолтами, если его вообще нет — мы должны передавать `None` дальше, чтобы Pydantic (или вызывающий код) просто пропустил его сохранение.

Найди метод `detect_volitional_pattern` и перепиши блок обработки результата:
```python
            # Build result with both volitional_pattern and exit_signal
            volitional_pattern = data.get("volitional_pattern")
            exit_signal = data.get("exit_signal", {"should_exit": False})
            
            # Normalize exit_signal
            if not isinstance(exit_signal, dict):
                exit_signal = {"should_exit": False}
            
            # If volitional_pattern exists, ensure it has required fields
            # CRITICAL: We must check if it's explicitly None, or an empty dict
            if volitional_pattern is not None and isinstance(volitional_pattern, dict):
                # If it's an empty dict, or has explicit None values for required fields, handle it
                trigger = volitional_pattern.get("trigger")
                impulse = volitional_pattern.get("impulse")
                
                # If LLM returned a dict with nulls, treat it as "no pattern"
                if trigger is None or impulse is None or trigger == "" or impulse == "":
                    volitional_pattern = None
                else:
                    # Valid pattern, ensure defaults for missing optional fields
                    volitional_pattern.setdefault("target", volitional_pattern.get("topic", "General"))
                    volitional_pattern.setdefault("topic", volitional_pattern.get("trigger", "General"))
                    volitional_pattern.setdefault("intent_category", "Casual")
                    volitional_pattern.setdefault("topic_engagement", 1.0)
                    volitional_pattern.setdefault("fuel", 0.5)
                    volitional_pattern.setdefault("intensity", 0.5)
            else:
                # LLM explicitly returned null or something invalid
                volitional_pattern = None
            
            return {
                "volitional_pattern": volitional_pattern,
                "exit_signal": exit_signal
            }
```

### 2. Защита при сохранении в `src/r_core/memory.py`
В файле `memory.py` найдите метод `memorize_event`. Там нужно убедиться, что мы вообще не пытаемся парсить паттерн, если он `None`.

Найди этот блок (или похожий):
```python
        if extraction_result.get("volitional_pattern"):
            try:
                # Validation and saving logic
```
Замени его на:
```python
        vol_pattern_data = extraction_result.get("volitional_pattern")
        if vol_pattern_data is not None and isinstance(vol_pattern_data, dict):
            # Check if required keys actually exist and are not None before Pydantic validation
            if vol_pattern_data.get("trigger") and vol_pattern_data.get("impulse"):
                try:
                    # TODO: call Pydantic schema or DB save
                    await self.store.save_volitional_pattern(
                        user_id=message.user_id,
                        pattern_data=vol_pattern_data
                    )
                except Exception as e:
                    print(f"[Memory] Failed to save volitional pattern: {e}")
            else:
                print("[Memory] Skipped saving empty/null volitional pattern")
```
*Примечание: в `memory.py` метод сохранения может называться по-другому (например, создание объекта `VolitionalPattern` напрямую). Главное — обернуть это всё в строгую проверку `if vol_pattern_data.get("trigger"):`.*
