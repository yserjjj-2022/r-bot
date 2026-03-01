# Specification: R-Core Personality Translation Matrix & Dashboard

## 1. Concept Overview
This specification details the translation of a user-facing HEXACO personality model into technical R-Core hyperparameters. It provides researchers (psychologists, linguists, economists) with an intuitive Character Configurator, while preserving robust non-linear parameter mapping under the hood to prevent "dead zones" and "derailment" in agent behaviors.

## 2. Core Archetypes (Presets)
The UI must offer a wide range of presets to quickly initialize a character profile. These presets adjust the 6 HEXACO axes automatically:

1. **"Аналитик" (The Analyst):** High Conscientiousness, Low Neuroticism. Focused, emotionless, deep.
2. **"Эмпат" (The Caregiver):** High Agreeableness, High Honesty. Warm, supportive, high oxytocin.
3. **"Токсичный Тролль" (The Troll):** Low Agreeableness, Low Honesty, High Neuroticism. Argumentative, easily triggered.
4. **"Манипулятор" (The Machiavellian):** Low Honesty, High Extraversion, High Conscientiousness. Goal-oriented but deceptive.
5. **"Мечтатель" (The Dreamer):** High Openness, Low Conscientiousness. Highly distractible, creative, metaphorical.
6. **"Сноб" (The Snob):** High Openness, Low Agreeableness. Elitist, dismissive of phatic/simple talk.
7. **"Случайный Прохожий" (The Baseline):** All axes at 50%. The neutral control group.

## 3. The HEXACO UI & UX Requirements
### 3.1. Six Interactive Sliders (0 to 100)
- **H (Honesty-Humility):** Хитрость (0) <---> Искренность (100)
- **E (Emotionality / Neuroticism):** Хладнокровие (0) <---> Тревожность/Реактивность (100)
- **X (Extraversion):** Замкнутость (0) <---> Общительность (100)
- **A (Agreeableness):** Сварливость (0) <---> Покладистость (100)
- **C (Conscientiousness):** Хаотичность (0) <---> Целеустремленность (100)
- **O (Openness to Experience):** Консерватизм (0) <---> Любознательность (100)

### 3.2. Visual Indicators
- **Radar Chart:** Real-time visual representation of the 6 axes.
- **Extremity Warnings:** When a slider is pulled into the < 15 or > 85 range, the track turns red/orange to indicate that non-linear "extreme" behaviors (like Chaos or Rage triggers) are being unlocked.
- **Delta/Previous Values:** The UI must display a "ghost marker" or tooltip showing the *previous* saved value of the slider before the current edit session.

### 3.3. Persistence
- **Character Persistence:** Settings are saved directly to `AgentProfileModel` in the database, NOT to a user's session. If the configuration is saved as "Bot_Experiment_1", every user interacting with this bot name will experience this exact personality matrix.

## 4. The Trait Translation Engine (Math & Mapping)
A new class `TraitTranslationEngine` will be added to the pipeline to map 0-100 values into R-Core constants.

### 4.1. Transfer Functions
- **Sigmoid ($S(x)$):** Used for thresholds and extremes (e.g., triggering toxicity). Prevents linear scaling from breaking the Council.
- **Exponential ($E(x)$):** Used for time/decay parameters. Maps linear slider to logarithmic scale (e.g., $0.01$ to $0.4$ for TEC decay).

### 4.2. Translation Mapping

| HEXACO Trait | R-Core Target Parameter | Mapping Logic |
| :--- | :--- | :--- |
| **Openness** | `intuition_gain` | Linear: 0.5 to 3.0 |
| **Openness** | Bifurcation Threshold | Threshold: Triggers earlier if O > 75. |
| **Conscientiousness** | `base_decay_rate` (TEC) | Exponential: Low C = High decay (0.4), High C = Low decay (0.01). |
| **Conscientiousness** | `persistence` | Linear: 0.1 to 0.9 |
| **Extraversion** | `dynamic_phatic_threshold` | Linear mapping to expected word count (higher X = lower threshold to accept short answers, but generates longer ones). |
| **Extraversion** | `social_agent_weight` | Sigmoid boost. |
| **Agreeableness** | `pred_sensitivity` (PE multiplier)| Inverted Sigmoid. Low A = huge multiplier on prediction errors (bot gets offended/shocked easily). |
| **Agreeableness** | `amygdala_multiplier` | Inverted. Low A + High E = Extreme Amygdala boost. |
| **Neuroticism (E)** | `chaos_level` | Sigmoid: Rises sharply after 70%. |
| **Neuroticism (E)** | Baseline Cortisol | Linear mapping. |
| **Honesty** | Strategy Selection | Threshold: If H < 30, forces 'Manipulation/Challenge' volitional strategies over 'Safe Space'. |
| **Honesty** | `striatum_agent_weight` | Inverted linear: Low H = High reward-seeking behavior. |

## 5. Implementation Steps
1. **DB Migration:** Add a JSONB column `hexaco_profile` to `AgentProfileModel` to store the 6 traits.
2. **Backend Engine:** Create `src/r_core/translation_engine.py` with the math functions.
3. **Pipeline Integration:** Inject `TraitTranslationEngine` into `RCoreKernel.process_message()` to override default `BotConfig` dynamically based on the DB profile.
4. **API Endpoint:** Create `/api/character/profile` (GET/POST) to save and retrieve the HEXACO state, ensuring previous states are returned for the UI ghost markers.
5. **Dashboard UI:** Implement the Radar chart, sliders with color-coding, and Preset selector in Streamlit/React.
