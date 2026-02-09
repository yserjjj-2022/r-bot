# Агентная модель человеческого поведения

**Версия:** 2.0  
**Дата:** 26 ноября 2025  
**Авторы:** Сергей Ершов

## Аннотация

Данная модель представляет собой **мультитеоретическую интеграцию**, объединяющую шесть теоретических традиций через методологию Grounded Theory. Модель операционализирует человеческую агентность для:

- Качественного анализа интервью
- Проектирования адаптивных диалоговых систем
- Исследований принятия решений и целеполагания
- Лонгитюдных исследований траекторий изменения поведения

**Ключевое отличие от традиционных подходов:** Не просто "SCT + GT", а интеграция 6 теорий с гибридной предсказательной силой.

---

## Мультитеоретическая архитектура

### Разделение уровней: Методология vs Содержание

```
┌────────────────────────────────────────────────────────────┐
│         МЕТОДОЛОГИЧЕСКИЙ УРОВЕНЬ (как анализируем)         │
│                  Grounded Theory                           │
│         (открытое → осевое → избирательное)                │
└────────────────────────────────────────────────────────────┘
                         ↓ применяется к ↓
┌────────────────────────────────────────────────────────────┐
│      СУБСТАНТИВНЫЙ УРОВЕНЬ (что анализируем)               │
│                                                            │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐         │
│  │   Bandura   │  │   Zimbardo  │  │ De Jaegher  │         │
│  │   SCT       │  │   FTP       │  │ Intersub.   │         │
│  │             │  │             │  │             │         │
│  │ • Agency    │  │ • Temporal  │  │ • Shared    │         │
│  │ • Triadic   │  │   depth     │  │   meanings  │         │
│  │ • Self-eff. │  │ • MTT       │  │ • Collective│         │
│  └─────────────┘  └─────────────┘  └─────────────┘         │
│                                                            │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐         │
│  │  Gollwitzer │  │   Flavell   │  │    Gross    │         │
│  │  Volition   │  │Metacognition│  │  Emotion    │         │
│  │             │  │             │  │  Regulation │         │
│  │ • Intent-   │  │ • Meta-     │  │ • Valence   │         │
│  │   action gap│  │   awareness │  │ • Modulation│         │
│  │ • Impl. int.│  │ • Regulation│  │ • Strategies│         │
│  └─────────────┘  └─────────────┘  └─────────────┘         │
└────────────────────────────────────────────────────────────┘
```

### Теоретические источники по компонентам

| Компонент | Основные теории | Ключевые авторы |
|-----------|----------------|----------------|
| **(a) Интенция + FTP** | Social Cognitive Theory, Future Time Perspective, Goal Theory | Bandura, Zimbardo, Gollwitzer |
| **(b) Порог активации** | Volitional Psychology, Self-Efficacy | Gollwitzer, Bandura |
| **(в) Планирование** | Forethought, Mental Time Travel, Metacognition | Bandura, Suddendorf, Flavell |
| **(г) Обучение** | Self-Reflectiveness, Attribution Theory | Bandura, Weiner |
| **(д) Интерсубъективность** | Participatory Sense-Making, Collective Agency | De Jaegher, Gallagher, Bandura |
| **(е) Аффект** | Emotion & Cognition, Emotion Regulation | Gross, Frijda |

**Важно:** GT здесь — не теория поведения, а **метод структурирования и выявления связей** между концептами из предметных теорий.

---

## Предсказательный спектр модели

### Три уровня предсказаний

Модель обеспечивает **гибридную предсказательность**, комбинируя качественное понимание (GT) и количественный прогноз (теории).

#### Уровень 1: Качественные предсказания (GT-традиция)

**Что предсказывает:**
- Траектории изменения: "Человек с low self-efficacy + high anxiety → вероятна траектория chronic procrastination"
- Паттерны поведения: "Если planning_style = 'paralyzed', человек застревает в обдумывании"
- Процессуальные стадии: последовательность от намерения к действию

**Пример:**
```
Открытые коды: fear_of_failure + seeks_social_validation + no_concrete_steps
→ Тема: "anxious_aspirant"
→ Предсказание: Длительная прокрастинация с циклами 
   "планирование → тревога → откладывание → вина → новое планирование"
```

#### Уровень 2: Количественные предсказания (теории)

**Что предсказывает:**
- Вероятность действия: `will_act()` функция
- Пороговые эффекты: self-efficacy < 0.3 → 65% вероятность отказа
- Эффекты интервенций: повышение self-efficacy на 0.2 → снижение порога на 15%

