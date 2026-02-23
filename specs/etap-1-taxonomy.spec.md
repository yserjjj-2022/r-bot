# Этап 1: Таксономия и TEC Decay (Спецификация для локального ИИ-агента)

**CONTEXT FOR AI AGENT:**
You are a Senior Python Developer working on the `r-bot` project (a cognitive AI architecture). Your task is to implement "Stage 1: Taxonomy and TEC Decay" based on the `attention-engagement-theory.md` document. 

**STRICT RULE:** Do NOT modify database schemas directly via SQLAlchemy migrations (Alembic) or raw SQL strings in Python files. The user will handle database migrations manually in DBeaver using the provided SQL script. Your focus is strictly on Python code (`models.py`, `llm.py`, `pipeline.py`).

---

## Task 1: Update SQLAlchemy Model (`src/r_core/models.py`)

Locate the `VolitionalPattern` model. We need to add the new TEC/Taxonomy fields and ensure legacy fields don't cause insertion errors.

1. **Add new columns:**
   - `intent_category`: `String(50)` (default `"Casual"`)
   - `topic_engagement`: `Float` (default `1.0`)
   - `base_decay_rate`: `Float` (default `0.12`)
   - `complexity_modifier`: `Float` (default `1.0`)
   - `emotional_load`: `Float` (default `0.0`)
   - `recovery_rate`: `Float` (default `0.05`)

2. **Handle Legacy Fields (Data Contract):**
   Ensure the following existing fields have `nullable=True` or a safe `default` so that creating a new `VolitionalPattern` without them won't crash SQLAlchemy:
   - `conflict_detected` (Boolean, default False)
   - `resolution_strategy` (String, nullable=True)
   - `action_taken` (String, nullable=True)
   - `energy_cost` (Float, default 0.0)
   - `target` (String, nullable=True)

---

## Task 2: Update LLM Intent Classification (`src/r_core/infrastructure/llm.py`)

Locate `detect_volitional_pattern`. We are transforming this from a pure "conflict loop" detector into a general **Topic & Intent Tracker**.

1. **Update the `system_prompt`:**
   Remove the old "Behavioral Psychologist looking for procrastination loops" focus.
   Instead, instruct the LLM to track the current topic and classify the user's intent into one of 5 categories (Nature Taxonomy):
   - **Phatic**: Greetings, goodbyes, pure social rituals.
   - **Casual**: Small talk, weather, brief factual exchanges.
   - **Narrative**: Storytelling, recounting day's events.
   - **Deep**: Core values, fears, identity, philosophy.
   - **Task**: Instrumental goals, coding, debugging, planning.

2. **Update JSON Output Format in Prompt:**
   ```json
   { 
     "pattern_found": true, 
     "topic": "Brief 1-3 word topic name (e.g. Python Async)", 
     "intent_category": "Phatic|Casual|Narrative|Deep|Task"
   }
   ```
   *(Keep `pattern_found: false` for empty/meaningless noise)*

3. **Update the Python `return` dict:**
   Instead of returning `trigger`/`impulse`, return:
   ```python
   return {
       "topic": data.get("topic", "General"),
       "intent_category": data.get("intent_category", "Casual"),
       "topic_engagement": 1.0, # Fresh start
       "fuel": 1.0,
       "intensity": 0.5
   }
   ```

---

## Task 3: Implement TEC Decay Logic (`src/r_core/pipeline.py`)

We need to implement the formulas from `attention-engagement-theory.md` and modify how `learned_delta` (reinforcement) works.

1. **Add a helper dictionary/method for Base Decay (Nature):**
   ```python
   BASE_DECAY_MAP = {
       "Phatic": 1.0,
       "Casual": 0.4,
       "Narrative": 0.15,
       "Deep": 0.05,
       "Task": 0.0  # Does not decay automatically
   }
   ```

2. **Locate or create `_update_volitional_patterns`:**
   For the active pattern, calculate `effective_decay`:
   - Get `base_decay` from the map using `pattern.intent_category`.
   - Calculate `situational_multiplier`: `(0.5 + (1 - current_PE) * 0.5) * (2.0 - response_density)`
     *(Assume `response_density` is `min(len(user_text.split()) / 50.0, 1.0)`)*
   - `effective_decay = base_decay * situational_multiplier`
   - Apply: `pattern.topic_engagement = max(0.0, pattern.topic_engagement - effective_decay)`
   - *(Note: Nurture modifiers like Importance/Novelty from Memory will be added in Stage 3. Skip them for now).*

3. **Locate `_apply_reinforcement` (or where `learned_delta` is updated):**
   Change the logic to respect TEC exhaustion:
   ```python
   # OLD logic:
   if current_PE < 0.2:
       pattern.learned_delta += rate
       
   # NEW logic:
   if current_PE < 0.2 and pattern.topic_engagement > 0.5:
       pattern.learned_delta += rate
   ```

---

## Task 4: Provide SQL Migration Script

At the very end of your response, output a raw SQL script block (PostgreSQL/SQLite syntax depending on what is inferred) that the user can run in DBeaver to safely add the new columns to the `volitional_patterns` table without dropping data.

Example:
```sql
ALTER TABLE volitional_patterns ADD COLUMN intent_category VARCHAR(50) DEFAULT 'Casual';
ALTER TABLE volitional_patterns ADD COLUMN topic_engagement FLOAT DEFAULT 1.0;
-- etc...
```

**END OF CONTEXT.**
