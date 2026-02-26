# Bugfix: Topic Transitions Graph Error

## Обзор проблемы
В логах появилась ошибка при работе `Bifurcation Engine` с таблицей `topic_transitions`:
1. `UndefinedTableError: relation "topic_transitions" does not exist`. Таблица не создана в PostgreSQL.
2. Проблема двойной сериализации вектора: вектор передается в `get_transition_modifier` уже в виде строки, а `json.dumps()` в `_serialize_vector` превращает её в массив символов `["[", "-", "0", ...]`.

Система не упала благодаря блокам `try/except`, но функционал Feedback Loop и Anti-Looping игнорируется.

## Задачи для локального агента

### Шаг 1: Добавление миграции SQL
Убедитесь, что миграция для создания таблицы физически существует. В папке `src/r_core/infrastructure/` или `migrations/` (в зависимости от структуры проекта) должен быть файл `.sql`, который применяется при старте, либо SQL-код должен быть добавлен в инициализацию базы данных.

Если в проекте используется файл для инициализации таблиц (например, `init_db.py` или сырой `schema.sql`), добавьте туда DDL-запрос. Если используется `alembic`, сгенерируйте ревизию.
*(Если в проекте нет системы миграций, добавьте создание таблицы в `src/r_core/infrastructure/db.py` в функцию `init_db`)*.

**Схема таблицы (PostgreSQL):**
```sql
CREATE TABLE IF NOT EXISTS topic_transitions (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL,
    source_embedding vector(1536), -- Замените 1536 на размерность вашей модели (например, 768)
    target_embedding vector(1536),
    transition_type VARCHAR(50),
    agent_intent VARCHAR(50),
    success_weight FLOAT DEFAULT 0.5,
    attempts INTEGER DEFAULT 1,
    last_used_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_topic_transitions_user ON topic_transitions(user_id);
```

### Шаг 2: Починка двойной сериализации векторов
Проблема локализована в `src/r_core/pipeline.py` в блоке `Bifurcation Engine`, когда вызывается `self.hippocampus.get_transition_modifier(..., item.get("embedding"))`. Из БД векторы иногда возвращаются в виде строки, а метод `_serialize_vector` в `hippocampus.py` ожидает только списки (List[float]).

**Правка в `src/r_core/hippocampus.py`:**
Сделайте метод `_ensure_list` абсолютно пуленепробиваемым:
```python
def _ensure_list(self, embedding: Any) -> List[float]:
    """Helper to ensure embedding is a python list, not numpy array or string"""
    if embedding is None:
        return []
    if isinstance(embedding, str):
        try:
            import json
            return json.loads(embedding)
        except:
            return []
    if hasattr(embedding, 'tolist'):
        return embedding.tolist()
    if isinstance(embedding, list):
        return embedding
    return []
```

### Шаг 3: Проверка типов в `pipeline.py`
В `src/r_core/pipeline.py` перед вызовом `is_recently_exhausted` и `get_transition_modifier` убедитесь, что `current_embedding` также является списком, а не numpy массивом.
```python
# Если current_embedding это numpy array, переведите его в list перед передачей в hippocampus
if hasattr(current_embedding, 'tolist'):
    current_emb_list = current_embedding.tolist()
else:
    current_emb_list = current_embedding
```
*(Используйте `current_emb_list` вместо `current_embedding` во всех вызовах методов `hippocampus` в блоке Bifurcation)*.

## Инструкции по выполнению
Выполняй изменения, полностью перезаписывая файлы `src/r_core/hippocampus.py` и `src/r_core/pipeline.py` (никаких `# ... rest of code ...`).
Проверь, где именно в проекте создаются таблицы, и добавь DDL для `topic_transitions`.
