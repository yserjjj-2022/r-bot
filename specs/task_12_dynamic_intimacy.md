# Task 12: Dynamic Intimacy & Trust Gradient (No-Migration Schema)

## Context
Currently, the bot's communication style is binary: `formal` ("Вы") or `informal` ("Ты"). However, human relationships develop gradually. We want to experiment with "gradations of intimacy" (доверительность) where the bot transitions from a polite stranger to a close friend based on shared history, emotional resonance, and time spent together.

Importantly, trust can also **decrease** if the user is toxic, ignores the bot, or doesn't interact for a long time. 

To avoid schema bloat, we will store these metrics inside the existing `attributes` JSONB field rather than creating new database columns.

## Acceptance Criteria
1. **No SQL Migrations:** Use the existing `attributes` JSONB field in `UserProfileModel` to store `intimacy_score` (float 0.0 to 1.0) and `trust_stage` (string).
2. **Intimacy Engine (Growth & Decay):** Create logic to update the score after each session or during memory consolidation:
    - **Growth:** +0.01 per conversation turn, +0.05 for deep emotional topics.
    - **Decay (Time):** -0.05 if the user hasn't interacted for > 3 days.
    - **Penalty (Conflict):** -0.1 if user toxicity or high negative arousal is detected (e.g., Rage archetype triggered).
3. **Dynamic Prompting:** Update `llm.py` so that the `address_block` scales based on `intimacy_score`:
    - `0.0 - 0.3` (Stranger): Polite, distant, formal ("Вы" or very respectful "Ты").
    - `0.3 - 0.7` (Acquaintance): Casual, friendly but respects boundaries.
    - `0.7 - 1.0` (Close Friend): High empathy, emotionally open, informal.
4. **Integration with Task 13:** Ensure the prompt sanitizer (`utils.py -> sanitize_bot_history`) correctly reads the `intimacy_score` from the JSON attributes to conditionally remove diminutives.

## Implementation Steps

### 1. Intimacy Calculation Engine (`src/r_core/social_dynamics.py` or similar)
Create a helper function to calculate the new score.

```python
def calculate_new_intimacy(current_score: float, turn_metrics: dict) -> float:
    \"\"\"
    Calculates the new intimacy score based on turn events.
    \"\"\"
    new_score = current_score
    
    # 1. Base growth per interaction
    new_score += 0.005 
    
    # 2. Emotional bonding (Affective ToM triggers)
    if turn_metrics.get("affective_triggers_detected", 0) > 0:
        new_score += 0.02
        
    # 3. Penalties for conflict / rage
    if turn_metrics.get("hormonal_archetype") in ["RAGE", "PANIC"]:
        new_score -= 0.05
        
    # Cap between 0.0 and 1.0
    return max(0.0, min(1.0, new_score))
```

### 2. Update Profile in Pipeline (`src/r_core/pipeline.py`)
At the end of `process_message`, extract the current score from `user_profile.attributes`, update it using the helper, and save it back to the database using `self.memory.update_user_profile()`.

```python
        # Extract current score
        attributes = user_profile.get("attributes", {}) if user_profile else {}
        current_intimacy = attributes.get("intimacy_score", 0.0)
        
        # Calculate new score using the stats we just gathered
        new_intimacy = calculate_new_intimacy(current_intimacy, internal_stats)
        
        # Determine Trust Stage for logging/UI
        if new_intimacy < 0.3: trust_stage = "stranger"
        elif new_intimacy < 0.7: trust_stage = "acquaintance"
        else: trust_stage = "friend"
        
        # Save back to DB (only if changed significantly to save DB writes, or every turn)
        attributes["intimacy_score"] = new_intimacy
        attributes["trust_stage"] = trust_stage
        await self.memory.update_user_profile(message.user_id, {"attributes": attributes})
```

### 3. LLM Prompt Modification (`src/r_core/infrastructure/llm.py`)
In `generate_response`, inject dynamic relationship instructions into the system prompt based on `intimacy_score`.

```python
        # Example addition to system prompt building:
        intimacy_instruction = ""
        if intimacy_score < 0.3:
            intimacy_instruction = "Keep emotional distance. Be polite, formal, and objective. Do not act overly familiar."
        elif intimacy_score < 0.7:
            intimacy_instruction = "Act as a friendly acquaintance. You can be warm and casual, but respect boundaries."
        else:
            intimacy_instruction = "Act as a close, trusted friend. Be highly empathetic, emotionally open, and deeply supportive."
```

### 4. Optional UI / Metrics
Log `new_intimacy` into `rcore_metrics` payload so it can be visualized on the dashboard.