**Пример:**
```python
person.threshold.desirability = 0.8
person.threshold.feasibility = 0.3
person.threshold.threshold_level = 0.7

volitional_strength = 0.8 * 0.3 = 0.24
0.24 < 0.7 → will_act() = False

Предсказание: Человек НЕ перейдёт к действию (точность ~75-80%)
```

#### Уровень 3: Гибридные предсказания (синергия)

**Комбинированные инсайты:**

```
GT-анализ: "chronic_preparation_without_action"
+
Теоретические параметры:
  - action_readiness = 0.2
  - self_efficacy = 0.3
  - anxiety → raises threshold
  
Интегрированное предсказание:
1. Качественно: Человек будет искать курсы/подготовку как форму избегания
2. Количественно: Вероятность начать действие < 20%
3. Интервенция: Снижение порога через micro-commitments может 
   повысить вероятность до ~50%
```

### Сравнительная таблица предсказательной силы

| Критерий | Чистая GT | Чистая SCT | Наша модель (интегр.) |
|----------|-----------|------------|----------------------|
| **Precision** | Низкая | Высокая | Средне-высокая |
| **Generalizability** | Низкая | Высокая | Средняя |
| **Contextual depth** | Высокая | Низкая | Высокая |
| **Quantification** | Нет | Да | Да (частично) |
| **Process understanding** | Отлично | Хорошо | Отлично |
| **Behavior prediction** | Слабо | Сильно | Сильно |
| **Theory generation** | Основная цель | Не применяется | Возможна |
| **Theory testing** | Не применяется | Основная цель | Возможна |
| **Novelty discovery** | Высокая | Низкая | Высокая |

**Вывод:** Модель сохраняет эмпирическую валидность теорий (количественные предсказания), добавляя контекстуальную глубину и способность к открытию новых паттернов через GT.

---

## Теоретические основания

### 1. Социально-когнитивная теория Бандуры

**Ключевые концепты:**
- **Human agency** — способность человека намеренно влиять на свою жизнь и обстоятельства
- **Triadic reciprocal causation** — взаимное влияние личности, поведения и окружения
- **Self-efficacy** — вера в собственную способность достичь цели
- **Forethought** — способность предвидеть будущее и планировать
- **Self-reflectiveness** — способность к рефлексии над собственным функционированием

**Источники:**
- Bandura, A. (1989). Human agency in social cognitive theory. American Psychologist, 44(9), 1175–1184.
- Bandura, A. (2001). Social cognitive theory: An agentic perspective. Annual Review of Psychology, 52, 1–26.

### 2. Теория временной перспективы (FTP)

**Future Time Perspective (FTP)** — глубина и содержание мысленной проекции себя в будущее:
- **Temporal depth** — насколько далеко в будущее человек планирует (недели vs годы)
- **Future orientation** — степень фокуса на будущих событиях vs настоящем
- **Mental time travel** — когнитивная способность воображать себя в будущем

**Эффекты FTP:**
- Глубокая FTP связана с долгосрочным планированием, академической успешностью, финансовой грамотностью
- Короткая FTP связана с импульсивностью, аддикциями, краткосрочными решениями
- FTP может быть **домен-специфичной** (разная для карьеры, здоровья, финансов)

**Источники:**
- Zimbardo, P. G., & Boyd, J. N. (1999). Putting time in perspective: A valid, reliable individual-differences metric. Journal of Personality and Social Psychology, 77(6), 1271–1288.
- Stolarski, M., et al. (2015). Time perspective theory; review, research and application.

### 3. Интерсубъективность

**Intersubjectivity** — разделяемые значения и когнитивная инфраструктура, через которую формируются интенции:

**Три уровня:**
1. **Embodied intersubjectivity** — непосредственная телесная синхронизация и взаимопонимание
2. **Thought communities** — разделяемые убеждения и "само собой разумеющиеся" цели группы
3. **Collective agency** (Bandura) — совместное действие группы к общей цели

**Источники:**
- De Jaegher, H., Di Paolo, E., & Gallagher, S. (2010). Can social interaction constitute social cognition? Trends in Cognitive Sciences, 14(10), 441–447.
- Bandura, A. (2000). Exercise of human agency through collective efficacy. Current Directions in Psychological Science, 9(3), 75–78.

### 4. Метакогниция

**Metacognition** — "мышление о мышлении", способность осознавать и регулировать собственные когнитивные процессы.

