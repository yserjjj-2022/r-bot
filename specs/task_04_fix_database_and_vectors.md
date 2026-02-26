# Task 4: Fix UndefinedTableError and JSON double-serialization

## Описание проблемы
Судя по логам с продакшена, есть две критические ошибки:

1. **База данных не была обновлена:** Ошибка `relation "topic_transitions" does not exist`. Таблица не создалась (вероятно, скрипт `tools/init_db.py` не был запущен, или миграция в нем не отработала корректно).
2. **Двойная сериализация JSON:** Эмбеддинги приходят в виде `["[", "-", "0", ".", "0", ...]`. Это означает, что где-то список превратился в строку `"[...]"` и затем эта строка была преобразована в список символов, или `json.dumps()` был вызван дважды.

## Шаги для локального агента

### 1. Фикс двойной сериализации в `src/r_core/hippocampus.py`

В файле `src/r_core/hippocampus.py` метод `_ensure_list` нужно переписать так, чтобы он справлялся со списком строк (символов) и двойной сериализацией.

Найди метод `_ensure_list` и замени его на этот пуленепробиваемый вариант:
```python
    def _ensure_list(self, embedding: Any) -> List[float]:
        """Утилита для гарантии того, что вектор - это список float."""
        import json
        if not embedding:
            return []
            
        # 1. Если это уже список
        if isinstance(embedding, list):
            if len(embedding) > 0:
                # Если первый элемент списка - строка, похожая на "[" (следствие двойного парсинга)
                if isinstance(embedding[0], str) and embedding[0] == "[":
                    # Собираем символы обратно в строку и парсим
                    joined_str = "".join(embedding)
                    try:
                        return json.loads(joined_str)
                    except:
                        pass # Fallback to loop
                        
                # Если первый элемент строка-число (например "0.15")
                if isinstance(embedding[0], str):
                    try:
                        return [float(x) for x in embedding if x not in ('[', ']', ',', ' ')]
                    except:
                        pass
                        
                # Нормальный список float
                if isinstance(embedding[0], (int, float)):
                    return [float(x) for x in embedding]
            return embedding
            
        # 2. Если это numpy массив
        if hasattr(embedding, "tolist"):
            return embedding.tolist()
            
        # 3. Если это строка
        if isinstance(embedding, str):
            try:
                parsed = json.loads(embedding)
                if isinstance(parsed, list):
                    return [float(x) for x in parsed]
                if isinstance(parsed, str): # Двойная сериализация
                    return [float(x) for x in json.loads(parsed)]
            except json.JSONDecodeError:
                pass
                
        return []
```

### 2. Принудительное создание таблицы в `src/r_core/infrastructure/db.py`
Чтобы не зависеть от того, запустил ли пользователь `init_db.py`, давай добавим автоматическое создание таблицы `topic_transitions` при старте сессии, так же, как создаются другие таблицы, если их нет.

В `src/r_core/infrastructure/db.py` найди блок импортов и добавь:
```python
from sqlalchemy import text
```

Дальше, в конец файла `db.py` (или после определения моделей) добавь функцию:
```python
async def init_models():
    """Инициализация моделей и таблиц, которых нет в ORM"""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        
        # Создаем topic_transitions вручную, так как она использует pgvector
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS topic_transitions (
                id SERIAL PRIMARY KEY,
                user_id BIGINT NOT NULL,
                source_embedding vector(1536),
                target_embedding vector(1536),
                transition_type VARCHAR(50),
                agent_intent VARCHAR(255),
                success_weight FLOAT DEFAULT 1.0,
                attempts INTEGER DEFAULT 1,
                last_used_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
            );
            
            -- Индексы не создаем IF NOT EXISTS напрямую, просто игнорим ошибки
        """))
```
*Примечание: убедись, что если функция `init_models` уже существует, просто добавь в неё блок `CREATE TABLE IF NOT EXISTS topic_transitions ...`.*

### 3. Защита от ошибок в `pipeline.py` (Fallback)
В `pipeline.py`, в блоке `Bifurcation Engine` (где вызываются `get_recent_transitions` и `get_transition_modifier`), агент уже обернул вызовы в `try...except`, поэтому падение БД не должно крашить весь пайплайн (как видно по логам, он просто печатает `❌ Error in get_transition_modifier` и продолжает работу). 

**Тебе нужно только обновить `hippocampus.py` и добавить создание таблицы.**
Выполни эти два изменения.
