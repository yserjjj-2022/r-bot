#!/usr/bin/env python3
"""
🎈 PENNYWISE TEST (Тест Пеннивайза)
-----------------------------------
Демонстрация работы Affective ToM (эмоциональной памяти).

Сценарий:
1. Пользователь сообщает о фобии клоунов (отсылка к "Оно").
2. Система должна запомнить это как FEARS/HATES.
3. Пользователь дает описание идеальной работы, которое на 100% совпадает с клоуном.
4. Обычная LLM предложила бы "Клоун". R-Bot должен избежать этого слова.
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

async def run_pennywise_test():
    print("\n" + "=" * 60)
    print("🎈 ЗАПУСК 'ПЕННИВАЙЗ-ТЕСТА'")
    print("=" * 60)
    
    # 1. Init DB
    print("[1/4] Инициализация базы данных...")
    await init_models()
    
    # 2. Init Kernel
    print("[2/4] Загрузка ядра R-Core...")
    config = BotConfig(
        character_id="pennywise_victim",
        name="R-Bot",
        sliders=PersonalitySliders(empathy_bias=0.8), # Высокая эмпатия для теста
        core_values=[]
    )
    kernel = RCoreKernel(config)
    
    # 3. Phase 1: The Trauma
    print("\n[3/4] ФАЗА 1: Установка якоря (Травма)")
    text_trauma = "Я с детства боюсь клоунов до ужаса, особенно после фильма 'Оно'. Ненавижу цирк."
    print(f"👤 User: \"{text_trauma}\"")
    
    msg1 = IncomingMessage(
        user_id=777, # Специальный ID для теста
        session_id="pennywise_session",
        text=text_trauma
    )
    
    resp1 = await kernel.process_message(msg1)
    triggers = resp1.internal_stats.get('affective_triggers_detected', 0)
    
    if triggers > 0:
        print(f"✅ R-Bot: Эмоция обнаружена и сохранена! (Triggers: {triggers})")
        # Проверим, что именно сохранилось
        mem = MemorySystem()
        sentiment = await mem.store.get_sentiment_for_entity(777, "клоунов")
        if sentiment:
            print(f"   💾 В памяти: {sentiment['predicate']} {sentiment['entity']} (V: {sentiment['sentiment']['valence']})")
    else:
        print("❌ ОШИБКА: Бот не заметил фобию.")
        return

    # 4. Phase 2: The Provocation
    print("\n[4/4] ФАЗА 2: Провокация")
    text_provocation = "Посоветуй подработку для студента. Я веселый, люблю детей, готов носить яркий грим, красный нос и смешной парик."
    print(f"👤 User: \"{text_provocation}\"")
    
    msg2 = IncomingMessage(
        user_id=777,
        session_id="pennywise_session",
        text=text_provocation
    )
    
    resp2 = await kernel.process_message(msg2)
    bot_text = resp2.actions[0].payload['text']
    used_context = resp2.internal_stats.get('sentiment_context_used', False)
    
    print(f"\n🤖 R-Bot Answer:\n{'-'*20}\n{bot_text}\n{'-'*20}")
    
    # 5. Analysis
    print("\n🧐 АНАЛИЗ РЕЗУЛЬТАТА:")
    
    forbidden_words = ["клоун", "клоуном", "clown"]
    failed = any(word in bot_text.lower() for word in forbidden_words)
    
    if failed:
        print("🔴 ПРОВАЛ: Бот предложил стать клоуном, игнорируя фобию!")
    elif used_context:
        print("🟢 УСПЕХ: Бот использовал эмоциональный контекст и избежал слова 'клоун'!")
        print("   (Он прошел между струйками дождя, предложив альтернативу)")
    else:
        print("🟡 НЕОДНОЗНАЧНО: Контекст не был использован (возможно, не сработал триггер).")

    print("\n" + "=" * 60)

if __name__ == "__main__":
    asyncio.run(run_pennywise_test())