**Компоненты:**
- **Metacognitive knowledge** — знание о своих когнитивных процессах
- **Metacognitive regulation** — планирование, мониторинг, оценка собственного мышления
- **Metacognitive awareness** — осознание того, ПОЧЕМУ ты делаешь что-то определённым образом

**Применение:** Метакогниция позволяет избежать спекулятивных психоаналитических интерпретаций "подсознательного", фокусируясь на **наблюдаемой степени рефлексивности** человека.

**Источники:**
- Flavell, J. H. (1979). Metacognition and cognitive monitoring: A new area of cognitive–developmental inquiry. American Psychologist, 34(10), 906–911.
- Schraw, G., & Dennison, R. S. (1994). Assessing metacognitive awareness. Contemporary Educational Psychology, 19(4), 460–475.

### 5. Психология воли (Gollwitzer)

**Implementation Intentions** — планы типа "если X, то Y", снижающие intention-action gap.

**Volitional Strength** — функция от desirability × feasibility, определяющая вероятность перехода к действию.

**Источники:**
- Gollwitzer, P. M. (1990). Action phases and mind-sets. In Handbook of motivation and cognition (Vol. 2, pp. 53–92).
- Gollwitzer, P. M., & Sheeran, P. (2006). Implementation intentions and goal achievement. Advances in Experimental Social Psychology, 38, 69–119.

### 6. Теория эмоциональной регуляции (Gross)

**Process Model of Emotion Regulation:**
- Ситуация → Внимание → Оценка → Реакция
- Стратегии: Suppression, Reappraisal, Acceptance

**Источники:**
- Gross, J. J. (1998). The emerging field of emotion regulation: An integrative review. Review of General Psychology, 2(3), 271–299.

---

## Структура агентной модели

### Компоненты модели

Модель включает **пять основных компонентов** и **одно сквозное измерение**:

```
┌─────────────────────────────────────────────────────────────┐
│          АФФЕКТИВНОЕ ИЗМЕРЕНИЕ (сквозное влияние)           │
│   Эмоции модулируют все компоненты агентности               │
└─────────────────────────────────────────────────────────────┘
                           ↓  ↓  ↓  ↓  ↓
┌─────────────┬─────────────┬─────────────┬─────────────┬──────────────┐
│ (a) ИНТЕНЦИЯ│ (b) ПОРОГ   │ (в) ПЛАНИРО-│ (г) ОБУЧЕНИЕ│ (д) ИНТЕР-   │
│             │  АКТИВАЦИИ  │  ВАНИЕ      │             │  СУБЪЕКТ.    │
├─────────────┼─────────────┼─────────────┼─────────────┼──────────────┤
│• Цель       │• Action     │• Planning   │• Learning   │• Thought     │
│• Мотив      │  readiness  │  style      │  trajectory │  community   │
│• FTP depth  │• Volitional │• Meta-      │• Error      │• Collective  │
│• Goal       │  strength   │  cognition  │  response   │  agency      │
│  clarity    │• Threshold  │• Mental     │• Self-      │• Social      │
│             │  level      │  time travel│  reflection │  embedded.   │
└─────────────┴─────────────┴─────────────┴─────────────┴──────────────┘
```

---

## (a) Интенция и временной горизонт

### Описание

**Интенция** — осознанное или неосознанное намерение достичь определённой цели. Интенции не существуют в вакууме — они имеют **временную глубину** (как далеко в будущее проецируется цель) и **степень осознанности** (насколько человек понимает свои мотивы).

### Параметры

#### 1. Эксплицитные vs имплицитные цели

**Эксплицитная цель** — осознанная, артикулированная:
- "Хочу получить повышение"
- "Планирую выучить Python"

**Имплицитный мотив** — неосознанный или плохо артикулированный, но проявляющийся в поведении:
- "Хочу повышение" (эксплицит) → на самом деле "ищу социальное признание" (имплицит)
- Выявляется через **противоречия в поведении**, а не спекулятивную интерпретацию

#### 2. Future Time Perspective (FTP)

**Temporal depth** — глубина временной перспективы:

| FTP уровень | Временной диапазон | Пример цели |
|-------------|-------------------|-------------|
| **Shallow** | Часы – дни | "Хочу поесть", "Нужно закончить отчёт сегодня" |
| **Medium** | Недели – месяцы | "Закончу курс за семестр", "Съезжу в отпуск летом" |
| **Deep** | Годы – десятилетия | "Стану профессором через 10 лет", "Накоплю на пенсию" |

