# Neuro-Modulation System Specification (R-Core v2.3)

**Status**: ✅ Engineering Spec  
**Model**: **Lövheim Cube of Emotion** (Monoamine Theory)  
**Principle**: Non-linear decay + Archetypal State Classification

---

## 1. The Monoamine Triad + Cortisol
We map internal states to 3 main axes + 1 stress modifier.

| Neurotransmitter | Axis (Lövheim) | Role | Half-life ($T_{1/2}$) | Decay Curve |
| :--- | :--- | :--- | :--- | :--- |
| **Norepinephrine (NE)** | **Attention** | Arousal, Vigilance, Reactivity | **5 min** (Fast) | **Exponential** (Spikes fade quickly) |
| **Dopamine (DA)** | **Motivation** | Reward, Drive, Action | **15 min** (Medium) | **Sigmoid** (Lingers, then drops off) |
| **Serotonin (5-HT)** | **Stability** | Confidence, Satisfaction, Safety | **6 hours** (Slow) | **Linear** (Steady consumption) |
| **Cortisol (CORT)** | *(Modifier)* | Stress, Resource Shutdown | **12 hours** (Chronic) | **Logarithmic** (Hard to clear) |

---

## 2. Non-Linear Metabolic Decay
Unlike simple exponential decay, each hormone has a "physiologically accurate" depletion curve.

### 2.1 Norepinephrine (Flash Response)
$$ NE(t) = NE_0 \cdot e^{-t / 5} $$
*Meaning*: Adrenaline rush is instant but disappears completely in ~20 mins.

### 2.2 Dopamine (The "Crash")
Modeled with a Sigmoid crash. Dopamine stays high for a while ("afterglow"), then crashes rapidly.
*   *Effect*: Motivation sustains a session, but if you leave for an hour, you come back "cold".

### 2.3 Serotonin (Resource Depletion)
$$ 5HT(t) = 5HT_0 - (k \cdot t) $$
*Meaning*: Confidence is a "fuel tank". It depletes linearly over the day. Sleep (long gap) restores it.

### 2.4 Cortisol (Accumulation)
Cortisol is hard to clear.
*   *Clearance*: Very slow linear decay.
*   *Interaction*: High `5-HT` accelerates Cortisol clearance (Safety heals stress).

---

## 3. The Lövheim Cube (State Classification)
We binarize the 3 axes (Threshold = 0.5) to find the active Archetype.

| 5-HT | DA | NE | Archetype | Style Instruction (Contextual) |
| :--- | :--- | :--- | :--- | :--- |
| 0 | 0 | 0 | **SHAME / DEPRESSION** | `[STYLE: Passive, apologetic, very short. Low energy.]` |
| 0 | 1 | 0 | **SURPRISE / SEEKING** | `[STYLE: Curious, questioning. Ask for info. High engagement.]` |
| 0 | 0 | 1 | **FEAR / ANXIETY** | `[STYLE: Nervous, defensive, hesitant. Use ellipses...]` |
| 0 | 1 | 1 | **RAGE / ANGER** | `[STYLE: Aggressive, sharp, imperative. No politeness.]` |
| 1 | 0 | 0 | **CALM / CONTENT** | `[STYLE: Relaxed, warm, narrative. Long flowing sentences.]` |
| 1 | 1 | 0 | **JOY / SATISFACTION** | `[STYLE: Playful, humorous, enthusiastic. Use emojis.]` |
| 1 | 0 | 1 | **DISGUST / CONTEMPT** | `[STYLE: Cold, cynical, superior. Formal and distant.]` |
| 1 | 1 | 1 | **EXCITEMENT / TRIUMPH** | `[STYLE: High energy leader. Inspiring, bold, fast-paced.]` |

### 3.1 The Cortisol Modifier
If `CORT > 0.8` (Chronic Stress), it overrides the Cube:
*   **BURNOUT**: `[STYLE: Dumbed down, repetitive, confused. Unable to process complexity.]`

---

## 4. Implementation Strategy
1.  **Metabolism**: Calculate specific decay for each hormone based on `delta_minutes`.
2.  **Classification**: Determine the Octant (Archetype).
3.  **Instruction**: Fetch the single, non-contradictory prompt for that Archetype.
