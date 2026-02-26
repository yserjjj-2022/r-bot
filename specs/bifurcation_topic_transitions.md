# R-Bot Architectural Spec: Topic Transition Micrograph (Bifurcation v2.0)

## 1. Концепция: Vector/Symbolic Reinforcement Learning
Вместо того чтобы штрафовать негативные эмоциональные якоря (токсичный позитив), `Bifurcation Engine` должен оценивать успешность перехода между темами на основе реальной вовлеченности пользователя (TEC). 

Мы создаем микрограф переходов `topic_transitions` (source_topic -> target_topic). Успех перехода обновляется без участия LLM — только за счет метрик предсказательной ошибки (PE) и плотности ответа.

---

## 2. Модификация Базы Данных (`infrastructure/db.py`)
Нужно добавить новую таблицу для хранения микрографа переходов.

```python
from sqlalchemy import Column, Integer, Float, String, DateTime
from pgvector.sqlalchemy import Vector
from datetime import datetime

class TopicTransitionModel(Base):
    __tablename__ = "topic_transitions"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, index=True)
    
    # Откуда переходили (вектор исчерпанной темы)
    source_embedding = Column(Vector(1536))
    
    # Куда попытались переключиться (вектор предложенного якоря)
    target_embedding = Column(Vector(1536))
    
    # Тип прыжка (Zeigarnik, Emotional, Semantic)
    transition_type = Column(String(50))
    
    # Интенция агента в момент прыжка (для ролевых ботов: "broker_sell", "avatar_support" и т.д.)
    # Пока может быть None или "casual_chat"
    agent_intent = Column(String(100), nullable=True)
    
    # Насколько это было успешно (от 0.0 до 1.0)
    success_weight = Column(Float, default=0.5)
    
    attempts = Column(Integer, default=1)
    last_used_at = Column(DateTime, default=datetime.utcnow)
```

## 3. Модификация `Bifurcation Engine` (`pipeline.py`)

### Задача А: Исключение "Эффекта Золотой Рыбки" (Anti-looping Penalty)
Когда `Bifurcation Engine` собирает кандидатов, он должен сверять их векторы (`embedding`) с текущим `current_topic_embedding`.
- Рассчитать косинусное расстояние (similarity).
- Если `similarity > 0.65` (тема слишком похожа на текущую исчерпанную), кандидат получает жесткий штраф: `score = score * 0.1` или полностью исключается.

### Задача Б: Применение микрографа переходов (Vector Search)
При оценке `score` каждого кандидата, нужно делать запрос к `topic_transitions`:
- Найти исторические переходы с похожим `source_embedding` и похожим `target_embedding` в контексте текущего `agent_intent`.
- Если такой переход был успешен (`success_weight > 0.6`), умножить `score` кандидата на повышающий коэффициент.
- Если переход приводил к провалу (`success_weight < 0.4`), умножить на понижающий коэффициент.

### Задача В: Фиксация попытки перехода (Pending Evaluation)
Когда Bifurcation Engine выбирает тему и инжектит директиву, мы сохраняем это состояние в `current_topic_state`:
```python
self.current_topic_state["pending_transition"] = {
    "source_embedding": old_topic_embedding,
    "target_embedding": selected_candidate["embedding"],
    "transition_type": selected_candidate["vector_type"],
    "agent_intent": current_agent_intent # из профиля или контекста
}
```

## 4. Замыкание петли (Hippocampus Feedback)
В начале следующего хода (когда пользователь отвечает), `TopicTracker` оценивает новый уровень TEC.
Если был активен `pending_transition`:
- Считаем `transition_success = current_TEC * response_density`.
- Сохраняем или обновляем запись в `topic_transitions` (upsert с использованием Exponential Moving Average: `new_weight = old_weight * 0.7 + transition_success * 0.3`).

## 5. Результат
1. Бот перестанет возвращаться к темам, которые только что обсуждались.
2. Бот научится интуитивно подбирать типы тем под каждого пользователя.
3. Система готова к внедрению целеполагания (Agent Intentions): граф сможет строить маршруты диалога для выполнения конкретных задач (например, подвести к продаже).