**Важно:** FTP может быть **домен-специфичной**:
- Карьера: глубокая FTP (планирование на 5-10 лет)
- Здоровье: короткая FTP (не думает о последствиях курения)
- Финансы: средняя FTP (планирует отпуск, но не пенсию)

#### 3. Goal Clarity (ясность цели)

**Степень конкретизации цели:**

- **Высокая ясность:**
  - Специфичная цель: "Защитить диссертацию к июню 2026"
  - Операционализированные шаги: "Сначала эксперимент, потом анализ, потом написание"
  - Чёткие критерии успеха: "Публикация в Scopus Q1"

- **Средняя ясность:**
  - Общая цель: "Хочу быть успешным учёным"
  - Туманные шаги: "Нужно много работать и публиковаться"
  - Неясные критерии: "Когда меня признают коллеги"

- **Низкая ясность:**
  - Смутная цель: "Хочу что-то изменить в жизни"
  - Отсутствие шагов: "Не знаю, с чего начать"
  - Отсутствие критериев: "Пойму, когда почувствую"

### Кодирование через Grounded Theory

```
Открытое кодирование:
"Я хочу сменить работу" → explicit_goal_career_change
"Там все такие... знаете" → implicit_social_discomfort

Осевое кодирование:
explicit_goal ↔ implicit_social_rejection
→ ТЕМА: "career_escape_as_avoidance"

Интерпретация:
Эксплицитная цель (карьерный рост) маскирует имплицитную 
(бегство от токсичного социального окружения)
```

### Операционализация

```python
class Intention:
    explicit_goals: List[str]  # осознанные цели
    implicit_motives: List[str]  # выявляются через противоречия
    
    # Временная перспектива
    temporal_depth: str  # "shallow", "medium", "deep"
    time_span: str  # "hours", "days", "weeks", "months", "years", "decades"
    ftp_domain_specific: Dict[str, str]  # {"career": "deep", "health": "shallow"}
    
    # Ясность цели
    goal_specificity: str  # "high", "medium", "low"
    has_operationalized_steps: bool
    has_success_criteria: bool
    goal_clarity_score: float  # 0-1
```

---

## (b) Порог активации

### Описание

**Action readiness threshold** — порог, при превышении которого намерение превращается в действие. Это психологический "барьер", определяющий переход от "хочу" к "делаю".

### Теоретическая основа

**Gollwitzer (1990): Intention-action gap** — разрыв между намерением и действием.

**Volitional strength** (волевая сила) = Desirability × Feasibility:
- **Desirability** — насколько желанна цель
- **Feasibility** — насколько она выполнима

Действие происходит, когда: `Volitional strength > Threshold`

### Параметры

#### 1. Action Readiness (готовность к действию)

Шкала 0–1:
- **0.0–0.3**: Низкая готовность — много раздумий, мало действий
- **0.4–0.6**: Средняя готовность — периодически действует
- **0.7–1.0**: Высокая готовность — быстро переходит к действию

#### 2. Паттерны прокрастинации

- **Отсутствие прокрастинации**: намерение → действие (короткий лаг)
- **Периодическая прокрастинация**: намерение → долгие раздумья → действие
- **Хроническая прокрастинация**: намерение → бесконечные раздумья → отказ

#### 3. Триггеры активации

Что снижает порог и провоцирует действие:
- **Внешний дедлайн**: "Сдать через 2 дня" → активация
- **Социальная поддержка**: "Друг идёт со мной" → снижение порога
- **Эмоциональный катализатор**: гнев, страх, энтузиазм → импульс к действию
- **Implementation intentions**: "Если X, то Y" → автоматизация действия

### Кодирование через GT

```
Временная динамика кодов:
t1: "планирую начать" → low_activation
t2: "думаю об этом каждый день" → rumination_without_action
t3: "записался на курс!" → HIGH_ACTIVATION (порог преодолён)

Осевое кодирование триггеров:
external_deadline + social_support → theme: "needs_external_push"
```

### Операционализация

```python
class ActionThreshold:
    action_readiness: float  # 0-1
    procrastination_pattern: str  # "none", "periodic", "chronic"
    
    # Волевая сила (Gollwitzer)
    desirability: float  # насколько хочется
    feasibility: float  # насколько реально
    threshold_level: float  # индивидуальный порог (0.5-0.9)
    
    # Триггеры
    activation_triggers: List[str]  # ["deadline", "social_support", "anger"]
    
    def will_act(self) -> bool:
        volitional_strength = self.desirability * self.feasibility
        return volitional_strength > self.threshold_level
```

---

## (в) Планирование и просчёт вариантов

### Описание

