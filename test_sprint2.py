import asyncio
from src.r_core.schemas import BotConfig, PersonalitySliders, IncomingMessage
from src.r_core.pipeline import RCoreKernel
from src.r_core.infrastructure.db import init_models
import os

async def test_bot(name: str, sliders: PersonalitySliders, text: str):
    print(f"\n{'='*20} TESTING BOT: {name} {'='*20}")
    print(f"Input: '{text}'")
    print(f"Profile: Empathy={sliders.empathy_bias}, Dominance={sliders.dominance_level}")

    # 1. Init Config
    config = BotConfig(
        character_id="test_v1",
        name=name,
        sliders=sliders,
        core_values=["test"]
    )

    # 2. Init Kernel (Database connection happens inside)
    # The kernel initializes MemorySystem -> PostgresMemoryStore
    kernel = RCoreKernel(config)

    # 3. Process
    # Using a random user_id to avoid collision or stick to 1 for persistent memory test
    msg = IncomingMessage(user_id=1, session_id="test_session", text=text)
    
    print(">>> Processing message... (Calling LLM + DB)")
    response = await kernel.process_message(msg)

    # 4. Result
    print(f"\n[Winner]: {response.winning_agent.value} (Score: {response.internal_stats['winner_score']:.2f})")
    print(f"[Reason]: {response.internal_stats['winner_reason']}")
    print(f"[Latency]: {response.internal_stats['latency_ms']}ms")
    print(f"\n>>> FINAL RESPONSE: {response.actions[0].payload['text']}")

async def main():
    # 0. Check ENV
    if not os.getenv("OPENAI_API_KEY"):
        print("WARNING: OPENAI_API_KEY is not set. Agents might fail or error out.")
    
    print(">>> Initializing Database Tables...")
    try:
        await init_models()
        print(">>> DB Tables checked/created.")
    except Exception as e:
        print(f"CRITICAL DB ERROR: {e}")
        print("Did you run 'docker-compose up -d'?")
        return

    text = "Я устал, ненавижу всё это."

    # Case A: Эмпат (Должен победить Social Agent)
    await test_bot(
        "Анна (Психолог)",
        PersonalitySliders(
            empathy_bias=0.9, 
            risk_tolerance=0.1, 
            dominance_level=0.1, 
            pace_setting=0.5, 
            neuroticism=0.2
        ),
        text
    )

    # Case B: Терминатор (Должен победить Prefrontal Agent или Amygdala)
    await test_bot(
        "T-800 (Логик)",
        PersonalitySliders(
            empathy_bias=0.0, # Эмпатия выключена
            risk_tolerance=0.9, 
            dominance_level=0.8, 
            pace_setting=0.2, 
            neuroticism=0.0
        ),
        text
    )
    
    # Case C: Проверка памяти (Intuition)
    # Повторяем тот же текст. Интуиция должна заметить "дежавю", 
    # так как мы сохранили сообщение в Case A и B.
    print(f"\n{'='*20} TESTING MEMORY RECALL {'='*20}")
    await test_bot(
        "Memory Test Bot",
        PersonalitySliders(empathy_bias=0.5, pace_setting=1.0, risk_tolerance=0.5, dominance_level=0.5, neuroticism=0.1),
        text
    )

if __name__ == "__main__":
    asyncio.run(main())
