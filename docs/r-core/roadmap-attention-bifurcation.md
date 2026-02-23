# 📍 План Перехода на Процессинг с TEC и Bifurcation Engine

**Статус**: 📐 Architectural Plan  
**Дата**: 23.02.2026  
**Теоретическая база**: [attention-engagement-theory.md](./attention-engagement-theory.md)  
**Техническая детализация**: … отдельный документ после ревью кода

---

## 1. Что мы меняем и почему

### Проблема (устраняем)

Диалог в R-Core сейчас обрабатывается как последовательность реплик: **тема N => PE низок => паттерн усиливается => тема N+1 тоже**. Это создаёт «петлю темы» — чем дольше говорим о X, тем увереннее система продолжает X. Человек устроен иначе.

### Что мы добавляем

Мы вводим два новых основных принципа обработки диалога:

1. **Topic Engagement Capacity (TEC)**: диалог всегда работает в двух измерениях: ЧТО говорят И насколько ещё вовлечёны в это.
2. **Bifurcation Engine**: система не ждёт, пока пользователь переключится, а предсказывает момент и направление перехода.

---

## 2. Принципиальные изменения в архитектуре

### 2.1 Модель данных: расширение Volitional Pattern

Каждый VolitionalPattern получает новое состояние:

```
NEW FIELDS in VolitionalPattern:
  topic_engagement: float = 1.0     # TEC: 0.0-1.0
  base_decay_rate: float = 0.12     # базовый decay за ход
  complexity_modifier: float = 1.0  # >1.0 для технических тем
  emotional_load: float = 0.0       # >0.5 для травматичных тем
  recovery_rate: float = 0.05       # восстановление TEC
```

### 2.2 Новый принцип Reinforcement

Старая логика (v2.x):
```
IF PE < 0.2: pattern.learned_delta += rate
```

Новая логика (v3.0):
```
IF PE < 0.2 AND pattern.topic_engagement > 0.5:
    pattern.learned_delta += rate
# Если TEC < 0.5: reinforcement заморожен, даже если PE низок

# ВСЕГДА:
pattern.topic_engagement -= effective_decay
```

### 2.3 Новый компонент Pipeline: Bifurcation Detector

```
IF pattern.topic_engagement < threshold_bifurcation:
    hypotheses = bifurcation_engine.generate(user_id, current_topic)
    winner = bifurcation_engine.arbitrate(hypotheses)
    IF tonic_ne > 0.5 AND winner.score > 0.6:
        inject_proactive_mirror(winner.topic, winner.bridge_phrase)
```

### 2.4 Двусторонняя связь с Нейромодуляцией

```
IF TEC < 0.3:
    neuromodulation.tonic_ne_boost += (0.3 - TEC) x 2.5
    => архетип сдвигается к SURPRISE/SEEKING
    => Prefrontal агент получает +10% score
```

---

## 3. Этапы реализации

### Этап 1: TEC Decay (2-3 дня)

**Цель**: Ввести TEC-переменную в модель данных и выправить PE-reinforcement.

Изменяемые файлы:
- `models.py` / VolitionalPattern: 5 новых полей.
- `pipeline.py` / `_update_volitional_patterns()`: вызов `update_tec()` после каждой реплики.
- `pipeline.py` / `_apply_reinforcement()`: проверка TEC > 0.5 перед reinforcement.
- Миграция БД: новая колонка `topic_engagement` в `volitional_patterns`.
- Логирование: `rcore_metrics` + поля `tec_value`, `tec_decay_effective`.

**KPI**: TEC падает до < 0.5 за 5-7 подряд однотемных реплик.

---

### Этап 2: LC-NE Integration (2 дня)

**Цель**: Подключить TEC к нейрогормональному слою.

Изменяемые файлы:
- `neuromodulation.py` / `metabolize()`: вход `tec_value`. При `tec < 0.3` — Tonic NE boost.
- `neuromodulation.py`: новый метод `get_lc_mode()` → `"phasic"` | `"tonic"`.
- `pipeline.py` / `_apply_hormonal_modulation()`: при `lc_mode == "tonic"` — Prefrontal агент +10%.
- Логирование: поле `lc_mode` в `rcore_metrics`.

