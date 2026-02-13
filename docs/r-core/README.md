# 📚 R-Core Documentation

**Добро пожаловать в документацию R-Core Kernel!**

Это — навигация по всем компонентам системы. Каждый документ — это отдельный "том" с глубоким погружением в конкретную тему.

---

## 🗂️ Оглавление

### 📖 **Том 1: [R-Core Architecture](./architecture.md)**
**Главный обзорный документ**

Описывает общую архитектуру R-Core Kernel:
- Cognitive Parliament (5 агентов)
- Mood System (VAD модель)
- Memory System (Буквальная STM, Векторная LTM, Семантическая, Волевая)
- Council Report (LLM Batch Processing)
- Входы/Выходы (Schemas)

**Читать первым** для понимания общей картины.

**Статус**: ✅ Актуальная версия  
**Последнее обновление**: Февраль 2026

---

### 💚 **Том 2: [Affective Theory of Mind & Profiling](./affective-tom-guide.md)**
**Эмоциональная память и профиль личности**

Подробное описание механизма запоминания отношений и черт характера:
- **Affective Extraction**: Извлечение эмоций (LOVES, HATES, FEARS) и VAD-сентимент.
- **Smart Profiling**: Механизм "Winner-Takes-Slot" для черт личности (Traits).
- **Neuro-Modulation**: Влияние проигравших агентов на стиль ответа через наречия.
- **Observability**: Таблица `rcore_metrics` и полные логи для дашборда.

**Статус**: ✅ Реализовано (Этап 2.1)  
**Дата завершения**: 08.02.2026

---

### 🔮 **Том 3: [Predictive Processing](./predictive-processing.md)**
**Прогнозирование реакции пользователя и адаптация поведения**

Механизм предсказания следующего сообщения пользователя:
- Prediction Error (PE) и Empathy Alignment (EA)
- 4 поведенческих состояния: In Sync, Neutral, Puzzled, Lost
- Влияние на Mood System (VAD adjustments)
- Uncertainty Agent (активация при PE >= 0.8)

**Статус**: 🚧 В разработке (Этап 2.2)

---

### 🧪 **Том 4: [Ablation Studies & Testing](./testing.md)**
**Инструменты проверки гипотез и сравнения архитектур**

- **Zombie Mode (A/B Test)**: Сравнение R-Core ("Кортикал") с обычной LLM ("Зомби").
- **Metrics**: Latency, Sentiment, User Engagement.
- **Streamlit Controls**: Переключатель режимов A/B в сайдбаре.

**Статус**: ✅ Реализовано (Февраль 2026)

---

### 🧬 **Том 5: [Narrative Identity & Intentionality](./narrative-identity.md)** *(Concept)*
**Глубинные слои личности и целеполагание**

Концепция формирования "души" бота через нарратив и импринтинг.
- **Intentionality**: Core Drives, Hidden Agenda.
- **Imprinting**: Origin Story, Hard-coded Memories.

**Статус**: 💡 R&D Концепция (На обсуждении)

---

### 💊 **Том 6: [Neuro-Modulation (Hormonal Physics)](./neuromodulation-spec.md)** *(New)*
**Биохимический слой регуляции системы**

Детальная спецификация системы "Большой Четвёрки" нейромодуляторов:
- **Norepinephrine (NE)**: Регулятор чувствительности (Gain Control) и реакции на новизну.
- **Dopamine (DA)**: Регулятор порога действий (Action Threshold) и мотивации.
- **Serotonin (5-HT)**: Регулятор стабильности (Stability) и ингибирования импульсов.
- **Cortisol (CORT)**: Реакция на стресс, перераспределение ресурсов (PFC Shutdown).

Документ содержит математическую модель динамической инерции и чувствительности.

**Статус**: ✅ Спецификация готова, модуль реализован (Этап 2.2)

---

### 🗺️ **Том 7: [Self & Other Model Roadmap](./self-and-other-roadmap.md)** *(🆕 New)*
**Дорожная карта развития самосознания и Theory of Mind**

