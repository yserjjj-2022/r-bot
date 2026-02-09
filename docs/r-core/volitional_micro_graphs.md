# Volitional Micro-Graphs: A Framework for Behavioral Analysis and NPC Logic

## Concept Origin
This concept originated from the "Grounded Theory AI" project, where we used LLMs to reconstruct the "volitional act" of respondents (investors) based on their interview answers. We found that breaking down a textual response into a structured causal graph provides a powerful model of human decision-making.

## The Core Model (v1.0)
Instead of treating text as a bag of words, we treat behavior as a **Volitional Graph** consisting of specific node types:
1.  **TRIGGER**: External stimulus (e.g., "Boss advises IPO", "Enemy attacks").
2.  **STATE**: Internal context (e.g., "Belief in market efficiency", "Low health").
3.  **IMPULSE**: System 1 automatic response (e.g., "Desire to copy", "Fear/Flight").
4.  **GOAL**: System 2 conscious intention (e.g., "Buy undervalued asset", "Protect the king").
5.  **CONFLICT**: The clash between competing signals (e.g., Impulse vs Goal).
6.  **INHIBITION**: The "willpower" mechanism (Veto power).
7.  **ACTION**: The observable outcome.

## Synthetic Model v2.0 (Integrated with COM-B)
Synthesizing the micro-graph approach with the COM-B model (Capability, Opportunity, Motivation - Behavior) results in a more robust 8-step process.

### The 8-Step Volitional Cycle
1.  **CONTEXT (Pre-conditions)**
    *   *State*: Internal psychophysiological state (beliefs, fatigue, mood).
    *   *Capability*: Physical and psychological skills required.
    *   *Opportunity*: External factors and social norms facilitating/hindering action.
2.  **TRIGGER**
    *   External or internal stimulus initiating the cycle.
3.  **DOUBLE ACTIVATION (Motivation)**
    *   *Impulse (System 1)*: Automatic, habitual, or emotional reaction (Automatic Motivation).
    *   *Goal (System 2)*: Reflective, conscious intention or plan (Reflective Motivation).
4.  **CONFLICT**
    *   The collision point. If Impulse == Goal, skip to Action. If Impulse != Goal, engage Regulation.
5.  **REGULATION & CHECK**
    *   *Inhibition*: The "free won't" mechanic; suppressing the Impulse.
    *   *Capacity Check*: Verifying if current resources (Willpower/Capability) are sufficient to sustain Inhibition.
6.  **ARBITRATION**
    *   The collapse of the wave function. The final decision is made: Impulse wins (failure), Goal wins (success), or Compromise.
7.  **ACTION**
    *   Observable behavior.
8.  **REFLECTION & FEEDBACK**
    *   Updating the *Context* based on the outcome. Success increases Capability (Self-Efficacy); failure alters State.

## Applications in R-Bot and Games

### 1. Advanced NPC Logic (Cognitive Agents)
Instead of simple state machines or behavior trees, NPCs can run a "Volitional Cycle":
*   **Dynamic Reactions**: An NPC doesn't just "attack if hostile". They process: *Insult (Trigger) -> Anger (Impulse) -> Fear of Guards (Inhibition) -> Arbitration -> Calculated Insult Back (Action).*
*   **Emergent Storytelling**: Conflicts can be resolved differently based on dice rolls or hidden "Willpower" stats, creating unpredictable but logical narrative twists.

### 2. Player Profiling & Analysis
The system can analyze **player** text inputs (in text-based RPGs) to build a psychometric profile:
*   "Player A consistently skips the 'Inhibition' phase and acts on 'Impulse'." -> Tag: *Impulsive/Aggressive*.
*   "Player B always seeks 'Information' (State) before 'Action'." -> Tag: *Analytical*.
This allows the Game Master (AI) to adapt the narrative to the player's psychological type.

### 3. AI Interviewer (Evaluation)
In serious games or HR bots:
*   **Real-time probing**: If the user describes an Action but the Graph misses the "Reasoning/Goal" node, the bot can ask: *"What was your intention behind this?"*
*   **Competence Assessment**: We can measure "Volitional Competence" — how well a candidate manages Conflicts and inhibits negative Impulses.

## Technical Implementation
The core engine uses a single LLM prompt to extract `nodes` (Trigger, Impulse, etc.) and `edges` (triggers, inhibits, leads_to) from a text chunk. This JSON structure is then saved to the database, allowing for:
- Visualization (Force-directed graphs).
- Quantitative analysis (counting "Failed Inhibitions").
- Logic scripting (if Conflict > Willpower then Fail).
