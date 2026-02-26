# Task 2: Topic Transition Feedback Loop (Micrograph Training)

## Обзор задачи
На Этапе 1 мы создали инфраструктуру графа переходов (`TopicTransitionModel`) и реализовали "Анти-Эхо" фильтр (не даем боту повторять темы).
Цель Этапа 2 — **зациклить процесс (Feedback Loop)**, чтобы `Bifurcation Engine` начал *обучаться* на основе реакции пользователя и использовал эти знания для выбора лучших тем.

## Шаги для локального агента

### 1. Сохранение `pending_transition` при смене темы
В `src/r_core/pipeline.py` в блоке `Bifurcation Engine`, когда бот принимает решение сменить тему и инжектит директиву в промпт (после сортировки `bifurcation_candidates`), необходимо зафиксировать этот факт.

- Добавьте в словарь `self.current_topic_state` новый ключ `pending_transition` (если его нет в `__init__`, добавьте его со значением `None`).
- Когда кандидат выбран, сохраните данные о переходе:
```python
self.current_topic_state["pending_transition"] = {
    "source_embedding": current_embedding,
    "target_embedding": selected_candidate.get("embedding"),
    "transition_type": selected_candidate.get("vector", "unknown"),
    "agent_intent": "casual_chat" # В будущем сюда пойдет реальная интенция
}
```

### 2. Оценка успешности перехода (TopicTracker)
В следующем ходе пользователя нам нужно оценить, насколько хорошо сработал этот переход. Это делается в блоке **TOPIC TRACKER UPDATE** (сразу после вычисления нового значения `TEC`).

Если в `self.current_topic_state` есть `pending_transition`:
1. Вычислите `transition_success` на основе вовлеченности:
   ```python
   # Чем больше TEC и плотность ответа, тем успешнее переход
   response_density = min(len(message.text.split()) / 50.0, 1.0) if message.text else 0.0
   current_tec = self.current_topic_state["tec"]
   
   # Базовая формула успеха (от 0.0 до 1.0)
   transition_success = min(1.0, current_tec * (0.5 + response_density))
   ```
2. Вызовите асинхронный метод `self.hippocampus.update_transition_weight(...)` (см. пункт 3), передав ему данные из `pending_transition` и `transition_success`.
3. Очистите `self.current_topic_state["pending_transition"] = None`.

### 3. Реализация `update_transition_weight` и `get_transition_modifier`
В `src/r_core/hippocampus.py` необходимо добавить два новых метода:

**Метод А: `update_transition_weight`**
- Находит в таблице `topic_transitions` запись по `source_embedding` и `target_embedding` (используя косинусное сходство `< 0.1` или точное совпадение).
- Если запись найдена, обновляет `success_weight` используя экспоненциальное скользящее среднее (EMA):
  `new_weight = old_weight * 0.7 + transition_success * 0.3`
- Увеличивает счетчик `attempts += 1`.
- Если запись не найдена (хотя она должна была быть создана в `save_topic_transition` на Этапе 1), создает её с `success_weight = transition_success`.

**Метод Б: `get_transition_modifier`**
- Принимает `user_id`, `current_embedding` (source), и `candidate_embedding` (target).
- Ищет в БД похожий исторический переход (сходство source < 0.15 и сходство target < 0.15).
- Если переход найден, возвращает модификатор на основе `success_weight`. Например:
  - Если `success_weight > 0.6`, возвращает `1.5` (повышающий коэффициент).
  - Если `success_weight < 0.4`, возвращает `0.5` (понижающий коэффициент).
  - Иначе возвращает `1.0`.
- Если переход не найден, возвращает `1.0`.

### 4. Применение модификатора при выборе темы
В `src/r_core/pipeline.py` в блоке `Bifurcation Engine`:
- Во время подсчета `score` для каждого кандидата (в циклах `for item in semantic_candidates` и т.д.), вызовите (или получите заранее батчем) `transition_modifier = await self.hippocampus.get_transition_modifier(...)`.
- Умножьте итоговый `score` кандидата на этот модификатор: `score *= transition_modifier`.

## Ожидаемый результат
`Bifurcation Engine` начнет предпочитать те переходы (связки тем), которые исторически вызывали у пользователя рост TEC и развернутые ответы, и избегать тех, на которые пользователь отвечал односложно.

## Протокол исполнения
Выполняй изменения, полностью перезаписывая файлы. Не используй сокращения кода (`...`). Отчитайся о статусе после внедрения Feedback Loop.
