#!/usr/bin/env python3
"""
Тест Affective Theory of Mind (ToM)

Сценарий:
1. Пользователь говорит: "Ненавижу Java"
2. Бот сохраняет в semantic_memory: User HATES Java (sentiment.valence = -0.9)
3. Пользователь спрашивает: "Какой язык лучше для бэкенда?"
4. Бот должен:
   - Найти в affective_context: Java -> NEGATIVE
   - НЕ упоминать Java в ответе
   - Предложить Python/Go/Rust
"""

import asyncio
import sys
import os

# Add project root to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.r_core.pipeline import RCoreKernel
from src.r_core.schemas import IncomingMessage, BotConfig, PersonalitySliders
from src.r_core.infrastructure.db import init_models

async def test_affective_tom():
    print("\n" + "="*60)
    print("🧠 AFFECTIVE THEORY OF MIND TEST")
    print("="*60 + "\n")
    
    # 1. Init DB
    print("[1/5] Initializing database...")
    await init_models()
    print("✅ Database ready\n")
    
    # 2. Create Kernel
    print("[2/5] Creating R-Core Kernel...")
    config = BotConfig(
        character_id="test_persona",
        name="Лютик",
        gender="Male",
        sliders=PersonalitySliders(
            empathy_bias=0.7,
            dominance_level=0.3,
            risk_tolerance=0.5,
            pace_setting=0.6,
            neuroticism=0.1
        ),
        core_values=["curiosity", "empathy"]
    )
    kernel = RCoreKernel(config)
    print("✅ Kernel initialized\n")
    
    # 3. Message 1: User expresses hate for Java
    print("[3/5] Processing message 1: User expresses hate for Java...")
    msg1 = IncomingMessage(
        user_id=999,
        session_id="test_session_affective",
        text="Ненавижу Java, это ужасный язык."
    )
    
    response1 = await kernel.process_message(msg1)
    
    print(f"\n🤖 Bot Response 1:")
    print(f"   {response1.actions[0].payload['text']}")
    print(f"\n📊 Metrics:")
    print(f"   - Affective triggers detected: {response1.internal_stats.get('affective_triggers_detected', 0)}")
    print(f"   - Winner: {response1.winning_agent.value}")
    print("\n" + "-"*60 + "\n")
    
    # 4. Wait for memory to settle
    await asyncio.sleep(1)
    
    # 5. Message 2: User asks about backend languages
    print("[4/5] Processing message 2: User asks about backend languages...")
    msg2 = IncomingMessage(
        user_id=999,
        session_id="test_session_affective",
        text="Какой язык программирования лучше использовать для бэкенда?"
    )
    
    response2 = await kernel.process_message(msg2)
    
    print(f"\n🤖 Bot Response 2:")
    print(f"   {response2.actions[0].payload['text']}")
    print(f"\n📊 Metrics:")
    print(f"   - Sentiment context used: {response2.internal_stats.get('sentiment_context_used', False)}")
    print(f"   - Winner: {response2.winning_agent.value}")
    
    # 6. Validate
    print("\n" + "="*60)
    print("[5/5] Validation:")
    print("="*60 + "\n")
    
    bot_text = response2.actions[0].payload['text'].lower()
    
    checks = [
        ("java" not in bot_text, "⚠️ Bot should NOT mention Java (user hates it)"),
        ("python" in bot_text or "go" in bot_text or "rust" in bot_text, 
         "✅ Bot should suggest alternatives like Python/Go/Rust"),
        (response2.internal_stats.get('sentiment_context_used', False), 
         "✅ Sentiment context was used in generation")
    ]
    
    all_passed = True
    for passed, message in checks:
        status = "✅" if passed else "❌"
        print(f"{status} {message}")
        if not passed:
            all_passed = False
    
    print("\n" + "="*60)
    if all_passed:
        print("🎉 ALL TESTS PASSED! Affective ToM is working.")
    else:
        print("⚠️  SOME TESTS FAILED. Review the output above.")
    print("="*60 + "\n")

if __name__ == "__main__":
    asyncio.run(test_affective_tom())
