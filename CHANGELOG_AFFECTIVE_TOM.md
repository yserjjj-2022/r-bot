# 🎉 Affective Theory of Mind — Changelog

**Дата**: 07.02.2026  
**Ветка**: `r-core-kernel-prototype`  
**Статус**: ✅ **РЕАЛИЗОВАНО**

---

## 📦 Что Добавлено

### 1. Расширение Базы Данных

**Файл**: [`src/r_core/infrastructure/db.py`](src/r_core/infrastructure/db.py)

- ✅ Добавлено поле `sentiment: JSONB` в модель `SemanticModel`
- ✅ Автоматическая миграция при `init_models()`:
  - `ALTER TABLE semantic_memory ADD COLUMN sentiment JSONB`
  - `CREATE INDEX idx_semantic_sentiment ON semantic_memory USING GIN (sentiment)`
- ✅ Добавлены метрики в `MetricsModel`:
  - `affective_triggers_detected: int`
  - `sentiment_context_used: bool`

**Коммит**: `f3ec83e` (ранее в истории ветки)

---

### 2. LLM Service — Извлечение Эмоций

**Файл**: [`src/r_core/infrastructure/llm.py`](src/r_core/infrastructure/llm.py)

- ✅ Секция **"AFFECTIVE EXTRACTION"** в `generate_council_report()`:
  - Определяет ключевые слова: `loves`, `hates`, `fears`, `enjoys`, `despises`, `adores`
  - Возвращает JSON с полями: `subject`, `predicate`, `object`, `intensity`
- ✅ Параметр `affective_context: str` в `generate_response()`:
  - Инъекция warnings в system prompt
  - Формат: `⚠️ AVOID mentioning 'X' (User HATES it)`

**Коммит**: `cc639ab`

---

### 3. Memory System — Сохранение и Поиск Sentiment

**Файл**: [`src/r_core/memory.py`](src/r_core/memory.py)

- ✅ Метод `get_sentiment_for_entity(user_id, entity)`:
  - SQL-запрос с `sentiment IS NOT NULL`
  - Возвращает словарь: `{entity, predicate, sentiment, intensity}`
- ✅ Метод `_extract_affective_context(user_id, text)`:
  - Извлекает слова из текста (3+ символа)
  - Проверяет каждое через `get_sentiment_for_entity()`
  - Возвращает список `affective_warnings` для промпта
- ✅ Обновление `save_semantic()`:
  - Поддержка параметра `sentiment` в `SemanticTriple`
  - Сохранение в JSONB-поле БД

**Коммит**: `bc78f6a`

---

### 4. Pipeline — Обработка Affective Extraction

**Файл**: [`src/r_core/pipeline.py`](src/r_core/pipeline.py)

- ✅ Обработка `council_report["affective_extraction"]`:
  - Преобразование `intensity` → VAD-формат:
    - `HATES` → `valence: -intensity`
    - `LOVES` → `valence: +intensity`
    - `FEARS` → `valence: -intensity, arousal: 0.5, dominance: -0.2`
  - Создание `SemanticTriple` с полем `sentiment`
  - Сохранение через `memory.store.save_semantic()`
- ✅ Формирование `affective_context_str` из `context["affective_context"]`:
  - Для NEGATIVE: `⚠️ AVOID mentioning 'entity'`
  - Для POSITIVE: `💚 User LOVES 'entity'`
- ✅ Передача `affective_context_str` в `llm.generate_response()`
- ✅ Логирование метрик:
  - `affective_triggers_detected` — счётчик извлечённых эмоций
  - `sentiment_context_used` — флаг использования контекста

**Коммит**: `62443a5`

---

### 5. Streamlit UI — Визуализация

**Файл**: [`app_streamlit.py`](app_streamlit.py)

- ✅ Новая функция `get_affective_memory(user_id)`:
  - SQL-запрос к `semantic_memory` с фильтром `sentiment IS NOT NULL`
  - Возвращает последние 20 записей
- ✅ Sidebar секция **"💚 Emotional Memory"**:
  - Expander "View User Preferences"
  - Отображение эмодзи на основе `predicate`:
    - 🔴 `HATES`, `DESPISES`
    - 😨 `FEARS`
    - 💚 `LOVES`, `ADORES`
    - 😊 `ENJOYS`
- ✅ Индикатор в чате:
  - `💚 Sentiment Context Used (X triggers)` под каждым ответом
  - Показывается только если `sentiment_context_used == True`

