# Техническое Задание: Оптимизация алгоритма Topic Boundary Detection (TEC)

## Контекст проблемы (Bug Report)
Текущая реализация отслеживания смены темы в `RCoreKernel` (Topic Tracker) работает некорректно для современных моделей эмбеддингов (text-embedding-3). Алгоритм использует пошаговое косинусное сходство (Markov property) с жестким порогом `0.5`. 

**Симптом:** Любой короткий ответ пользователя ("ага", "ясно", "ок") имеет косинусное сходство `0.15 - 0.35` с предыдущей развернутой фразой. Это вызывает ложное срабатывание индикатора смены темы (`topic_changed = True`), что приводит к перманентному сбросу счетчика интереса (TEC) в `1.0`. В результате механизм бифуркации (Bifurcation Engine) никогда не активируется.

## Цель
Перевести Topic Tracker с наивного пошагового сравнения на архитектуру **усредненного вектора темы (Topic Centroid)** и откалибровать пороги отсечения, добавив защиту от коротких (шумных) фраз.

---

## Инструкции по реализации (STRICT)

**Целевой файл:** `src/r_core/pipeline.py`
**Язык комментариев:** Русский (согласно протоколу)

### 1. Модификация структуры состояния (State Init)
В классе `RCoreKernel` (в методе `__init__`) обновите словарь `self.current_topic_state`:
- Поле `"topic_embedding"` теперь должно хранить не вектор последнего сообщения, а **усредненный вектор (Centroid)** всех сообщений текущей темы.
- Добавьте новое поле `"messages_in_topic": 0` (счетчик сообщений для корректного расчета скользящего среднего вектора).

```python
        # ✨ NEW: Topic Tracker (independent from volitional patterns)
        self.current_topic_state = {
            "topic_embedding": None,         # Усредненный вектор (Centroid) текущей темы
            "topic_text": "",                # Text summary of topic
            "tec": 1.0,                      # Topic Engagement Capacity [0.0, 1.0]
            "turns_on_topic": 0,             # Turns spent on this topic
            "messages_in_topic": 0,          # Счетчик сообщений для расчета центроида
            "intent_category": "Casual",     # Nature taxonomy: Phatic/Casual/Narrative/Deep/Task
            "last_prediction_error": 0.5     # PE from last turn (for decay calculation)
        }
```

### 2. Защита от коротких фраз (Phatic Bypass)
В методе `process_message` (блок `Topic Tracker Update`):
Перед тем как вычислять косинусное сходство, внедрите проверку длины и типа сообщения. 
Короткие фразы (менее 4 слов) или фразы, распознанные как `is_phatic_message`, **не могут быть началом новой темы**. Их векторы шумные. Для таких сообщений принудительно устанавливайте `topic_changed = False` и пропускайте вычисление `similarity`.

```python
        is_short_or_phatic = False
        if message.text:
            word_count = len(message.text.split())
            if word_count < 4 or is_phatic_message(message.text):
                is_short_or_phatic = True
```

### 3. Изменение логики сравнения (Distance Logic)
Если сообщение длинное и не фатическое, вычислите косинусное сходство между `current_embedding` и центроидом `self.current_topic_state["topic_embedding"]`.
- Снизьте порог смены темы с `0.5` до **`0.40`** (эмпирически обосновано для центроидов на современных моделях).

```python
            if similarity < 0.40:
                # Тема значительно изменилась
                topic_changed = True
```

### 4. Обновление центроида (Centroid Update Rule)
Если тема *не изменилась* (topic_changed == False), плавно обновите центроид темы, используя счетчик `"messages_in_topic"`.
- Формула: `new_centroid = (old_centroid * count + current_embedding) / (count + 1)`
- Обязательно **нормализуйте** новый вектор после сложения. Убедитесь, что импортировали `numpy as np` или используете существующие импорты `dot` и `norm`.

Пример логики обновления:
```python
            # Плавно обновляем центроид темы
            count = self.current_topic_state["messages_in_topic"]
            old_centroid = self.current_topic_state["topic_embedding"]
            
            # Взвешенное сложение (используем списковые включения или numpy, если импортирован весь модуль)
            # В файле уже есть from numpy.linalg import norm, поэтому можно использовать numpy
            import numpy as np
            old_arr = np.array(old_centroid)
            curr_arr = np.array(current_embedding)
            
            new_centroid = ((old_arr * count) + curr_arr) / (count + 1)
            # Нормализация
            new_centroid = new_centroid / np.linalg.norm(new_centroid)
            
            self.current_topic_state["topic_embedding"] = new_centroid.tolist()
            self.current_topic_state["messages_in_topic"] += 1
```
*(Не забудьте сбрасывать `"messages_in_topic": 1` при `topic_changed == True`)*

---

## Протокол Безопасности (CRITICAL)
- **SAFETY PROTOCOL B:** При редактировании `src/r_core/pipeline.py` вы обязаны предоставить ПОЛНЫЙ, исполняемый код файла. Использование плейсхолдеров (`# ... existing code ...`) СТРОГО ЗАПРЕЩЕНО. 
- Сохраните всю существующую логику интеграции с БД, волей (Volition), гормонами (LC-NE) и Хиппокампом. Ни одна строка существующей бизнес-логики вне блока `Topic Tracker Update` не должна пострадать.