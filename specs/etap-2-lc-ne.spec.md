# Этап 2: LC-NE Integration (Спецификация для локального ИИ-агента)

**CONTEXT FOR AI AGENT:**
You are a Senior Python Developer working on the `r-bot` project (a cognitive AI architecture). Your task is to implement "Stage 2: LC-NE Integration" based on the `attention-engagement-theory.md` document. 

**STRICT RULE:** Do NOT modify database schemas directly via SQLAlchemy migrations (Alembic) or raw SQL strings in Python files. Your focus is strictly on Python code (`neuromodulation.py` and `pipeline.py`).

---

## Task 1: Update Locus Coeruleus (LC) Mode Logic (`src/r_core/infrastructure/neuromodulation.py`)

Locate the `NeuroModulationSystem` class (or where neurotransmitters like Norepinephrine/NE are managed). We need to connect the `TEC` (Topic Engagement Capacity) value to the Tonic NE level.

1. **Add `get_lc_mode()` method:**
   Add a new method to the neuromodulation system that determines the current LC mode based on TEC:
   ```python
   def get_lc_mode(self, current_tec: float) -> str:
       """
       Determines the Locus Coeruleus mode based on Topic Engagement Capacity.
       Returns 'phasic' (Exploitation) or 'tonic' (Exploration).
       """
       if current_tec < 0.3:
           return "tonic"
       return "phasic"
   ```

2. **Update `metabolize_time()` or neurotransmitter update logic:**
   Modify the method that updates neurotransmitter levels (specifically Norepinephrine/NE). It needs to accept `current_tec` as an optional parameter (defaulting to 1.0).
   - If `current_tec < 0.3`:
     Calculate a Tonic NE boost: `tonic_ne_boost = (0.3 - current_tec) * 2.5`
     Add this boost to the current NE level (ensuring it doesn't exceed 1.0 or the maximum allowed value for hormones).
   - *Note: This boost forces the system into a SURPRISE/SEEKING state, signaling readiness for a topic switch.*

---

## Task 2: Connect LC Mode to Pipeline (`src/r_core/pipeline.py`)

Locate the main dialogue processing pipeline (likely in `process_message`).

1. **Extract current TEC:**
   After finding the `dominant_volition` (the active pattern), extract its `topic_engagement` value. If there's no active pattern, default to `1.0`.

2. **Determine LC Mode:**
   Call `self.neuromodulation.get_lc_mode(current_tec)` to get the mode (`"phasic"` or `"tonic"`).

3. **Apply Hormonal Modulation with TEC:**
   If you call a method to update hormones based on stimuli (e.g., `update_from_stimuli`), or during temporal metabolism, ensure `current_tec` influences the NE level as implemented in Task 1.

4. **Modify Prefrontal Agent Score (The Exploration Bias):**
   Locate where the `signals` (Agent scores) are evaluated (e.g., inside `_process_unified_council` or right before the arbitration step where `signals.sort(key=lambda s: s.score, reverse=True)` happens).
   - If `lc_mode == "tonic"`:
     Find the `AgentSignal` for the `Prefrontal` agent and increase its score by 10% (multiply by 1.1), capped at 10.0.
     *Rationale: In tonic mode (exploration), the system needs higher cognitive control (Prefrontal) to plan a topic switch.*

---

## Task 3: Update Metrics Logging (`src/r_core/pipeline.py`)

Ensure the new LC-NE state is logged for research and dashboarding.

1. **Update `internal_stats` / `rcore_metrics` payload:**
   Locate where `internal_stats` dictionary is built right before calling `log_turn_metrics`.
   Add the following keys to the payload:
   - `"lc_mode"`: The string returned by `get_lc_mode()` (e.g., `"phasic"`)
   - `"tec_value"`: The `current_tec` value used.

**END OF CONTEXT.**