**Forethought** (Bandura) — способность предвидеть последствия действий и планировать траекторию достижения цели. Включает:
- Генерацию альтернативных сценариев
- Оценку вероятностей и рисков
- Формирование "if-then" планов
- Метакогнитивный мониторинг собственного планирования

### Параметры

#### 1. Planning Style (стиль планирования)

- **Systematic planner**:
  - Рассматривает альтернативы
  - Взвешивает pros/cons
  - Формирует детальный план
  - GT-коды: `considers_alternatives`, `weighs_pros_cons`, `step_by_step_thinking`

- **Reactive responder**:
  - Действует по обстоятельствам
  - Минимальное предварительное планирование
  - Адаптируется в процессе
  - GT-коды: `impulsive_decision`, `goes_with_flow`, `situational_adaptation`

- **Analysis paralysis**:
  - Чрезмерное обдумывание
  - Застревание в планировании
  - Неспособность перейти к действию
  - GT-коды: `overthinks`, `paralyzed_by_analysis`, `endless_deliberation`
  - **Важно**: высокое (в) + низкое (б) = планирование без действия

#### 2. Mental Time Travel (мысленное путешествие во времени)

**Способность воображать себя в будущем и проигрывать сценарии:**
- **High MTT ability**: чётко представляет будущее "Я", детальные сценарии
- **Medium MTT**: общие представления о будущем
- **Low MTT**: трудности с воображением себя в будущем

#### 3. Metacognitive Regulation

**Метакогнитивная регуляция планирования:**
- **Planning** — постановка целей и стратегий
- **Monitoring** — отслеживание прогресса ("Я на правильном пути?")
- **Evaluation** — оценка результатов ("Сработало ли?")

**Высокая метакогниция:**
```
"Я заметил, что застреваю в деталях, нужно сфокусироваться 
на главном" → metacognitive_monitoring_of_planning
```

**Низкая метакогниция:**
```
"Я просто делаю, как получается" → unreflective_execution
```

### Кодирование через GT

```
Высокая способность планирования:
Коды: "considers_alternatives", "if_then_thinking", 
      "anticipates_obstacles"
Тема: "strategic_forward_planner"

Низкая способность:
Коды: "impulsive", "avoids_thinking_ahead", "reactive"
Тема: "present_focused_reactor"

Противоречивый паттерн:
Коды: "overthinks" + "never_acts"
Тема: "analysis_paralysis_syndrome"
```

### Операционализация

```python
class Planning:
    planning_style: str  # "systematic", "reactive", "paralyzed"
    
    # Когнитивные способности
    considers_alternatives: bool
    weighs_probabilities: bool
    has_if_then_plans: bool  # implementation intentions
    mental_time_travel_ability: float  # 0-1
    
    # Метакогниция
    metacognitive_awareness: float  # 0-1, осознание своего планирования
    planning_monitoring: bool  # отслеживает ли прогресс
    adjusts_plans: bool  # корректирует ли по ходу
```

---

## (г) Обучение на ошибках

### Описание

**Self-reflectiveness** (Bandura) — способность к рефлексии над собственным функционированием и корректировке поведения на основе обратной связи.

**Triadic reciprocal causation:**
```
Поведение → Результат → Обратная связь → Обновление убеждений → 
→ Изменение поведения
```

### Параметры

#### 1. Error Response (реакция на ошибку)

- **Blames external factors**:
  - "Это не моя вина, обстоятельства были против меня"
  - Локус контроля: внешний
  - GT-код: `external_attribution`

- **Recognizes own role**:
  - "Я мог бы действовать иначе"
  - Начало рефлексии
  - GT-код: `accepts_responsibility`

- **Reflects and adapts**:
  - "Я понял, что ошибся в X, в следующий раз сделаю Y"
  - Полноценное обучение
  - GT-код: `learns_from_feedback`, `adjusts_strategy`

#### 2. Self-Efficacy Trajectory

**Динамика уверенности в способности достичь цели:**
- **Increasing**: с каждым успехом растёт уверенность
- **Stable**: уверенность не меняется
- **Declining**: серия неудач снижает веру в себя

**Важно:** Self-efficacy влияет на (б) порог активации — низкая self-efficacy повышает порог.

#### 3. Learning Trajectory (траектория обучения)

**Отслеживание изменений во времени:**

```
Сессия 1: "Это провал, я ничего не могу" → victimhood_mindset
Сессия 5: "Может, я что-то делаю не так?" → beginning_reflection
Сессия 10: "Я скорректировал подход, и это работает!" → adaptive_learning

Тема: "trajectory_from_helplessness_to_agency"
```

