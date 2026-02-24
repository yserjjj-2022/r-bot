# Этап 3.1: Topic Tracker — Фикс TEC Decay (Спецификация для локального ИИ-агента)

**CONTEXT FOR AI AGENT:**
You are a Senior Python Developer working on the `r-bot` project. During testing, we discovered that **TEC (Topic Engagement Capacity) does not decay** because it is incorrectly tied to `volitional_patterns` (which track long-term goals, not short-term topic fatigue).

Your task: Implement a **standalone Topic Tracker** that monitors the current conversation topic and calculates TEC decay independently from volitional patterns.

**STRICT RULES:**
1. Do NOT modify database schemas or create new tables. Use in-memory state in `pipeline.py`.
2. Do NOT break existing logic for volitional patterns or prediction processing.
3. Follow the TEC decay formula from `attention-engagement-theory.md` exactly.

---

## Problem Statement

**Current Behavior (BROKEN):**
```python
current_tec = dominant_volition.get("topic_engagement", 1.0)
```
- TEC is extracted from volitional patterns (e.g., `high_energy`).
- Volitional patterns are about **long-term goals** (e.g., "learning Python"), not **short-term topic fatigue**.
- TEC never decays → Bifurcation Engine never triggers.

**Test Log Evidence:**
```
[LC-NE] TEC=1.00, Mode=phasic  # Should decay after 3-4 short replies
[LC-NE] TEC=1.00, Mode=phasic  # Still 1.00 after 5 turns!
```

**Expected Behavior (TARGET):**
```
[LC-NE] TEC=0.85, Mode=phasic  # Turn 1
[LC-NE] TEC=0.60, Mode=phasic  # Turn 2 (short reply → faster decay)
[LC-NE] TEC=0.25, Mode=tonic   # Turn 3 → Bifurcation triggered!
[Bifurcation Engine] Tonic LC detected. Generating hypotheses...
```

---

## Task 1: Add Topic Tracker State in `Pipeline`

**File:** `src/r_core/pipeline.py`

### 1.1 Initialize Topic Tracker in `__init__`
Add a new instance variable to track the current topic:

```python
class Pipeline:
    def __init__(self, ...):
        # ... existing code ...
        
        # ✨ NEW: Topic Tracker (independent from volitional patterns)
        self.current_topic_state = {
            "topic_embedding": None,         # Vector of current topic
            "topic_text": "",                # Text summary of topic
            "tec": 1.0,                      # Topic Engagement Capacity [0.0, 1.0]
            "turns_on_topic": 0,             # Turns spent on this topic
            "intent_category": "Casual",     # Nature taxonomy: Phatic/Casual/Narrative/Deep/Task
            "last_prediction_error": 0.5     # PE from last turn (for decay calculation)
        }
```

---

## Task 2: Update TEC After Each User Reply

**File:** `src/r_core/pipeline.py`, method `process_message`

### 2.1 Calculate TEC Decay (Right After PE Verification)
Locate the section where Prediction Error is calculated and verified (around line ~200-250, after `hippocampus.verify_prediction`). 

**Insert this logic immediately after PE verification:**

```python
# ========== ✨ NEW: Topic Tracker Update ==========
# This block updates TEC based on prediction error and response density

# Step 1: Check if topic has changed (compare embeddings)
topic_changed = False
if self.current_topic_state["topic_embedding"] is not None:
    # Calculate cosine similarity between current message and tracked topic
    from numpy import dot
    from numpy.linalg import norm
    
    current_emb = current_embedding  # Already computed earlier in process_message
    topic_emb = self.current_topic_state["topic_embedding"]
    
    # Cosine similarity
    similarity = dot(current_emb, topic_emb) / (norm(current_emb) * norm(topic_emb))
    
    if similarity < 0.5:
        # Topic has changed significantly
        topic_changed = True
        print(f"[TopicTracker] 🔄 Topic Change Detected (similarity={similarity:.2f}). Resetting TEC.")
else:
    # First turn, initialize topic
    topic_changed = True

# Step 2: Reset TEC if topic changed, otherwise apply decay
if topic_changed:
    self.current_topic_state = {
        "topic_embedding": current_embedding,
        "topic_text": message.text[:100],  # First 100 chars as summary
        "tec": 1.0,
        "turns_on_topic": 1,
        "intent_category": extraction.get("intent_category", "Casual"),  # From LLM extraction
        "last_prediction_error": prediction_error
    }
else:
    # Apply TEC decay formula (from attention-engagement-theory.md Section 4.3)
    self.current_topic_state["turns_on_topic"] += 1
    
    # Base decay by intent category (Nature Taxonomy)
    BASE_DECAY_MAP = {
        "Phatic": 1.0,      # Social rituals: instant burn
        "Casual": 0.4,      # Small talk: fast decay
        "Narrative": 0.15,  # Stories: moderate
        "Deep": 0.05,       # Deep topics: slow decay
        "Task": 0.0         # Task-oriented: no decay until resolved
    }
    
    intent = self.current_topic_state["intent_category"]
    base_decay = BASE_DECAY_MAP.get(intent, 0.3)
    
    # Situational multiplier (formula from attention-engagement-theory.md)
    # High PE = user is disengaged → faster decay
    # Short replies (low response_density) → faster decay
    response_density = min(len(message.text.split()) / 50.0, 1.0)
    situational_multiplier = (0.5 + (1 - prediction_error) * 0.5) * (2.0 - response_density)
    
    effective_decay = base_decay * situational_multiplier
    
    # Apply decay
    old_tec = self.current_topic_state["tec"]
    self.current_topic_state["tec"] = max(0.0, old_tec - effective_decay)
    self.current_topic_state["last_prediction_error"] = prediction_error
    
    print(f"[TopicTracker] TEC: {old_tec:.2f} → {self.current_topic_state['tec']:.2f} "
          f"(decay={effective_decay:.2f}, PE={prediction_error:.2f}, turns={self.current_topic_state['turns_on_topic']})")

# ========== END Topic Tracker Update ==========
```

