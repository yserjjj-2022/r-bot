# Neuro-Modulation System Specification (R-Core v2.2)

**Status**: ✅ Engineering Spec  
**Principle**: "Mechanical Summation before Cognitive Processing"  
**Goal**: Reduce LLM latency/tokens by calculating state deterministically in Python.

---

## 1. The "Big Four" Hormones
We model internal state using 4 float values (0.0 - 1.0).

| Hormone | Symbol | Semantic Role | Decay (Half-life) | Triggers (Inputs) |
| :--- | :--- | :--- | :--- | :--- |
| **Norepinephrine** | `NE` | **Arousal / Attention**. Reactivity to novelty. | **Short** (5 min) | Spikes on Prediction Error. Decays rapidly to calm. |
| **Dopamine** | `DA` | **Motivation / Reward**. Drive to act. | **Medium** (15 min) | Spikes on positive triggers (In Sync). |
| **Serotonin** | `5HT` | **Stability / Patience**. Impulse control. | **Long** (6 hours) | Accumulates with "Time in Sync". Buffers negative inputs. |
| **Cortisol** | `CORT` | **Stress / Defense**. Resource shutdown. | **Very Long** (12 hours) | Accumulates on "Lost" state or aggression. Blocks PFC. |

---

## 2. Temporal Metabolism (The "Sense of Time")

Before any text processing, the system "metabolizes" the time passed since the last interaction (`delta_t` in minutes).

### Decay Formulas
All hormones decay towards a baseline (usually 0.0 or 0.1) using an exponential decay function:
$$ H_{new} = H_{old} \times (0.5)^{\frac{\Delta t}{half\_life}} $$

### Emergent Effects
1.  **"Wake Up" Effect** (`Delta > 8 hours`):
    *   `NE` drops to ~0 (Calm).
    *   `CORT` drops significant (Stress release).
    *   Result: Bot greets the user freshly, forgetting yesterday's irritation.
2.  **"Ping-Pong" Effect** (`Delta < 30 seconds`):
    *   `NE` has no time to decay -> Accumulates high -> High Tempo.

---

## 3. Mechanical Summation (Python Layer)

We map hormones + time into **3 Control Signals** using simple linear algebra.

### Signal A: `Tempo` (0.0 - 1.0)
*Controls response length and speed.*
$$ Tempo = NE + (0.5 \times CORT) - (0.5 \times 5HT) $$
*   **> 0.8 (High)**: "Burst Mode". Short sentences. No intros.
*   **< 0.3 (Low)**: "Narrative Mode". Flowing, reflective text.

### Signal B: `SocialTemperature` (0.0 - 1.0)
*Controls warmth and openness.*
$$ Temp = 5HT + DA - CORT $$
*   **> 0.7 (Warm)**: Polite, using emojis, supportive.
*   **< 0.3 (Cold)**: Dry, formal, distant.

### Signal C: `CognitiveLoad` (0.0 - 1.0)
*Controls how much "thinking" is allowed.*
$$ Load = 1.0 - CORT + (0.3 \times DA) $$
*   **Low Load (< 0.4)**: Block complex logic. Fallback to simple answers. (Stress stupidity).

---

## 4. Token-Efficient Style Injection

Instead of describing the state, we inject **Pre-Computed Constraints**.

| Combined State | Generated System Instruction (Max 10 tokens) |
| :--- | :--- |
| **High Tempo** | `[CONSTRAINT: Max 15 words. Direct answer.]` |
| **Low Tempo** | `[STYLE: Relaxed, narrative, detailed.]` |
| **High Cortisol** | `[TONE: Defensive, cold, minimal.]` |
| **High Dopamine** | `[TONE: Enthusiastic, pro-active!]` |

This bypasses the need for the LLM to "reason" about emotions. It just follows formatting constraints.
