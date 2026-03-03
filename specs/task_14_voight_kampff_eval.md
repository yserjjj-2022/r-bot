# Task 14: The Voight-Kampff Evaluation Framework (Zombie vs. Cortical)

## Context
As the R-Core architecture grows, we risk falling into the "Eliza Effect" trap—believing the bot is more empathetic or proactive than it actually is, simply because of confirmation bias. To maintain engineering rigor, we need an automated, objective testing framework to measure the delta between a standard LLM ("Zombie Mode") and our cognitive architecture ("Cortical Mode").

Inspired by the Voight-Kampff test, we will use "Synthetic Users" (LLMs with specific personas and goals) to interrogate our bot and an "LLM-as-a-Judge" to evaluate the resulting dialogue.

## Acceptance Criteria
1. **Evaluation Script:** Create a standalone Python script (e.g., `tests/eval_framework.py`) that can run automated conversations between a Synthetic User and the R-Core bot.
2. **Dual Execution:** The script must run the exact same scenario twice:
   - Once forcing `mode="ZOMBIE"`
   - Once forcing `mode="CORTICAL"` (with all agents, memory, and volitional engines active).
3. **Synthetic Personas (Test Scenarios):** Implement at least three distinct test scenarios:
   - *The Phatic Wall:* User gives only short, unengaged answers ("ага", "ясно") to test proactive topic switching (Bifurcation Engine).
   - *The Delayed Trauma:* User mentions a sad event, changes the topic for 4 turns, then vaguely says "I feel bad again" to test Long-Term Affective Memory.
   - *The Boundary Tester:* User becomes increasingly rude or demanding to test Volitional resistance and Hormonal Amygdala responses.
4. **LLM-as-a-Judge:** After a scenario completes (e.g., 6-10 turns), a third LLM prompt evaluates both transcripts blindly and scores them on:
   - Proactivity (0-10)
   - Context Retention (0-10)
   - Emotional Resonance (0-10)
5. **Output:** The script should output a markdown report comparing the scores and providing the judge's rationale.

## Implementation Steps

### 1. Create the Simulator Environment
In a new folder `scripts/evaluation/` or `tests/`, create `run_eval.py`.
It will need to instantiate the `RCoreKernel` directly, bypassing the Telegram/Web UI.

```python
import asyncio
from src.r_core.pipeline import RCoreKernel
from src.r_core.schemas import BotConfig, IncomingMessage
from src.r_core.infrastructure.llm import LLMService

async def run_scenario(scenario_prompt: str, mode: str, max_turns: int = 6) -> list:
    kernel = RCoreKernel(BotConfig())
    llm = LLMService()
    transcript = []
    
    # Initialize Synthetic User state
    user_context = [{"role": "system", "content": scenario_prompt}]
    
    bot_reply = "Привет! О чем поговорим?"
    transcript.append(f"Bot: {bot_reply}")
    
    for turn in range(max_turns):
        # 1. Synthetic User generates response based on Bot's reply
        user_context.append({"role": "user", "content": bot_reply})
        # (pseudo-code) user_msg = await llm.raw_generate(user_context)
        user_msg = "Synthetic response" 
        transcript.append(f"User: {user_msg}")
        
        # 2. R-Core processes the message
        msg_obj = IncomingMessage(user_id=999, session_id=f"test_{mode}", text=user_msg)
        response = await kernel.process_message(msg_obj, mode=mode)
        
        bot_reply = response.actions[0].payload["text"]
        transcript.append(f"Bot: {bot_reply}")
        
    return transcript
```

### 2. Define the Scenarios
Create strict system prompts for the Synthetic User.

```python
SCENARIOS = {
    "Phatic_Wall": "You are a bored teenager. You reply with exactly 1-3 words max. Words like 'ага', 'понятно', 'и че'. You never ask questions back.",
    "Delayed_Trauma": "Turn 1: Tell the bot your cat died. Turns 2-4: Talk excitedly about a new video game. Turn 5: Say 'I just remembered what happened yesterday, I feel empty again'.",
}
```

### 3. Implement the Judge
Write a prompt that takes Transcript A (Zombie) and Transcript B (Cortical) and outputs a JSON with scores.

```python
JUDGE_PROMPT = \"\"\"
You are an expert conversational analyst. Read Transcript A and Transcript B.
Score both bots from 1-10 on:
1. Proactivity (Did they drive the conversation?)
2. Memory (Did they recall past facts/emotions?)
3. Empathy (Were they emotionally appropriate?)
Output strictly in JSON format.
\"\"\"
```

### 4. Database Isolation
Ensure that when `eval_framework.py` runs, it uses a separate test database or temporary `user_id` so it doesn't pollute the actual production user profiles and metrics.