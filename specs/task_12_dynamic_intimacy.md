# Task 12: Dynamic Intimacy & Trust Gradient

## Context
Currently, the bot's communication style is binary: `formal` ("Вы") or `informal` ("Ты"). However, human relationships develop gradually. A user wants to experiment with "gradations of intimacy" (доверительность) where the bot transitions from a polite stranger to a close friend based on shared history, emotional resonance, and time spent together.

This aligns perfectly with our goal of "flexible and innovative study of human behavior" by allowing us to study how users react to a machine that *earns* their trust.

## Acceptance Criteria
1. **Database Schema Update:** Add an `intimacy_score` (float 0.0 to 1.0) and `trust_level` (enum/string) to the `user_profiles` table.
2. **Intimacy Engine:** Create a mechanism (e.g., in `hippocampus.py` or a new `social_dynamics.py`) that calculates the `intimacy_score` based on:
    - Number of total interactions (session length).
    - Accumulation of emotional anchors (from Affective ToM).
    - Successful volitional resolutions (bot helped user solve a problem).
3. **Dynamic Prompting:** Update `llm.py` so that the `address_block` scales based on `intimacy_score`:
    - `0.0 - 0.3`: Polite, distant, formal ("Вы" or very respectful "Ты").
    - `0.3 - 0.7`: Casual acquaintance, friendly but respects boundaries.
    - `0.7 - 1.0`: Close friend, high empathy, uses comfortable nicknames (if allowed), deep emotional mirroring.
4. **Metrics:** Log changes in `intimacy_score` to `rcore_metrics` for dashboard visualization.

## Implementation Steps

### 1. Database Update (`src/r_core/infrastructure/db.py`)
Add fields to `UserProfileModel`:
```python
    intimacy_score: Mapped[float] = mapped_column(Float, default=0.1) # 0.0 to 1.0
    trust_stage: Mapped[str] = mapped_column(String(20), default="stranger") # stranger, acquaintance, friend, confidant
```
Add migration logic in `init_models()`.

### 2. Intimacy Calculation (e.g., during Consolidation)
In `hippocampus.py` (or pipeline), whenever memory consolidation happens, recalculate intimacy:
- Base increase per 100 messages.
- Bonus for high `emotion_score` episodic memories.
- Bonus for semantic facts where `predicate` in `["LOVES", "FEARS", "TRUSTS"]`.

### 3. LLM Prompt Modification (`src/r_core/infrastructure/llm.py`)
Replace the binary `user_mode` check with a gradient system based on the profile's `intimacy_score`.

*Example Logic:*
```python
if intimacy_score < 0.3:
    address_block = "Address the user politely but keep emotional distance. Avoid overly personal questions."
elif intimacy_score < 0.7:
    address_block = "Address the user as a friendly acquaintance. Be warm, use 'ТЫ', but respect boundaries."
else:
    address_block = "Address the user as a close, trusted friend. Be highly empathetic, emotionally open, and deeply supportive."
```

### 4. Optional Override
Ensure there is still a manual override in the UI (e.g., a slider or dropdown in the User Profile dashboard) to force a specific trust level for testing purposes.