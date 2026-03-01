# Task 7: Dynamic Phatic Threshold (Personalized Verbosity)

## Концепция
Сейчас система считает сообщение "фатическим" (phatic), если в нём меньше 4 слов (жесткий хардкод в `pipeline.py`). Это не учитывает индивидуальный стиль общения пользователя: для кого-то 5 слов — это уже развернутый ответ, а для кого-то 2 слова — норма.

Нужно научить бота адаптироваться к "многословности" (verbosity) пользователя и динамически вычислять порог фатичности.

## Архитектурное решение

### 1. Сохранение метрики в профиле пользователя
В таблице `user_profiles` есть поле `attributes` (JSONB). Туда мы добавим новую метрику:
```json
{
  "avg_word_count": 5.0,
  "messages_analyzed": 10
}
```

### 2. Динамический расчёт порога (Dynamic Phatic Threshold)
Вместо хардкода `word_count < 4`, порог будет вычисляться как:
```python
dynamic_threshold = max(2, min(4, int(avg_word_count * 0.4)))
```
*Логика: Если пользователь пишет в среднем по 10 слов, порог будет 4 слова. Если пишет по 3 слова, порог будет 2 слова.*

### 3. Место реализации
Все изменения будут в `src/r_core/pipeline.py` в методе `process_message`.

#### Шаг 1: Извлечение средней длины
В блоке, где мы получаем `user_profile` из контекста:
```python
        user_profile = context.get("user_profile", {})
        attributes = user_profile.get("attributes", {}) if user_profile else {}
        avg_word_count = attributes.get("avg_word_count", 5.0)
```

#### Шаг 2: Применение динамического порога
В блоке Topic Tracker Update:
```python
        # === Защита от коротких фраз (Phatic Bypass) ===
        is_short_or_phatic = False
        word_count = 0
        if message.text:
            word_count = len(message.text.split())
            
            # Динамический порог на основе истории юзера
            dynamic_phatic_threshold = max(2, min(5, int(avg_word_count * 0.4)))
            
            phatic_patterns = ["ага", "ясно", "ок", "да", "нет", "хм", "мм", "угу", "ну", "понятно", "окей", "ладно", "чё", "да?", "и что?", "и что теперь?"]
            is_phatic_keyword = any(pattern in message.text.lower() for pattern in phatic_patterns)
            
            if word_count <= dynamic_phatic_threshold or (word_count <= dynamic_phatic_threshold + 1 and is_phatic_keyword):
                is_short_or_phatic = True
                print(f"[TopicTracker] ⏭️ Phatic message detected (words: {word_count}, threshold: {dynamic_phatic_threshold})")
```

#### Шаг 3: Обновление статистики (Фоновая задача)
Чтобы `avg_word_count` обновлялся, мы добавим фоновое обновление профиля прямо в конце пайплайна (или в Гиппокампе, но проще в пайплайне для начала, через прямой SQL-апдейт). 

*Примечание для локального агента: так как мы не хотим усложнять pipeline прямыми SQL-запросами к профилю на каждом шаге (чтобы не тормозить ответ), лучше перенести обновление `avg_word_count` в `Hippocampus` или `MemorySystem.memorize_event`.*

## Инструкция для агента:
Пока мы просто запишем спеку, чтобы не потерять идею. В новом треде мы реализуем эту механику:
1. Обновим `user_profiles.attributes` при каждом новом сообщении (скользящее среднее).
2. Заменим хардкод `word_count < 4` на `word_count <= max(2, int(avg_word_count * 0.4))`.