Поэтапный план внедрения двух ключевых способностей "мыслящего" AI:

**Self-Model (Понимание себя):**
- Явные ценности бота (Bot Values)
- Собственные убеждения о мире (Bot Affective Profile)
- Рефлексия над действиями (Reflective Layer)

**Other-Model (Theory of Mind):**
- Инференция состояния юзера (User State Inference)
- Предсказание реакций (Reaction Prediction)
- Моделирование целей юзера (Goal Graphs)

Документ включает 3 фазы разработки, оценку сложности и конкретные технические рекомендации.

**Статус**: 📝 Дорожная карта (Февраль 2026)  
**Теоретическая основа**: Александр Мирер (концепция "мыслящего"), Premack & Woodruff (Theory of Mind, 1978)

---

### 🗺️ **Том 7: [Self & Other Model Roadmap](./self-and-other-roadmap.md)** *(🆕 New)*
**Дорожная карта развития самосознания и Theory of Mind**

Поэтапный план внедрения двух ключевых способностей "мыслящего" AI:

**Self-Model (Понимание себя):**
- Явные ценности бота (Bot Values)
- Собственные убеждения о мире (Bot Affective Profile)
- Рефлексия над действиями (Reflective Layer)

**Other-Model (Theory of Mind):**
- Инференция состояния юзера (User State Inference)
- Предсказание реакций (Reaction Prediction)
- Моделирование целей юзера (Goal Graphs)

Документ включает 3 фазы разработки, оценку сложности и конкретные технические рекомендации.

**Статус**: 📝 Дорожная карта (Февраль 2026)  
**Теоретическая основа**: Александр Мирер (концепция "мыслящего"), Premack & Woodruff (Theory of Mind, 1978)

---

## 📊 Roadmap

### ✅ Завершено
- **Этап 1**: Core Architecture (Council, Mood, Memory)
- **Этап 2.1**: Affective Theory of Mind + Smart Profiling
  - ✅ Explicit Trait Extraction ("I am skeptical")
  - ✅ Affective Relations ("I love Yennefer")
  - ✅ Neuro-Modulation (Adverb Injection style)
  - ✅ SQL-Metrics Logging (`rcore_metrics`)
  - ✅ A/B Zombie Mode Switcher

### 🚧 В процессе
- **Этап 2.2**: Optimization & Deep Memory
  - ✅ **Hormonal Physics**: Модуль `neuromodulation.py` реализован (NE, DA, 5-HT, CORT)
  - ⏳ **Latency Reduction**: Parallel agent execution (`asyncio.gather`)
  - ⏳ **Vector Traits**: Fuzzy matching для профиля через эмбеддинги
  - ⏳ **Deep Episodic**: Использование эпизодической памяти для формирования мнений

### ⏳ Запланировано
- **Этап 3**: Predictive Processing (Empathy Feedback Loop)
- **Этап 4**: Self & Other Model (Self-awareness + Theory of Mind)
- **Этап 5**: Narrative Identity (Imprinting & Drives)
- **Этап 6**: Strategic Protocols (неискренность)

---

## 🛠️ Запуск и Тестирование

### Основной запуск
```bash
# Streamlit UI (с поддержкой A/B Zombie Mode)
streamlit run app_streamlit.py
```

### Мониторинг
В `app_streamlit.py` теперь доступны:
1. **Mood Dashboard** (VAD метрики).
2. **Internal Monologue** (раскрывающийся JSON).
3. **Emotional Memory** (сайдбар).
4. **🧪 Experiment Mode** (сравнение с "глупой" LLM).

---

## 📞 Контакты

**Проект**: [github.com/yserjjj-2022/r-bot](https://github.com/yserjjj-2022/r-bot)  
**Ветка**: `develop` (Stable) / `feature/neuro-modulation-v1` (Active)  
**Автор**: Sergey Ershov (yserjjj-2022)

---

**Приятного чтения! 📖**
