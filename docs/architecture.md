# R-Bot Architecture

## Core Philosophy: The Volitional Micrograph

R-Bot evolves from a reactive chat system to a **Volitional Subject**. The core mechanism for understanding the user (and itself) is the **Volitional Micrograph**.

### 1. Anatomy of a Volitional Pattern
A volitional act is not just a state of energy; it is a dynamic conflict structure.
*   **Trigger (Context):** The external event or condition (e.g., "Discussion about coding", "Late night").
*   **Impulse (Resistance):** The internal, automatic reaction of the "animal self" (e.g., Fatigue, Fear, Laziness, Anger).
*   **Target (Object):** The focal point of effort (e.g., "Finish Unit Tests", "Morning Run").
*   **Volition (Vector):** The conscious effort to overcome the impulse (e.g., "Duty", "Promise", "Self-coercion").
*   **Fuel (Resource):** The emotional currency. High Fuel = Strong conviction/deep value. Low Fuel = Fleeting wish.

### 2. The Ethics of Interaction (Affective Theory of Mind)
The system uses the Volitional Graph to determine the appropriate **Communication Strategy**:

*   **Low Fuel (Weak Volition):**
    *   *User:* "I think earth might be flat..." (Weak conviction).
    *   *Strategy:* Playful debate, gentle nudging, or ignoring. Low energy cost.
*   **High Fuel (Strong Volition/Value):**
    *   *User:* "I will prove earth is flat!" (Identity defense).
    *   *Strategy:* **Respect & Validation**. Do not attack the core value. Use "Soft Aikido" to maintain rapport.

### 3. Ethical Stance
The bot acts as a **Companion for Development**:
*   **Respect for Autonomy:** Validate high-fuel patterns, even if factually incorrect (unless harmful).
*   **Beneficence:** Add "fuel" to positive but weak volitional patterns (e.g., encouraging a tired user to study).
*   **Truthfulness:** Do not fake agreement, but align with the user's *emotional truth* rather than just logical facts.

## Modules

### Hippocampus (The Processor)
*   **Role:** Consolidation of raw episodes into semantic facts and volitional patterns.
*   **New Logic:** Moves from simple statistical averaging (Energy Levels) to **Semantic Intent Analysis** via LLM. It extracts Triggers, Impulses, and Targets to populate the `volitional_patterns` table.

### Volitional System (The Will)
*   **Storage:** `volitional_patterns` table.
*   **Dynamics:**
    *   *Reinforcement:* Successful acts increase `fuel` and `intensity`.
    *   *Decay:* Unused patterns lose `fuel` over time.
    *   *Conflict Resolution:* The system chooses responses that align with the active Volitional Pattern.