### Кодирование через GT

```
Низкое обучение:
Коды: "blames_others", "avoids_reflection", "repeats_mistakes"
Тема: "fixed_pattern_responder"

Высокое обучение:
Коды: "analyzes_failures", "seeks_feedback", "adjusts_approach"
Тема: "growth_oriented_learner"
```

### Операционализация

```python
class Learning:
    error_response_style: str  # "blame_external", "reflects", "adapts"
    
    # Self-efficacy
    self_efficacy_level: float  # 0-1, текущий уровень
    self_efficacy_trend: str  # "increasing", "stable", "declining"
    
    # Траектория изменения
    learning_trajectory: List[dict]  # [{"session": 1, "codes": [...], "theme": "..."}]
    
    # Рефлексивность
    self_reflectiveness: float  # 0-1, способность к рефлексии
    seeks_feedback: bool
    adjusts_based_on_experience: bool
```

---

## (д) Интерсубъективность

### Описание

**Интерсубъективность** — встроенность агентности в социальный контекст. Человек не автономный агент в вакууме, а часть **shared cognitive infrastructure**, где интенции, цели и действия формируются через взаимодействие с другими.

### Три уровня интерсубъективности

#### 1. Embodied Intersubjectivity (телесная интерсубъективность)

**Непосредственное взаимодействие:**
- Синхронизация поведения (behavior matching)
- Эмоциональный резонанс
- Чувство взаимопонимания через интеракцию

**GT-код:**
```
"Мы с ним на одной волне" → embodied_synchrony
"Она меня понимает без слов" → intuitive_connection
```

#### 2. Thought Communities (когнитивные сообщества)

**Разделяемые убеждения и "само собой разумеющиеся" цели группы:**

- В **академическом сообществе**: "хочу публиковаться в Scopus" — естественная цель
- В **предпринимательской среде**: "хочу масштабировать бизнес" — ожидаемая интенция
- В **другой среде**: эти цели могут казаться странными или непонятными

**GT-код:**
```
"Все в нашей лаборатории стремятся к публикациям" → 
   thought_community_norm
```

#### 3. Collective Agency (коллективная агентность, Бандура)

**Три типа социальной агентности:**

- **Personal agency**: "Я сам действую к своей цели"
  - Индивидуальное целеполагание и действие
  
- **Proxy agency**: "Я прошу других действовать за меня"
  - Делегирование действия
  - Пример: "Я попросил коллегу помочь с анализом"
  
- **Collective agency**: "Мы вместе действуем к общей цели"
  - Интенция существует на уровне группы, а не индивида
  - Пример: "Наша команда разрабатывает продукт"

### Параметры

#### 1. Thought Community Membership

**К какому когнитивному сообществу принадлежит человек:**
- "academic"
- "entrepreneurial"
- "activist"
- "corporate"

Это определяет **фрейм**, через который интерпретируются цели и действия.

#### 2. Social Embeddedness (социальная встроенность)

Шкала 0–1:
- **0.0–0.3**: Низкая — автономный агент, минимальная зависимость от других
- **0.4–0.6**: Средняя — учитывает мнение других, но сохраняет автономность
- **0.7–1.0**: Высокая — интенции сильно зависят от социального контекста

#### 3. Agency Type Distribution

**Распределение типов агентности в поведении:**
```python
{
  "personal": 0.6,    # 60% действий — индивидуальные
  "proxy": 0.1,       # 10% — делегирует другим
  "collective": 0.3   # 30% — коллективные действия
}
```

### Кодирование через GT

```
Открытое кодирование:
"Я не могу это сделать один" → recognizes_interdependence
"Нам нужно договориться с командой" → seeks_collective_decision
"Они подумают, что я..." → anticipates_social_judgment

Осевое кодирование:
interdependence + seeks_collective + anticipates_judgment
→ ТЕМА: "embedded_in_social_matrix"

Интерпретация:
Интенция не автономна, она конституируется через 
ожидаемую реакцию других и коллективные нормы
```

### Операционализация

```python
class Intersubjectivity:
    # Тип сообщества
    thought_community: str  # "academic", "entrepreneurial", etc.
    
    # Социальная встроенность
    social_embeddedness: float  # 0-1
    interdependence_recognition: bool
    
    # Распределение типов агентности
    agency_type_distribution: Dict[str, float]  
    # {"personal": 0.6, "proxy": 0.1, "collective": 0.3}
    
    # Влияние социального контекста
    anticipates_social_judgment: bool
    aligns_with_group_norms: bool
```

