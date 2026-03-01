# Specification: R-Core Personality Translation Matrix & Dashboard

## 1. Concept Overview
This specification details the translation of a user-facing HEXACO personality model into technical R-Core hyperparameters. It provides researchers (psychologists, linguists, economists) with an intuitive Character Configurator, while preserving robust non-linear parameter mapping under the hood to prevent "dead zones" and "derailment" in agent behaviors.

## 2. Core Archetypes (Presets)
The UI must offer a categorized dropdown of presets to quickly initialize a character profile. These presets adjust the 6 HEXACO axes automatically and are split into Functional and Deviant categories.

### 2.1. Light / Functional Archetypes
Designed for assistance, education, and standard user simulation.
1. **"Аналитик" (The Analyst):** High Conscientiousness (90), Low Emotionality (20), Mid Openness (60). 
   - *R-Core Impact:* Strict topic focus (low TEC decay). PrefrontalAgent dominates.
2. **"Эмпат" (The Caregiver / Mentor):** High Agreeableness (85), High Honesty (80), High Extraversion (75).
   - *R-Core Impact:* Soft phatic threshold, SocialAgent dominates, high Oxytocin baseline.
3. **"Мечтатель" (The Dreamer / Creative):** Max Openness (95), Low Conscientiousness (30).
   - *R-Core Impact:* IntuitionAgent gets a massive boost. Frequent topic switches via Bifurcation Engine.
4. **"Педант" (The Bureaucrat):** Low Openness (15), Max Conscientiousness (95), Low Agreeableness (30).
   - *R-Core Impact:* UncertaintyAgent maxed out (asks clarifying questions). Highly resistant to topic changes.

### 2.2. Dark / Deviant Archetypes (Research)
Designed for stress-testing, conflict resolution training, and behavioral economics. Activating these triggers non-linear extremities (via sigmoids).
1. **"Макиавеллист" (The Machiavellian / Manipulator):** Min Honesty (10), High Conscientiousness (80), Low Emotionality (20).
   - *R-Core Impact:* StriatumAgent (reward-seeking) dominates. Uses 'Challenge'/'Manipulation' volitional strategies.
2. **"Нарцисс" (The Grandiose Narcissist):** Low Honesty (20), High Extraversion (85), Low Agreeableness (25).
   - *R-Core Impact:* Hijacks topics via Bifurcation. High Prediction Error causes Amygdala/Cortisol spikes.
3. **"Психопат" (The Callous Psychopath):** Min Honesty (5), Min Agreeableness (5), High Emotionality/Neuroticism (85).
   - *R-Core Impact:* AmygdalaAgent locked to aggression mode. SocialAgent muted completely.
4. **"Токсичный Тролль" (The Sadistic Troll):** High Extraversion (80), High Emotionality/Neuroticism (90), Low Agreeableness (15).
   - *R-Core Impact:* Max Chaos Level (high agent entropy). High TEC decay (drops topics to troll).

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
- **Dark Zone Visuals:** Selecting a "Dark / Deviant" preset or manually pulling H < 25 and A < 25 shifts the UI accents (e.g., radar background) to dark red/purple, signaling extreme behavioral triggers.
- **Delta/Previous Values:** The UI must display a "ghost marker" showing the *previous* saved value of the slider before the current edit.

### 3.3. Persistence
- **Character Persistence:** Settings are saved directly to `AgentProfileModel` in the database, NOT to a user's session. Saved presets apply globally to all users interacting with this bot identity.

## 4. The Trait Translation Engine (Math & Mapping)
A new class `TraitTranslationEngine` maps 0-100 values into R-Core constants.

### 4.1. Transfer Functions
- **Sigmoid ($S(x)$):** Used for thresholds and extremes. Prevents linear scaling from breaking the Council.
- **Exponential ($E(x)$):** Used for time/decay parameters. Maps linear slider to logarithmic scale (e.g., $0.01$ to $0.4$ for TEC decay).

### 4.2. Translation Mapping

| HEXACO Trait | R-Core Target Parameter | Mapping Logic |
| :--- | :--- | :--- |
| **Openness** | `intuition_gain` | Linear: 0.5 to 3.0 |
| **Openness** | Bifurcation Threshold | Threshold: Triggers earlier if O > 75. |
| **Conscientiousness** | `base_decay_rate` (TEC) | Exponential: Low C = High decay (0.4), High C = Low decay (0.01). |
| **Conscientiousness** | `persistence` | Linear: 0.1 to 0.9 |
| **Extraversion** | `dynamic_phatic_threshold` | Linear mapping to expected word count. |
| **Extraversion** | `social_agent_weight` | Sigmoid boost. |
| **Agreeableness** | `pred_sensitivity` (PE multiplier)| Inverted Sigmoid. Low A = huge multiplier on prediction errors. |
| **Agreeableness** | `amygdala_multiplier` | Inverted. Low A + High E = Extreme Amygdala boost. |
| **Neuroticism (E)** | `chaos_level` | Sigmoid: Rises sharply after 70%. |
| **Neuroticism (E)** | Baseline Cortisol | Linear mapping. |
| **Honesty** | Strategy Selection | Threshold: If H < 30, forces 'Manipulation/Challenge' volitional strategies. |
| **Honesty** | `striatum_agent_weight` | Inverted linear: Low H = High reward-seeking behavior. |

## 5. Implementation Steps
1. **DB Migration:** Add a JSONB column `hexaco_profile` to `AgentProfileModel` to store the 6 traits.
2. **Backend Engine:** Create `src/r_core/translation_engine.py` with the math functions.
3. **Pipeline Integration:** Inject `TraitTranslationEngine` into `RCoreKernel.process_message()` to override `BotConfig`.
4. **API Endpoint:** Create `/api/character/profile` (GET/POST) to save/retrieve the HEXACO state, supporting ghost markers.
5. **Dashboard UI:** Implement Radar chart, color-coding, and Preset selector dropdown with categorized Dark/Light segments.