**KPI**: При TEC < 0.3 — архетип `SURPRISE/SEEKING` срабатывает в нейромодуляции.

---

### Этап 3: Bifurcation Engine (3-5 дней)

**Цель**: Интеллектуально предсказывать, на какую тему переключится пользователь.

Изменяемые файлы:
- `memory.py`: новый метод `get_bifurcation_hypotheses(user_id, current_topic)`. 
  Возвращает 3 гипотезы:
  - H1 (Semantic): ближайший узел в semantic_memory (косинус > 0.65).
  - H2 (Emotional): Formative Anchor с макс. |valence| x amygdala_intensity.
  - H3 (Zeigarnik): тема из chat_history, оборванная при высоком PE.
- `pipeline.py`: новый метод `_run_bifurcation_engine()`.
- `llm.py` / `generate_response()`: параметр `proactive_topic_bridge`.

Логирование (JSON в rcore_metrics):
```
{
  "event": "bifurcation_detected",
  "tec_at_bifurcation": 0.27,
  "predicted_vector": "semantic",
  "predicted_topic": "Rust",
  "actual_topic_switched": null
}
```
POST-факт: после следующей реплики `actual_topic_switched` заполняется фактом — для валидации.

**KPI**: точность предсказания вектора > 60% через 100 диалогов.

---

### Этап 4: Proactive Mirroring (2 дня)

**Цель**: Бот инициативно предлагает новую тему, снимая когнитивную нагрузку с пользователя.

Изменяемые файлы:
- `llm.py`: новый prompt-блок [BIFURCATION BRIDGE].
- Два режима: Passive (TEC 0.3-0.5) vs Active (TEC < 0.3).

Логирование:
```
{
  "event": "proactive_mirror",
  "switch_type": "active",
  "source_topic": "Python",
  "target_topic": "Rust",
  "vector": "semantic",
  "bridge_accepted": true
}
```

**KPI**: пользователь подхватывает предложенную тему > 50%.

---

### Этап 5: Dashboard + Аналитика (2 дня)

**Цель**: визуализация TEC + валидация Bifurcation Engine.

Изменяемые файлы:
- `app_streamlit.py`: новая секция "TEC Monitor":
  - Бар TEC для каждой активной темы.
  - Таблица bifurcation events с процентом совпадений.
  - Кнопка отключения Proactive Mirroring (для A/B тестирования).

**KPI**: Bifurcation accuracy > 60% видна на дашборде.

---

## 4. Что НЕ меняем в этом цикле

- Структура Council Report / парламент агентов — не меняем.
- TTL-механизм (Topic Fatigue) — остаётся как fallback для быстрых фазических тем.
- Логика semantic_memory / Anchors / chat_history — не меняем, только добавляем метод `get_bifurcation_hypotheses()`.
- Шкала гормонов и куб Лёвхайма — не меняем.

---

## 5. Схема потока данных

```
Пользователь пишет реплику
          |
    pipeline.py
          |
    [1] update_tec(pattern, pe, response_density)
          | => TEC в VolitionalPattern
    [2] neuromodulation.apply_tec(tec)
          | => Tonic NE boost если TEC < 0.3
          | => архетип SURPRISE/SEEKING
    [3] IF tec < threshold:
              bifurcation_engine.generate()
              bifurcation_engine.arbitrate()
          |
    [4] IF winner.score > 0.6:
              llm.inject_proactive_bridge()
          |
    [5] metrics.log(tec, lc_mode, bifurcation)
          |
    Ответ пользователю
```

---

## 6. Связанные файлы и изменения

| Файл | Изменения |
|------|----------|
| `src/r_core/models.py` | Добавить поля TEC в VolitionalPattern |
| `src/r_core/pipeline.py` | `update_tec()`, `_run_bifurcation_engine()`, `inject_proactive_bridge()` |
| `src/r_core/memory.py` | `get_bifurcation_hypotheses()` |
| `src/r_core/infrastructure/neuromodulation.py` | `apply_tec()`, `get_lc_mode()` |
| `src/r_core/infrastructure/llm.py` | Параметр `proactive_topic_bridge` в `generate_response()` |
| `app_streamlit.py` | Секция TEC Monitor |
| Миграция БД | Колонка `topic_engagement` в `volitional_patterns` |