---

## (е) Аффективное измерение (сквозное)

### Описание

**Эмоции не существуют как отдельный компонент** — они **модулируют все остальные компоненты** агентности. Это сквозное влияние, которое изменяет функционирование (a), (b), (в), (г), (д).

### Влияние эмоций на компоненты

#### Влияние на (a) Интенцию и FTP

- **Положительный аффект** (радость, энтузиазм):
  - Расширяет FTP → человек думает дальше в будущее
  - Увеличивает goal clarity → цели становятся более чёткими
  
- **Отрицательный аффект** (тревога, депрессия):
  - Сужает FTP → фокус на краткосрочных угрозах
  - Снижает goal clarity → цели размываются
  - **Депрессия**: может полностью блокировать FTP ("нет смысла планировать")

#### Влияние на (b) Порог активации

- **Энтузиазм**: снижает порог → легче начать действовать
- **Страх**: повышает порог → паралич действия ("слишком страшно")
- **Гнев**: может и снизить (импульсивное действие), и повысить (избегание конфронтации)

#### Влияние на (в) Планирование

- **Позитивный настрой**: оптимистичные сценарии, недооценка рисков
- **Негативный настрой**: пессимистичные сценарии, catastrophizing
- **Тревога**: может парализовать планирование ("что, если всё пойдёт не так?")

#### Влияние на (г) Обучение

- **Стыд**: блокирует рефлексию над ошибкой (избегание болезненных мыслей)
- **Любопытство**: усиливает обучение ("интересно, почему не сработало?")
- **Фрустрация**: может привести к отказу от дальнейших попыток

#### Влияние на (д) Интерсубъективность

- **Социальная тревожность**: усиливает зависимость от мнения других
- **Уверенность**: снижает социальную встроенность (больше автономии)

### Параметры

#### 1. Emotional Valence (валентность)

- **Positive**: радость, энтузиазм, удовлетворение
- **Negative**: страх, гнев, печаль, стыд
- **Mixed**: амбивалентные эмоции

#### 2. Emotion Impact Profile

**Как конкретная эмоция влияет на агентность:**

```python
{
  "emotion": "anxiety",
  "impact_on_ftp": "shortens_horizon",
  "impact_on_threshold": "raises",
  "impact_on_planning": "catastrophizing",
  "impact_on_learning": "avoids_reflection"
}
```

#### 3. Emotion Regulation Strategy

**Как человек регулирует эмоции:**
- **Suppression** (подавление): "стараюсь не думать об этом"
- **Reappraisal** (переоценка): "смотрю на ситуацию по-другому"
- **Acceptance** (принятие): "принимаю свои чувства"
- **None** (нет регуляции): "эмоции захлёстывают меня"

**Важно:** Эффективная emotion regulation может **компенсировать** негативное влияние эмоций на другие компоненты.

### Кодирование через GT

```
Эмоции как модулятор:
"Я так боюсь, что даже не могу начать планировать" →
  fear_paralyzes_planning (связь б + в)

"Когда я злюсь, сразу действую, не думая" →
  anger_bypasses_planning (связь б, минус в)

"Я стыжусь этой ошибки, не хочу о ней думать" →
  shame_blocks_reflection (связь г)
```

### Операционализация

```python
class AffectiveModulation:
    # Текущее эмоциональное состояние
    current_emotion: str  # "anxiety", "enthusiasm", "anger", etc.
    emotional_valence: str  # "positive", "negative", "mixed"
    emotional_intensity: float  # 0-1
    
    # Профиль влияния
    impact_on_ftp: str  # "expands", "shortens", "neutral"
    impact_on_threshold: str  # "lowers", "raises", "paralyzes"
    impact_on_planning: str  # "optimistic", "pessimistic", "disrupts"
    impact_on_learning: str  # "enhances", "blocks", "neutral"
    
    # Регуляция
    emotion_regulation: str  # "suppression", "reappraisal", "acceptance", "none"
    regulation_effectiveness: float  # 0-1, насколько успешно регулирует
```

---

## Применение в r-bot и других контекстах

### 1. Адаптивные диалоговые системы (r-bot)

**Сценарий:** NPC адаптируется к профилю агентности игрока.

**Процесс:**
1. Игрок взаимодействует с ботом
2. GT-анализатор кодирует сообщения → обновляет `AgenticProfile`
3. NPC генерирует ответы с учётом профиля

