# Database Migrations

Эта папка содержит SQL-скрипты для миграции схемы БД.

## Как применять миграции:

### 1. Локально (DBeaver)

1. Открой DBeaver.
2. Подключись к `postgresql://rbot:rbot_password@localhost:5433/rbot`.
3. Открой SQL-редактор (SQL Editor).
4. Скопируй содержимое файла миграции (например, `002_llm_raw_responses.sql`).
5. Выполни скрипт (Ctrl+Enter или кнопка Execute).
6. Проверь, что таблица создана:
   ```sql
   \dt llm_raw_responses
   ```

### 2. Через psql (командная строка)

```bash
psql postgresql://rbot:rbot_password@localhost:5433/rbot -f migrations/002_llm_raw_responses.sql
```

### 3. На проде (Amvera)

1. Подключись к продовой БД через psql или DBeaver.
2. Выполни скрипт вручную.

---

## Список миграций:

| # | Файл | Описание | Дата |
| :--- | :--- | :--- | :--- |
| 002 | `002_llm_raw_responses.sql` | Circular buffer для сырых ответов LLM | 2026-02-11 |

---

## Проверка примененных миграций:

```sql
-- Проверяем, есть ли таблица
SELECT table_name 
FROM information_schema.tables 
WHERE table_schema = 'public' 
AND table_name = 'llm_raw_responses';

-- Просмотр структуры таблицы
\d llm_raw_responses
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

### Посмотреть количество записей в буфере:
```sql
SELECT COUNT(*) AS total_records FROM llm_raw_responses;
```

### Очистить таблицу (если нужно):
```sql
TRUNCATE TABLE llm_raw_responses;
```
