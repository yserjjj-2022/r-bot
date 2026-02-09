# 💚 Affective Theory of Mind (ToM) — User Guide

## 🎯 Что это?

**Affective Theory of Mind** — это способность R-Bot **запоминать эмоциональное отношение пользователя** к объектам, людям и концепциям.

Если вы скажете боту **"Ненавижу Java"**, он:
1. Извлечёт эмоцию из вашего сообщения
2. Сохранит в **semantic_memory** как `(User, HATES, Java, sentiment={valence: -0.9})`
3. При следующем вопросе **избежит** упоминания Java в рекомендациях

---

## 🛠️ Архитектура

### 1. Извлечение (Extraction)

**LLM Service** (`src/r_core/infrastructure/llm.py`):
- В `generate_council_report()` добавлена секция **"AFFECTIVE EXTRACTION"**
- LLM анализирует текст на наличие ключевых слов:
  - `loves`, `hates`, `fears`, `enjoys`, `despises`, `adores`, etc.
- Возвращает JSON:

```json
{
  "affective_extraction": [
    {
      "subject": "User",
      "predicate": "HATES",
      "object": "Java",
      "intensity": 0.9
    }
  ]
}
```

### 2. Сохранение (Storage)

**Pipeline** (`src/r_core/pipeline.py`):
- Обрабатывает `affective_extraction` из Council Report
- Преобразует `intensity` в **VAD-формат**:
  - `HATES` → `valence: -0.9, arousal: 0.3, dominance: 0.0`
  - `LOVES` → `valence: +0.85, arousal: 0.3, dominance: 0.0`
  - `FEARS` → `valence: -0.7, arousal: 0.5, dominance: -0.2`

**Memory System** (`src/r_core/memory.py`):
- Сохраняет в таблицу `semantic_memory` с полем `sentiment`:

```sql
INSERT INTO semantic_memory (user_id, subject, predicate, object, sentiment)
VALUES (999, 'User', 'HATES', 'Java', '{"valence": -0.9, "arousal": 0.3, "dominance": 0.0}');
```

### 3. Восстановление (Recall)

**Memory System** (`src/r_core/memory.py`):
- Метод `_extract_affective_context(user_id, text)`:
  - Извлекает сущности из текущего сообщения
  - Проверяет через `get_sentiment_for_entity(entity)`, есть ли эмоциональная привязка
  - Возвращает `affective_warnings` список:

```python
[
  {
    "entity": "Java",
    "predicate": "HATES",
    "user_feeling": "NEGATIVE",
    "intensity": 0.9
  }
]
```

### 4. Влияние на Генерацию (Response Injection)

**Pipeline** (`src/r_core/pipeline.py`):
- Формирует `affective_context_str`:

```
⚠️ EMOTIONAL RELATIONS (User's Preferences):
- ⚠️ AVOID mentioning 'Java' (User HATES it, intensity=0.90). Do not use it as an example.
```

**LLM Service** (`src/r_core/infrastructure/llm.py`):
- `generate_response()` принимает параметр `affective_context`
- Инъецирует в system prompt перед генерацией

---

## 🧪 Тестирование

### Метод 1: Streamlit UI (рекомендуемый)

1. **Запустите Streamlit**:

```bash
streamlit run app_streamlit.py
```

2. **Инициализируйте БД** (если ещё не сделали):
   - Нажмите кнопку **"Initialize DB"** в sidebar

3. **Тестовый диалог**:

   **Шаг 1**: Выразите эмоцию
   ```
   User: Я ненавижу Java, это ужасный язык
   ```

   **Проверьте**:
   - В **Technical Details** должно быть: `affective_triggers_detected: 1`
   - В sidebar откройте **"💚 Emotional Memory" → "View User Preferences"**
   - Должна появиться запись: `🔴 HATES Java (V: -0.90)`

   **Шаг 2**: Задайте вопрос с упоминанием триггера
   ```
   User: Какой язык программирования мне использовать?
   ```

   **Ожидаемый результат**:
   - В ответе появится индикатор: `💚 Sentiment Context Used (1 triggers)`
   - Бот **НЕ должен** упоминать Java в рекомендациях
   - Вместо этого он предложит Python, Go, Rust и т.д.

### Метод 2: Консольный Скрипт

```bash
python tests/test_affective_tom_manual.py
```

**Что произойдёт**:
1. Инициализация БД
2. Отправка "Я ненавижу Java"
3. Проверка сохранённого sentiment
4. Отправка "Какой язык использовать?"
5. Проверка, что бот избегает Java

---

## 📊 Метрики

В `internal_stats` каждого ответа теперь добавлены:

```json
{
  "affective_triggers_detected": 1,  // Сколько эмоций извлечено из текущего сообщения
  "sentiment_context_used": true     // Был ли применён affective context при генерации
}
```

Эти метрики также логируются в таблицу `rcore_metrics` (если включено логирование).

---

## 🔧 Расширенные Возможности

### Добавить новые эмоции

Редактировать `src/r_core/infrastructure/llm.py` → секция **"AFFECTIVE EXTRACTION"**:

```python
"- Keywords: loves, hates, fears, enjoys, despises, adores, can't stand, passionate about, disgusted by, **obsessed with, indifferent to**."
```

Добавьте обработку в `src/r_core/pipeline.py`:

```python
if predicate in ["HATES", "DESPISES", "FEARS", "DISGUSTED_BY"]:
    valence = -intensity
elif predicate in ["LOVES", "ENJOYS", "ADORES", "OBSESSED_WITH"]:
    valence = intensity
elif predicate == "INDIFFERENT_TO":
    valence = 0.0
```

### Temporal Memory Decay (Забывание старых эмоций)

В `src/r_core/memory.py` → `get_sentiment_for_entity()`:

```python
import math
from datetime import datetime

# Формула Эббингауза
days_ago = (datetime.utcnow() - row.created_at).days
time_decay = 1 / (1 + math.log(1 + days_ago))

return {
    "entity": row.object,
    "sentiment": row.sentiment,
    "intensity": abs(row.sentiment.get("valence", 0.0)) * time_decay  # Уменьшение со временем
}
```

---

## 🐞 Известные Ограничения

1. **Простое извлечение сущностей**: Текущая реализация использует простое разбиение по словам (3+ символа). Для production рекомендуется NER (Named Entity Recognition) или LLM-извлечение.

2. **LLM может пропустить неявные эмоции**: Если пользователь говорит сарказмом ("О, да, Java — лучший язык, конечно"), LLM может неправильно интерпретировать как LOVES.

3. **Нет прогнозирования реакции**: Predictive Processing (Прогноз реакции пользователя) ещё не реализован (планируется в Этапе 2.2).

---

## 🚀 Следующие Шаги

- ✅ **Этап 2.1**: Affective ToM (ЗАВЕРШЁН)
- ⏳ **Этап 2.2**: Predictive Processing (Empathy Feedback Loop)
- ⏳ **Этап 2.3**: Temporal Memory Decay (Забывание старых эмоций)
- ⏳ **Этап 3**: Strategic Protocols (Неискренность, уклонение, омиссия)

---

## 📚 Дополнительные Ресурсы

- **Архитектурная документация**: [docs/r-core/architecture.md](./architecture.md)
- **Код LLM Service**: [src/r_core/infrastructure/llm.py](../../src/r_core/infrastructure/llm.py)
- **Код Memory System**: [src/r_core/memory.py](../../src/r_core/memory.py)
- **Код Pipeline**: [src/r_core/pipeline.py](../../src/r_core/pipeline.py)