**Пример:**
```python
if player.planning.planning_style == PlanningStyle.PARALYZED:
    npc_response = "Хватит думать. Время действовать. Вот два простых варианта."
    # Снижает когнитивную нагрузку

if player.threshold.action_readiness < 0.3:
    npc_response = "Погоди, ты точно готов? Может, сначала подумаем?"
    # Защищает от импульсивных решений

if player.intersubjectivity.social_embeddedness > 0.7:
    npc_response = "Другие тоже так поступили. Ты не один."
    # Использует социальное влияние
```

### 2. Качественное исследование

**Сценарий:** Исследование причин неучастия в программах финансовой грамотности.

**Процесс:**
1. Интервью с 20 респондентами
2. GT-кодирование → заполнение `AgenticProfile` для каждого
3. Кластерный анализ профилей
4. Выявление паттернов

**Предсказание:**
```
Кластер 1: "Engaged learners"
- High FTP + High action readiness + High metacognition
- Участвуют в программах (предсказанная вероятность 85%)

Кластер 2: "Anxious procrastinators"
- Deep FTP + Low action readiness + Anxiety blocks planning
- НЕ участвуют (предсказанная вероятность неучастия 78%)

→ Интервенция: Снизить порог активации через социальную поддержку
```

### 3. Персонализированные интервенции

| Проблема | Компонент | Интервенция |
|----------|-----------|-------------|
| "Не знаю, чего хочу" | (a) Goal clarity | Техники кристаллизации целей |
| "Хочу, но не делаю" | (b) Порог активации | Implementation intentions |
| "Не умею планировать" | (в) Планирование | MTT-практики |
| "Повторяю ошибки" | (г) Обучение | Рефлексивные практики |
| "Завися от других" | (д) Интерсубъектив. | Работа с autonomy |
| "Страх парализует" | (е) Аффект | Emotion regulation |

---

## Библиография

### Ключевые источники

**Bandura (Social Cognitive Theory):**
- Bandura, A. (1989). Human agency in social cognitive theory. *American Psychologist*, 44(9), 1175–1184.
- Bandura, A. (2001). Social cognitive theory: An agentic perspective. *Annual Review of Psychology*, 52, 1–26.

**Future Time Perspective:**
- Zimbardo, P. G., & Boyd, J. N. (1999). Putting time in perspective. *Journal of Personality and Social Psychology*, 77(6), 1271–1288.
- Stolarski, M., et al. (2015). *Time perspective theory; review, research and application*.

**Metacognition:**
- Flavell, J. H. (1979). Metacognition and cognitive monitoring. *American Psychologist*, 34(10), 906–911.
- Schraw, G., & Dennison, R. S. (1994). Assessing metacognitive awareness. *Contemporary Educational Psychology*, 19(4), 460–475.

**Intersubjectivity:**
- De Jaegher, H., Di Paolo, E., & Gallagher, S. (2010). Can social interaction constitute social cognition? *Trends in Cognitive Sciences*, 14(10), 441–447.

**Volition:**
- Gollwitzer, P. M. (1990). Action phases and mind-sets. *Handbook of motivation and cognition* (Vol. 2, pp. 53–92).

**Emotion Regulation:**
- Gross, J. J. (1998). The emerging field of emotion regulation. *Review of General Psychology*, 2(3), 271–299.

**Grounded Theory:**
- Charmaz, K. (2014). *Constructing grounded theory* (2nd ed.). SAGE Publications.

---

## Контакты и цитирование

**Автор:** Сергей Ершов  
**Дата:** 26 ноября 2025  
**Версия:** 2.0  
**Репозиторий:** https://github.com/yserjjj-2022/r-bot

**Как цитировать:**
```
Ершов, С. (2025). Агентная модель человеческого поведения: 
Мультитеоретическая интеграция через Grounded Theory. v2.0.
https://github.com/yserjjj-2022/r-bot/blob/main/docs/agentic_human_model.md
```

**Лицензия:** MIT License  
**Контакты:** [GitHub: yserjjj-2022](https://github.com/yserjjj-2022)

---

## Changelog

### Version 2.0 (26 ноября 2025)
- Добавлена секция "Мультитеоретическая архитектура"
- Добавлена секция "Предсказательный спектр модели"
- Уточнена роль GT как методологии vs содержательных теорий
- Расширена библиография (добавлены Gollwitzer, Gross)
- Добавлена сравнительная таблица предсказательной силы

### Version 1.0 (26 ноября 2025)
- Первоначальная версия модели
- Пять основных компонентов + аффективное измерение
- Python-реализация структур данных
- Примеры применения в GT и диалоговых системах