**Коммит**: `2d24134` ([commit link](https://github.com/yserjjj-2022/r-bot/commit/2d24134e40024279610d64ec653d4c983d76c68a))[cite:33]

---

### 6. Тестовый Скрипт

**Файл**: [`tests/test_affective_tom_manual.py`](tests/test_affective_tom_manual.py)

- ✅ Консольный тест:
  1. Отправка "Я ненавижу Java"
  2. Проверка сохранения sentiment в БД
  3. Отправка "Какой язык использовать?"
  4. Проверка, что бот избегает упоминания Java

**Запуск**:
```bash
python tests/test_affective_tom_manual.py
```

**Коммит**: `7a636d9` ([commit link](https://github.com/yserjjj-2022/r-bot/commit/7a636d9acf8b19b88c1dfcd38427d1682773dc25))[cite:34]

---

### 7. Документация

**Файл**: [`docs/affective-tom-guide.md`](docs/affective-tom-guide.md)

- ✅ Руководство пользователя:
  - Архитектура (Extraction → Storage → Recall → Injection)
  - Тестирование через Streamlit UI
  - Метрики и расширенные возможности
  - Известные ограничения

**Коммит**: `2651a52` ([commit link](https://github.com/yserjjj-2022/r-bot/commit/2651a52a46ff663daab0c3cb31d8cb01c804011b))[cite:35]

---

## 🧪 Тестирование

### Ручное Тестирование (Streamlit)

1. **Запустить UI**:
   ```bash
   streamlit run app_streamlit.py
   ```

2. **Инициализировать БД** (если ещё не сделано):
   - Нажать **"Initialize DB"** в sidebar

3. **Тестовый диалог**:
   ```
   User: Я ненавижу Java
   Bot: [извлекает sentiment, сохраняет в БД]
   
   User: Какой язык программирования использовать?
   Bot: [избегает упоминания Java, рекомендует Python/Go/Rust]
   ```

4. **Проверка в UI**:
   - В sidebar открыть **"💚 Emotional Memory"**
   - Должна быть запись: `🔴 HATES Java (V: -0.90)`
   - В ответе бота: `💚 Sentiment Context Used (1 triggers)`

### Автоматическое Тестирование

```bash
python tests/test_affective_tom_manual.py
```

**Ожидаемый вывод**:
```
🧠 Affective Theory of Mind Test
============================================================
[1/5] Initializing database...
✅ Database ready

[2/5] Creating R-Core Kernel...
✅ Kernel initialized

[3/5] Sending test message: 'I HATE Java programming language'
🤖 Bot Response: ...
📊 Stats:
  - Affective Triggers Detected: 1

[4/5] Checking semantic memory...
✅ Sentiment found in memory:
  - Entity: Java
  - Predicate: HATES
  - Valence: -0.90

[5/5] Sending follow-up: 'What programming language should I use?'
🤖 Bot Response: ...
✅ SUCCESS: Bot avoided mentioning Java (respecting user's preference)
============================================================
✅ Test Completed
```

---

## 📊 Метрики

### В `internal_stats` каждого ответа:

```json
{
  "latency_ms": 1234,
  "winner_score": 7.5,
  "affective_triggers_detected": 1,
  "sentiment_context_used": true,
  "mood_state": "V:0.12 A:0.05 D:0.00"
}
```

### В таблице `rcore_metrics` (если включено логирование):

```sql
SELECT 
  timestamp,
  affective_triggers_detected,
  sentiment_context_used,
  payload
FROM rcore_metrics
WHERE sentiment_context_used = TRUE
ORDER BY timestamp DESC
LIMIT 10;
```

---

## 🚀 Следующие Шаги

- ✅ **Этап 2.1**: Affective ToM (Theory of Mind) — **ЗАВЕРШЁН**
- ⏳ **Этап 2.2**: Predictive Processing (Empathy Feedback Loop)
  - Прогноз реакции пользователя
  - Сравнение с реальной реакцией
  - Обратная связь в Mood System
- ⏳ **Этап 2.3**: Temporal Memory Decay
  - Формула Эббингауза для "остывания" эмоций
  - Старые обиды забываются, свежие — сильнее влияют
- ⏳ **Этап 3**: Strategic Protocols (Неискренность)
  - Face-Saving (белая ложь)
  - Deflection (уклонение от опасных вопросов)
  - Omission (недосказанность)

---

## 🔗 Полезные Ссылки

- **Основная документация**: [docs/r-core.md](docs/r-core.md)
- **Руководство по Affective ToM**: [docs/affective-tom-guide.md](docs/affective-tom-guide.md)
- **Репозиторий**: [github.com/yserjjj-2022/r-bot](https://github.com/yserjjj-2022/r-bot)
- **Ветка**: [r-core-kernel-prototype](https://github.com/yserjjj-2022/r-bot/tree/r-core-kernel-prototype)

---

## 🙏 Благодарности

Реализация выполнена в соответствии с планом развития R-Core, описанным в session summary от 07.02.2026.

**Автор**: Sergey Ershov (yserjjj-2022)  
**Дата завершения**: 07.02.2026, 17:19 MSK
