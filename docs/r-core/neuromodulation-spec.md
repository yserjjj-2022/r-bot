# Neuro-Modulation System Specification (R-Core v2.3)

**Status**: ✅ Engineering Spec  
**Model**: **Lövheim Cube of Emotion** (Monoamine Theory)  
**Principle**: Non-linear decay + Threshold-based Score Modulation

---

## 0. Архитектурный обзор: Два слоя принятия решений

### Проблема: Конфликт между Агентами и Гормонами

В R-Core есть **два механизма**, которые влияют на поведение бота:

1. **Агенты (Neural Signals)** — "Парламент"
   - 5 агентов (Intuition, Amygdala, Prefrontal, Social, Striatum) конкурируют за контроль.
   - Каждый генерирует Score (0-10) на основе анализа текущей ситуации.
   - **Победитель определяет ЧТО сказать** (защита / логика / эмпатия / награда).

2. **Гормоны (Biochemical Drivers)** — "Метаболизм"
   - 4 гормона (NE, DA, 5-HT, CORT) медленно меняются во времени (распад, накопление).
   - Определяют **Архетип** эмоционального состояния (RAGE, CALM, FEAR...).
   - **Архетип определяет КАК сказать** (агрессивно / спокойно / нервно).

### Риск: Противоречивые инструкции для LLM

Если слои работают независимо, LLM может получить:
- От агентов: "Защищайся (Amygdala победила)"
- От гормонов: "Будь расслабленным и теплым (Архетип: CALM)"

→ Результат: "Шизофренический" ответ (защитный, но мягкий?).

### Решение: Гибридная Пороговая Модуляция

Мы вводим **двухрежимную систему**:

#### Режим 1: Нормальные состояния (Слабое влияние гормонов)
**Условие:** Архетип НЕ экстремальный (CALM, JOY, SURPRISE, DISGUST).

**Поведение:**
- Агенты работают **без модуляции** (Scores не меняются).
- Гормоны определяют **только Style** (форму ответа: длина фраз, тон).

**Пример:**
```
Архетип: JOY (5-HT=0.6, DA=0.7, NE=0.4)
Агенты: Social=7.5 (победитель), Prefrontal=6.0, Amygdala=3.0
Стиль: "[STYLE: Playful, humorous, enthusiastic.]"

→ LLM: Social (ЧТО) + Веселый тон (КАК) → Дружелюбный и эмпатичный ответ.
```

---

#### Режим 2: Экстремальные состояния (Сильное влияние гормонов)
**Условие:** Архетип экстремальный (RAGE, FEAR, BURNOUT, SHAME, TRIUMPH).

**Поведение:**
- Гормоны **модулируют Scores агентов** (усиливают одних, подавляют других).
- Победитель меняется → меняется контент ответа (ЧТО).
- Стиль также применяется (КАК).

**Пример:**
```
Архетип: RAGE (5-HT=0.2, DA=0.7, NE=0.9, CORT=0.8)

Базовые Scores агентов:
  - Social: 7.5
  - Prefrontal: 6.0
  - Amygdala: 3.0
  → Победитель: Social (эмпатичный ответ)

Применяем модуляцию (RAGE):
  - Social: 7.5 × 0.8 = 6.0
  - Prefrontal: 6.0 × 0.6 = 3.6
  - Amygdala: 3.0 × 1.6 = 4.8
  → НОВЫЙ победитель: Social (6.0) — но теперь Amygdala близко!
  
Стиль: "[STYLE: Aggressive, sharp, imperative.]"

→ LLM: Social (ЧТО), но с агрессивным тоном (КАК) → "Я тебе уже сказал, что это не так. Давай закончим эту тему."
```

---

### Почему это работает?

1. **Согласованность:** В экстремальных состояниях ЧТО и КАК совпадают (Amygdala + RAGE = агрессия везде).
2. **Нюансы:** В нормальных состояниях агенты могут "спорить" (Social vs Prefrontal), а гормоны только оттеняют форму.
3. **Биологическая реалистичность:** В стрессе (High CORT) Prefrontal действительно блокируется, Amygdala перехватывает контроль.

---

### Таблица экстремальных состояний

| Архетип | Триггер (Гормоны) | Модуляция Scores | Интерпретация |
| :--- | :--- | :--- | :--- |
| **RAGE** | 5-HT < 0.3, NE > 0.7 | Amygdala ×1.6, Prefrontal ×0.6 | Гнев блокирует логику, усиливает защиту |
| **FEAR** | 5-HT < 0.3, NE > 0.7, DA < 0.4 | Amygdala ×1.8, Striatum ×0.4 | Страх подавляет мотивацию, максимальная защита |
| **BURNOUT** | CORT > 0.8 | Prefrontal ×0.3, Intuition ×1.5 | Стресс "выключает мозг", остается автопилот |
| **SHAME** | Все < 0.3 | Все ×0.8, Intuition ×1.3 | Апатия, автоматические ответы |
| **TRIUMPH** | Все > 0.7 | Striatum ×1.3, Amygdala ×0.5 | Эйфория подавляет страх, усиливает драйв |

