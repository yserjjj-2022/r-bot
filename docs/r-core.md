# R-Core Architecture

**Version**: 2.0 (Prototype)
**Core Concept**: A modular cognitive architecture inspired by predictive processing and cortical specialization.

---

## 🏗️ High-Level Overview

R-Core is not just a prompt wrapper. It is a **cognitive kernel** that orchestrates specialized "agents" (simulating brain regions) to process information, maintain state (mood), and generate adaptive responses.

### Key Components

1.  **Memory System**: Semantic (Facts), Episodic (Experiences), Volitional (Goals).
2.  **Mood System**: A VAD (Valence-Arousal-Dominance) vector that evolves over time.
3.  **Cognitive Parliament**: A set of specialized agents that analyze input in parallel.
4.  **Integration (The Council)**: The mechanism for resolving conflicts between agents.
5.  **Predictive Processing**: Constant comparison of expected vs. actual user reactions.

---

## 🧠 Neuro-Cognitive Architecture (v2.1 Update)

*Added: Feb 2026*

R-Core implements a biological decision-making model based on the interplay between the **Basal Ganglia (Selection)** and **Neuromodulation (Style)**.

### 1. The Problem of "Schizophrenic" AI
In traditional "Winner-Takes-All" systems, if the Safety agent wins (score 9) against Logic (score 8), the bot becomes purely defensive, ignoring valid logical arguments. This creates robotic, binary behavior.

### 2. The Solution: Gating & Modulation
We distinguish between **WHAT** we do (Action) and **HOW** we do it (Adverbs).

#### A. Striatal Gating (Action Selection)
*   **Biological Analogy**: The Striatum (Basal Ganglia) inhibits all actions except the strongest one.
*   **Mechanism**: The Agent with the highest score determines the **Primary Intent**.
    *   *Example*: If Amygdala wins, the intent is "DEFEND/WITHDRAW".
    *   *Rule*: **Winner-Takes-All** applies strictly to the choice of action type to prevent conflicting goals (e.g., trying to apologize and attack simultaneously).

#### B. Neuromodulation (Style Blending)
*   **Biological Analogy**: Neurotransmitters (Dopamine, Norepinephrine) from "losing" regions still flood the global workspace, coloring the execution.
*   **Mechanism**: Losing agents with high scores (>5) inject **Adverbs/Style Constraints** into the response generation.
    *   *Example*:
        *   **Winner**: Amygdala (Score 9) -> Action: "Refuse the request."
        *   **Strong Loser**: Prefrontal (Score 7) -> Modifier: "...but do it **logically** and **precisely**."
        *   **Weak Loser**: Social (Score 2) -> Modifier: "...ignoring politeness."
    *   **Result**: "I cannot fulfill this request because it violates safety protocol X." (Cold, precise refusal).

---

## 🏛️ The Cognitive Parliament (Agents)

### 1. Amygdala (Safety & Threat)
*   **Role**: Threat detection, boundary defense.
*   **Trigger**: Aggression, insults, ambiguity, high risk.
*   **Output**: Urgency signal, "Freeze/Fight/Flight" intent.

### 2. Prefrontal Cortex (Logic & Planning)
*   **Role**: Executive function, planning, analysis.
*   **Trigger**: Complex tasks, questions, logical inconsistencies.
*   **Output**: Structured plans, factual corrections.

### 3. Social Cortex (Empathy & Norms)
*   **Role**: Social maintenance, Theory of Mind.
*   **Trigger**: Emotional displays, greetings, social rituals.
*   **Output**: Politeness, validation, emotional support.

### 4. Striatum (Reward & Desire)
*   **Role**: Motivation, curiosity, play.
*   **Trigger**: Novelty, jokes, opportunities for gain/fun.
*   **Output**: Engagement, playfulness, curiosity.

### 5. Intuition (System 1)
*   **Role**: Fast pattern matching (Déjà vu).
*   **Trigger**: Similarity to past episodic memories.
*   **Output**: "I've seen this before" signal (low latency).

---

## 🔄 The Cognitive Cycle (Pipeline)

1.  **Perception**: User text is received.
2.  **Memory Retrieval**: Context (semantic & episodic) is fetched.
3.  **Council Report (LLM)**: Single-pass analysis by all cortical agents (Amygdala, PFC, Social, Striatum).
4.  **Signal Parsing**: Raw scores (0-10) and rationales are extracted.
5.  **Integration (New!)**:
    *   Apply Personality Sliders (multipliers).
    *   **Gating**: Select Winner (Highest Score).
    *   **Modulation**: Collect "Style Injectors" from runners-up.
6.  **Response Generation**: LLM generates text using the Winner's Intent + Losers' Adverbs + Mood.
7.  **Prediction**: System predicts user's next reaction (Predictive Processing).
8.  **Learning**: Update memories and mood based on Prediction Error from *previous* turn.

---

## 🔮 Future Work

- **Hierarchical Gating**: Allowing sub-goals (e.g., "Social" wins overall, but "Logic" handles a sub-clause).
- **Active Inference**: Bot asking questions to reduce uncertainty (minimize entropy).
