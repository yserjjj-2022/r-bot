# Техническое Задание: Исправление SQL-ошибок в Bifurcation Engine

## Контекст проблемы (Bug Report)
В модуле `Hippocampus` (`src/r_core/hippocampus.py`), который отвечает за извлечение памяти для смены темы (Bifurcation Engine), обнаружены две критические SQL-ошибки. Они блокируют нормальную работу поиска ассоциаций при активации тонического режима Locus Coeruleus (TEC < 0.3).

**Ошибка 1:** В методе `get_semantic_neighbors` происходит сбой парсера SQLAlchemy (asyncpg): `syntax error at or near ":"`. 
Это происходит из-за того, что в оригинальном запросе (вероятно, до чьих-то правок) использовались позиционные параметры `$1, $2`, а в текущем коде используются именованные параметры `:emb, :limit, :user_id`. SQLAlchemy/asyncpg путается, когда видит синтаксис `vector_cosine_ops(embedding, :emb::vector)` — кастование типов `::vector` рядом с именованным параметром часто вызывает проблемы в asyncpg. 

К тому же, таблица `semantic_memory` не имеет полей `topic` и `content`. У нее есть `subject`, `predicate`, `object`.

**Ошибка 2:** В методе `get_zeigarnik_returns` возникает ошибка `column "emotion_score" does not exist`. Запрос обращается к таблице `chat_history`, пытаясь прочитать колонку `emotion_score`, которой там нет. Эмоции в нашей архитектуре хранятся в таблице `episodic_memory`.

## Цель
Исправить оба SQL-запроса в `src/r_core/hippocampus.py`, чтобы модуль `Bifurcation Engine` мог без ошибок получать кандидатов на смену темы (Semantic Neighbors и Zeigarnik Returns).

---

## Инструкции по реализации (STRICT)

### Часть 1. Исправление метода `get_semantic_neighbors` (Файл `src/r_core/hippocampus.py`)

1. Найдите метод `get_semantic_neighbors`.
2. Измените SQL-запрос. Используйте конкатенацию `subject`, `predicate`, `object` вместо несуществующего поля `content`. Уберите несуществующее поле `topic`.
3. Чтобы обойти баг SQLAlchemy с `::vector` кастованием именованных параметров, используйте функцию кастования `CAST(:emb AS vector)` вместо синтаксиса `::vector`. Оператор `<=>` стандартный для pgvector и работает надежнее функции `vector_cosine_ops`.

**Код для замены:**

```python
    async def get_semantic_neighbors(self, user_id: int, current_embedding: List[float], limit: int = 3) -> List[Dict[str, Any]]:
        """
        Vector 1: Semantic Neighbor
        
        Finds related semantic memories using vector similarity (Cosine Distance).
        Returns items where distance is between 0.35 and 0.65 (related, but not identical).
        """
        async with AsyncSessionLocal() as session:
            try:
                emb_str = self._serialize_vector(current_embedding)
                if not emb_str:
                    return []
                
                # ИЗМЕНЕНИЯ:
                # 1. Используем subject, predicate, object вместо topic/content
                # 2. Используем оператор <=> вместо vector_cosine_ops и CAST для безопасного кастования
                result = await session.execute(
                    text("""
                        SELECT id, subject, predicate, object, 
                               (embedding <=> CAST(:emb AS vector)) as distance
                        FROM semantic_memory
                        WHERE user_id = :user_id
                          AND embedding IS NOT NULL
                          AND (embedding <=> CAST(:emb AS vector)) BETWEEN 0.35 AND 0.65
                        ORDER BY distance ASC
                        LIMIT :limit
                    """),
                    {"user_id": user_id, "emb": emb_str, "limit": limit}
                )
                rows = result.fetchall()
                
                neighbors = []
                for row in rows:
                    content_str = f"{row[1]} {row[2]} {row[3]}" # Сборка контента из триплета
                    neighbors.append({
                        "id": row[0],
                        "topic": row[1], # Имитация topic для совместимости с BifurcationEngine
                        "content": content_str,
                        "distance": row[4],
                        "vector_type": "semantic_neighbor"
                    })
                
                print(f"[Hippocampus] get_semantic_neighbors: Found {len(neighbors)} neighbors for user {user_id}")
                return neighbors
                
            except Exception as e:
                print(f"[Hippocampus] ❌ Error in get_semantic_neighbors: {e}")
                return []
```

### Часть 2. Исправление метода `get_zeigarnik_returns` (Файл `src/r_core/hippocampus.py`)

1. Найдите метод `get_zeigarnik_returns`.
2. Измените таблицу с `chat_history` на `episodic_memory`. Таблица эпизодической памяти (`EpisodicModel`) специально создана для хранения поля `emotion_score` и содержит сырой текст (`raw_text`), а не `content`. У нее нет поля `prediction_error`, поэтому будем опираться только на `emotion_score`.

**Код для замены:**

```python
    async def get_zeigarnik_returns(self, user_id: int, limit: int = 3) -> List[Dict[str, Any]]:
        """
        Vector 3: Zeigarnik Return
        
        Finds recent episodic memories with high emotion_score (unresolved tension).
        These are "unfinished business" topics that the user might want to return to.
        """
        async with AsyncSessionLocal() as session:
            try:
                # ИЗМЕНЕНИЯ:
                # Читаем из episodic_memory, где есть поле emotion_score. 
                # У episodic_memory поле текста называется raw_text
                result = await session.execute(
                    text("""
                        SELECT id, raw_text, emotion_score, created_at
                        FROM episodic_memory
                        WHERE user_id = :user_id
                          AND (emotion_score > 0.7 OR emotion_score < -0.7)
                        ORDER BY created_at DESC
                        LIMIT :limit
                    """),
                    {"user_id": user_id, "limit": limit}
                )
                rows = result.fetchall()
                
                zeigarnik_returns = []
                for row in rows:
                    zeigarnik_returns.append({
                        "id": row[0],
                        "content": row[1], # Мапим raw_text в content для совместимости
                        "emotion_score": row[2],
                        "created_at": row[3],
                        "vector_type": "zeigarnik_return"
                    })
                
                print(f"[Hippocampus] get_zeigarnik_returns: Found {len(zeigarnik_returns)} unresolved topics for user {user_id}")
                return zeigarnik_returns
                
            except Exception as e:
                print(f"[Hippocampus] ❌ Error in get_zeigarnik_returns: {e}")
                return []
```

---

## Протокол Безопасности (CRITICAL)
- **SAFETY PROTOCOL B:** При редактировании файлов вы обязаны предоставить ПОЛНЫЙ, исполняемый код файла `src/r_core/hippocampus.py`. Использование плейсхолдеров (`# ... existing code ...`) СТРОГО ЗАПРЕЩЕНО. 
- Убедитесь, что отступы сохранены корректно (4 пробела для уровня внутри класса/метода).