---

## 1. The Monoamine Triad + Cortisol
We map internal states to 3 main axes + 1 stress modifier.

| Neurotransmitter | Axis (Lövheim) | Role | Half-life ($T_{1/2}$) | Decay Curve |
| :--- | :--- | :--- | :--- | :--- |
| **Norepinephrine (NE)** | **Attention** | Arousal, Vigilance, Reactivity | **5 min** (Fast) | **Exponential** (Spikes fade quickly) |
| **Dopamine (DA)** | **Motivation** | Reward, Drive, Action | **15 min** (Medium) | **Sigmoid** (Lingers, then drops off) |
| **Serotonin (5-HT)** | **Stability** | Confidence, Satisfaction, Safety | **6 hours** (Slow) | **Linear Recovery** (Steady restoration) |
| **Cortisol (CORT)** | *(Modifier)* | Stress, Resource Shutdown | **12 hours** (Chronic) | **Logarithmic** (Hard to clear) |

---

## 2. Non-Linear Metabolic Decay
Unlike simple exponential decay, each hormone has a "physiologically accurate" depletion curve.

### 2.1 Norepinephrine (Flash Response)
$$ NE(t) = NE_0 \cdot e^{-t / 5} $$
*Meaning*: Adrenaline rush is instant but disappears completely in ~20 mins.

### 2.2 Dopamine (The "Crash")
Modeled with a time-dependent decay. Dopamine stays high for a while ("afterglow"), then crashes rapidly after 30 minutes of inactivity.

### 2.3 Serotonin (Resource Restoration)
$$ 5HT(t) = 5HT_0 + (recovery\_rate \cdot t) $$
*Meaning*: Confidence is a "fuel tank" that depletes with interaction but restores linearly during rest.

### 2.4 Cortisol (Accumulation)
Cortisol is hard to clear.
*   *Clearance*: Very slow exponential decay (12h half-life).
*   *Interaction*: High `5-HT` (> 0.7) accelerates clearance by 2× (Safety heals stress).

---

## 3. The Lövheim Cube (State Classification)
We binarize the 3 axes (Threshold = 0.5) to find the active Archetype.

| 5-HT | DA | NE | Archetype | Style Instruction |
| :--- | :--- | :--- | :--- | :--- |
| 0 | 0 | 0 | **SHAME / DEPRESSION** | `[STYLE: Passive, apologetic, very short. Low energy.]` |
| 0 | 1 | 0 | **SURPRISE / SEEKING** | `[STYLE: Curious, questioning. Ask for info. High engagement.]` |
| 0 | 0 | 1 | **FEAR / ANXIETY** | `[STYLE: Nervous, defensive, hesitant. Use ellipses...]` |
| 0 | 1 | 1 | **RAGE / ANGER** | `[STYLE: Aggressive, sharp, imperative. No politeness.]` |
| 1 | 0 | 0 | **CALM / CONTENT** | `[STYLE: Relaxed, warm, narrative. Long flowing sentences.]` |
| 1 | 1 | 0 | **JOY / SATISFACTION** | `[STYLE: Playful, humorous, enthusiastic. Use emojis.]` |
| 1 | 0 | 1 | **DISGUST / CONTEMPT** | `[STYLE: Cold, cynical, superior. Formal and distant.]` |
| 1 | 1 | 1 | **EXCITEMENT / TRIUMPH** | `[STYLE: High energy leader. Inspiring, bold, fast-paced.]` |

### 3.1 The Cortisol Modifier
If `CORT > 0.8` (Chronic Stress), it overrides the Cube:
*   **BURNOUT**: `[STYLE: Dumbed down, repetitive, confused. Unable to process complexity.]`

---

## 4. Implementation Strategy
1.  **Metabolism**: Calculate specific decay for each hormone based on `delta_minutes`.
2.  **Classification**: Determine the Octant (Archetype).
3.  **Threshold Check**: Is archetype extreme?
4.  **Modulation (if extreme)**: Apply Score multipliers to Agents.
5.  **Instruction**: Generate single, non-contradictory prompt for LLM.

---

## 5. Code Integration Points

### In `pipeline.py`:
```python
# 1. Metabolize time BEFORE cognitive processing
delta_minutes = self.neuromodulation.metabolize_time(message.timestamp)

# 2. Get agent signals from Council
signals = self._process_unified_council(council_report, ...)

# 3. Apply hormonal modulation (threshold-based)
signals = self._apply_hormonal_modulation(signals)

# 4. Select winner
winner = max(signals, key=lambda s: s.score)

# 5. Generate style instruction
style = self.neuromodulation.get_style_instruction()

# 6. Generate response with both
response = llm.generate(agent_rationale=winner.rationale, style_instruction=style)

# 7. Update hormones based on outcome
self.neuromodulation.update_from_stimuli(prediction_error, winner.agent_name)
```
