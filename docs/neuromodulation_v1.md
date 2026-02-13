# Neuro-Modulation System V1 (Technical Manual)

## 1. Overview
The Neuro-Modulation System (NMS) provides a biological "body" for the R-Bot cognitive architecture. It acts as a bridge between the **Cognitive Agents** (Amygdala, Prefrontal, etc.) and the **Final Output**.

**Core Loop:**
`Stimuli -> Hormonal Update -> Mood (VAD) -> Style/Pacing Modulation`

## 2. Hormonal Physics Engine
Instead of abstract "emotions", the bot simulates 4 neurotransmitters with specific decay and synthesis rates.

| Hormone | Role | Triggers | Decay (Half-life) |
|---|---|---|---|
| **Dopamine (DA)** | Reward, Motivation, Confidence | Success, Praise, Novelty | Fast (15 min) |
| **Noradrenaline (NE)** | Stress, Focus, Aggression | Threat, Conflict, High Stakes | Medium (30 min) |
| **Serotonin (5-HT)** | Satisfaction, Calm, Stability | Social bonding, Agreement, Time | Slow (60 min) |
| **Cortisol (CORT)** | Anxiety, Caution, Submission | Failure, Confusion, Punishment | Very Slow (120 min) |

### Metabolic Rules
- **Decay:** Every interaction calculates `delta_t` since the last turn. Hormones decay towards baseline (0.5 or 0.1).
- **Synthesis:** Winning agents inject hormones (e.g., Amygdala winner -> +NE, +CORT).

## 3. The Lovheim Cube (VAD System)
Hormonal levels are mapped to the **VAD** (Valence, Arousal, Dominance) emotional vector using the Lovheim Cube of Emotion theory.

- **Valence (Pleasure):** High DA + High 5HT - High CORT
- **Arousal (Energy):** High NE + High DA - High 5HT
- **Dominance (Control):** High DA + High NE - High CORT

This ensures that the bot's "Mood" is physically consistent with its "Body".

## 4. Style & Pacing Control
The `MoodVector` directly controls the text generation style (syntax).

### Arousal & Pacing
- **High Arousal (> 0.7) OR Fast Pace Setting:**
  - *Instruction:* "Max 2 sentences. Be concise."
  - *Effect:* Short, punchy, telegraphic sentences.
- **Low Arousal (< -0.7) OR Slow Pace Setting:**
  - *Instruction:* "Long, flowing sentences. Elaborate thoughts."
  - *Effect:* Philosophical, verbose, pausing ("...").
- **Neutral:**
  - *Instruction:* "Conversational brevity. Keep it natural (2-4 sentences)."

### Dominance & Stance
- **High Dominance:** Imperative, absolute statements.
- **Low Dominance:** Hesitant, "perhaps", "sorry".

## 5. Unified Council
The "Council of Agents" now processes **Intuition** along with other agents in a single pass (if `use_unified_council` is enabled).

- **Intuition Gain:** A multiplier (default 1.0) to tune how loud the "gut feeling" is compared to rational agents.
- **Affective ToM:** If emotional keywords are detected, the system performs a "Full Council" extracting semantic emotional triples (e.g., `User HATES Deadlines`).

## 6. Analytics Dashboard (Encephalogram)
A new Streamlit interface tab provides real-time visualization:
1.  **Agent Conflict Graph:** Who is winning?
2.  **Hormonal Timeline:** NE/DA/5HT/CORT levels.
3.  **VAD State:** Numerical mood display.
4.  **Interaction History:** Detailed logs of every thought process.
