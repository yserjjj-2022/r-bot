#!/usr/bin/env python3
"""
Тестовый скрипт для проверки Affective Theory of Mind.

Проверяем:
1. Извлечение эмоциональных отношений из диалога
2. Сохранение в semantic_memory с sentiment
3. Восстановление affective_context при следующем сообщении
4. Влияние на генерацию ответа

Запуск:
    python tests/test_affective_tom_manual.py
"""

import asyncio
import sys
import os

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from src.r_core.schemas import IncomingMessage, BotConfig, PersonalitySliders
from src.r_core.pipeline import RCoreKernel
from src.r_core.infrastructure.db import init_models
from src.r_core.memory import MemorySystem

async def test_affective_tom():
    print("=" * 60)
    print("🧠 Affective Theory of Mind Test")
    print("=" * 60)
    
    # 1. Init DB
    print("\n[1/5] Initializing database...")
    await init_models()
    print("✅ Database ready")
    
    # 2. Create Kernel
    print("\n[2/5] Creating R-Core Kernel...")
    config = BotConfig(
        character_id="test_user",
        name="R-Bot",
        gender="Neutral",
        sliders=PersonalitySliders(),
        core_values=[]
    )
    kernel = RCoreKernel(config)
    print("✅ Kernel initialized")
    
    # 3. Test Message 1: User expresses hatred
    print("\n[3/5] Sending test message: 'I HATE Java programming language'")
    msg1 = IncomingMessage(
        user_id=999,
        session_id="test_session",
        text="Я ненавижу Java, это ужасный язык программирования"
    )
    
    response1 = await kernel.process_message(msg1)
    stats1 = response1.internal_stats
    
    print(f"\n🤖 Bot Response: {response1.actions[0].payload['text']}")
    print(f"\n📊 Stats:")
    print(f"  - Winner: {response1.winning_agent.value}")
    print(f"  - Affective Triggers Detected: {stats1.get('affective_triggers_detected', 0)}")
    print(f"  - Sentiment Context Used: {stats1.get('sentiment_context_used', False)}")
    
    # 4. Check if sentiment was saved
    print("\n[4/5] Checking semantic memory...")
    memory = MemorySystem()
    sentiment_data = await memory.store.get_sentiment_for_entity(999, "Java")
    
    if sentiment_data:
        print("✅ Sentiment found in memory:")
        print(f"  - Entity: {sentiment_data['entity']}")
        print(f"  - Predicate: {sentiment_data['predicate']}")
        print(f"  - Valence: {sentiment_data['sentiment']['valence']:.2f}")
        print(f"  - Intensity: {sentiment_data['intensity']:.2f}")
    else:
        print("❌ ERROR: Sentiment NOT saved to memory!")
        return
    
    # 5. Test Message 2: Ask about programming language
    print("\n[5/5] Sending follow-up: 'What programming language should I use?'")
    msg2 = IncomingMessage(
        user_id=999,
        session_id="test_session",
        text="Какой язык программирования мне использовать для бэкенда?"
    )
    
    response2 = await kernel.process_message(msg2)
    stats2 = response2.internal_stats
    
    print(f"\n🤖 Bot Response: {response2.actions[0].payload['text']}")
    print(f"\n📊 Stats:")
    print(f"  - Winner: {response2.winning_agent.value}")
    print(f"  - Affective Triggers Detected: {stats2.get('affective_triggers_detected', 0)}")
    print(f"  - Sentiment Context Used: {stats2.get('sentiment_context_used', False)}")
    
    # Check if bot avoided Java
    bot_text = response2.actions[0].payload['text'].lower()
    if "java" in bot_text and stats2.get('sentiment_context_used', False):
        print("\n⚠️ WARNING: Bot mentioned Java despite negative sentiment!")
    elif not "java" in bot_text and stats2.get('sentiment_context_used', False):
        print("\n✅ SUCCESS: Bot avoided mentioning Java (respecting user's preference)")
    elif not stats2.get('sentiment_context_used', False):
        print("\n⚠️ INFO: Sentiment context was NOT used (entity not detected in query)")
    
    print("\n" + "=" * 60)
    print("✅ Test Completed")
    print("=" * 60)

if __name__ == "__main__":
    asyncio.run(test_affective_tom())
