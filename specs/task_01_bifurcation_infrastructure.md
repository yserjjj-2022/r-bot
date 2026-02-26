# Task 1: Bifurcation Infrastructure & Anti-Looping

## Обзор задачи
Цель этого этапа — заложить фундамент для Микрографа семантических переходов (Topic Transitions) и решить проблему "золотой рыбки" (возврат к исчерпанной теме) в `Bifurcation Engine`.

## Шаги для локального агента

### 1. Обновление базы данных
В файле `src/r_core/infrastructure/db.py` необходимо добавить новую модель для хранения графа переходов.
- **Модель:** `TopicTransitionModel`
- **Таблица:** `topic_transitions`
- **Поля:**
  - `id`: Integer, primary_key
  - `user_id`: Integer, index
  - `source_embedding`: Vector(1536) — вектор исчерпанной темы
  - `target_embedding`: Vector(1536) — вектор предложенного кандидата
  - `transition_type`: String(50) — тип вектора (Semantic, Emotional, Zeigarnik)
  - `agent_intent`: String(100), nullable=True — интенция (цель) агента в момент прыжка
  - `success_weight`: Float, default=0.5 — вес успешности (обновляется по Feedback Loop)
  - `attempts`: Integer, default=1
  - `last_used_at`: DateTime, default=datetime.utcnow

### 2. Извлечение Embeddings в Memory и Hippocampus
Чтобы `Bifurcation Engine` мог сравнивать векторы кандидатов с текущей темой, функции поиска кандидатов должны возвращать `embedding`.
- **Проверить/обновить `src/r_core/hippocampus.py`:** метод `get_semantic_neighbors` должен возвращать `embedding` в составе словаря каждого соседа.
- **Проверить/обновить `src/r_core/hippocampus.py`:** метод `get_zeigarnik_returns` (там нужно извлекать `embedding` из таблицы `episodic_memory`).
- **Проверить/обновить `src/r_core/memory.py`:** метод `get_emotional_anchors` (через `search_by_sentiment`) должен возвращать `embedding`.

### 3. Лечение "Эффекта Золотой Рыбки" (Anti-Looping) в `pipeline.py`
В `src/r_core/pipeline.py` в блоке **Stage 3: The Bifurcation Engine**:
- При итерации по `bifurcation_candidates` добавьте проверку на сходство (Cosine Similarity).
- Текущий центроид лежит в `self.current_topic_state["topic_embedding"]`.
- Вычислите `similarity` между центроидом и `embedding` кандидата. Можно использовать функцию `cosine_distance` (не забудьте перевести distance в similarity, или проверять `distance < 0.35`).
- Если тема слишком похожа (например, cosine similarity `> 0.65` или расстояние `< 0.35`), кандидат должен быть **исключен** из финального пула (не добавляйте его в итоговый список `bifurcation_candidates`).
- Добавьте логирование: `[Bifurcation] Anti-looping triggered: dropped candidate '{candidate_topic}' (similarity={sim:.2f})`.

## Ожидаемый результат
1. При перезапуске приложения Alembic/SQLAlchemy успешно создаст таблицу `topic_transitions`.
2. Если `Bifurcation Engine` срабатывает, бот больше никогда не предложит тему, которая только что обсуждалась.

## Протокол исполнения
Выполняй изменения, полностью перезаписывая файлы. Не используй сокращения кода (`...`). После выполнения задания, отчитайся о статусе.
