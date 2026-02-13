# Database Migrations

Эта папка содержит SQL-скрипты для миграции схемы БД.

## Как применять миграции:

### 1. Локально (DBeaver)

1. Открой DBeaver.
2. Подключись к `postgresql://rbot:rbot_password@localhost:5433/rbot`.
3. Открой SQL-редактор (SQL Editor).
4. Скопируй содержимое файла миграции (например, `003_short_term_memory_load.sql`).
5. Выполни скрипт (Ctrl+Enter или кнопка Execute).
6. Проверь, что колонки добавлены:
   ```sql
   \d user_profiles
   \d semantic_memory
   ```

### 2. Через psql (командная строка)

```bash
psql postgresql://rbot:rbot_password@localhost:5433/rbot -f migrations/003_short_term_memory_load.sql
psql postgresql://rbot:rbot_password@localhost:5433/rbot -f migrations/004_semantic_memory_embedding.sql
```

### 3. На проде (Amvera)

1. Подключись к продовой БД через psql или DBeaver.
2. Выполни скрипт вручную.

---

## Список миграций:

| # | Файл | Описание | Дата |
| :--- | :--- | :--- | :--- |
| 002 | `002_llm_raw_responses.sql` | Circular buffer для сырых ответов LLM | 2026-02-11 |
| 003 | `003_short_term_memory_load.sql` | Счётчик `short_term_memory_load` для триггера гиппокампа | 2026-02-13 |
| 004 | `004_semantic_memory_embedding.sql` | Добавление `embedding` в `semantic_memory` для дедупликации | 2026-02-13 |

---

## Проверка примененных миграций:

```sql
-- Проверяем, есть ли новые колонки
SELECT column_name, data_type 
FROM information_schema.columns 
WHERE table_name = 'user_profiles' 
AND column_name IN ('short_term_memory_load', 'last_consolidation_at');

SELECT column_name, data_type 
FROM information_schema.columns 
WHERE table_name = 'semantic_memory' 
AND column_name = 'embedding';

-- Просмотр структуры таблиц
\d user_profiles
\d semantic_memory
```

---

## Полезные запросы:

### Посмотреть последние ошибки LLM:
```sql
SELECT 
    timestamp, 
    prompt_type, 
    parse_status, 
    error_message,
    LEFT(raw_response, 200) AS response_preview
FROM llm_raw_responses
WHERE parse_status != 'success'
ORDER BY timestamp DESC
LIMIT 10;
```

### Проверить счётчик гиппокампа:
```sql
SELECT 
    user_id,
    short_term_memory_load,
    last_consolidation_at
FROM user_profiles
WHERE short_term_memory_load > 0
ORDER BY short_term_memory_load DESC;
```

### Посмотреть факты с embedding:
```sql
SELECT 
    id,
    subject,
    predicate,
    object,
    confidence,
    CASE WHEN embedding IS NOT NULL THEN 'YES' ELSE 'NO' END AS has_embedding
FROM semantic_memory
WHERE user_id = 123
ORDER BY created_at DESC
LIMIT 10;
```

### Найти похожие факты (пример pgvector):
```sql
-- Найти 5 ближайших фактов к заданному embedding
SELECT 
    id,
    subject || ' ' || predicate || ' ' || object AS fact,
    1 - (embedding <=> (SELECT embedding FROM semantic_memory WHERE id = 456)) AS similarity
FROM semantic_memory
WHERE user_id = 123
  AND id != 456
  AND embedding IS NOT NULL
ORDER BY similarity DESC
LIMIT 5;
```

### Очистить таблицу (если нужно):
```sql
TRUNCATE TABLE llm_raw_responses;
```