---

## Task 3: Use Topic Tracker TEC for LC-NE Calculation

**File:** `src/r_core/pipeline.py`, method `process_message`

### 3.1 Replace Volitional TEC with Topic Tracker TEC
Locate the section where `current_tec` is extracted from `dominant_volition` (around line ~400-500, before LC-NE calculation).

**Find this line:**
```python
current_tec = dominant_volition.get("topic_engagement", 1.0)
```

**Replace with:**
```python
# ✨ FIX: Use Topic Tracker TEC instead of volitional pattern TEC
current_tec = self.current_topic_state["tec"]
```

### 3.2 Verify Tonic Boost is Applied Correctly
Ensure the existing code that calculates `tonic_ne_boost` when `TEC < 0.3` remains intact:

```python
# Existing code (DO NOT MODIFY, just verify it's there):
if current_tec < 0.3:
    tonic_ne_boost = max(0, (0.3 - current_tec) * 2.5)
    base_ne += tonic_ne_boost
    lc_mode = "tonic"
    print(f"[LC-NE] Tonic mode: Prefrontal score boosted to {prefrontal_weight + 0.10:.2f}")
```

---

## Task 4: Extract Intent Category from LLM Response

**File:** `src/r_core/pipeline.py`, method `process_message`

### 4.1 Add Intent Category to Extraction Prompt
Locate where you call LLM for memory extraction (the prompt that asks for triples, episodic anchors, etc.).

**Add this instruction to the prompt:**
```python
extraction_prompt = f"""
... existing instructions ...

Additionally, classify the user's message intent into ONE category:
- Phatic: Greetings, goodbyes, ritual phrases ("hi", "how are you")
- Casual: Small talk, weather, daily routines
- Narrative: Stories, past events, anecdotes
- Deep: Values, emotions, existential topics
- Task: Problem-solving, information seeking

Return format:
{{
    "triples": [...],
    "anchors": [...],
    "volitional_pattern": {{...}},
    "intent_category": "Casual"  // ✨ NEW FIELD
}}
"""
```

### 4.2 Store Intent Category in Topic Tracker
The intent category will be used in Task 2 when calculating base decay.

---

## Task 5: Add Logging for Debugging

**File:** `src/r_core/pipeline.py`

### 5.1 Log Topic Tracker State
After calculating TEC in Task 2, add:
```python
print(f"[TopicTracker] State: topic='{self.current_topic_state['topic_text'][:30]}...', "
      f"intent={self.current_topic_state['intent_category']}, "
      f"TEC={self.current_topic_state['tec']:.2f}, "
      f"turns={self.current_topic_state['turns_on_topic']}")
```

---

## Expected Test Results After Implementation

### Scenario: "Boring Conversation" (Short Replies)
**User Input:**
```
Turn 1: "Привет" (Phatic)
Turn 2: "Норм" (Casual, short)
Turn 3: "Ага" (Casual, very short)
Turn 4: "Понятно" (Casual, very short)
```

**Expected Log Output:**
```
[TopicTracker] TEC: 1.00 → 0.60 (decay=0.40, PE=0.5, turns=2)
[LC-NE] TEC=0.60, Mode=phasic

[TopicTracker] TEC: 0.60 → 0.20 (decay=0.40, PE=0.7, turns=3)
[LC-NE] TEC=0.20, Mode=tonic
[LC-NE] Tonic mode: Prefrontal score boosted to 0.60
[Bifurcation Engine] Tonic LC detected. Generating topic switch hypotheses...
```

---

## Testing Checklist

After implementation, verify:
1. ✅ TEC starts at 1.0 for new topics.
2. ✅ TEC decays with each short/predictable reply.
3. ✅ TEC resets to 1.0 when user changes topic (cosine similarity < 0.5).
4. ✅ When TEC < 0.3, `lc_mode` switches to "tonic".
5. ✅ Bifurcation Engine triggers and logs candidate topics.
6. ✅ Volitional patterns still work independently (fuel, intensity, etc.).

---

## Notes for Implementation

- **Do NOT touch volitional pattern logic.** They serve a different purpose (long-term motivation tracking).
- **Topic Tracker is ephemeral.** It resets every time the user changes subject. This is intentional.
- **Intent classification is simple for MVP.** Use LLM's best guess. We can refine later with a specialized classifier.

**END OF SPECIFICATION.**
