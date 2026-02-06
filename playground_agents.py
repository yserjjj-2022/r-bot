import asyncio
# Добавьте EpisodicAnchor в импорты
from src.r_core.schemas import IncomingMessage, PersonalitySliders, EpisodicAnchor 
from src.r_core.memory import MemorySystem
from src.r_core.agents import (
    MockLLMClient,
    IntuitionAgent,
    AmygdalaAgent,
    PrefrontalAgent,
    SocialAgent,
    StriatumAgent
)

async def run_parliament():
    # 1. Setup
    llm = MockLLMClient()
    mem = MemorySystem()
    
    # Создаем наших агентов
    agents = [
        IntuitionAgent(llm),
        AmygdalaAgent(llm),
        PrefrontalAgent(llm),
        SocialAgent(llm),
        StriatumAgent(llm)
    ]

    # 2. Настройка Личности: "Эмпатичный Психолог"
    sliders = PersonalitySliders(
        empathy_bias=0.9,     # Очень сочувствующий
        dominance_level=0.2,  # Мягкий
        risk_tolerance=0.1,   # Осторожный
        pace_setting=0.5,
        neuroticism=0.3
    )
    print(f"--- BOT PERSONALITY: Empathy={sliders.empathy_bias}, Risk={sliders.risk_tolerance} ---")

    # 3. Входящее сообщение (Триггер)
    user_id = 777
    text = "Я устал, ненавижу длинные тексты!"
    msg = IncomingMessage(user_id=user_id, session_id="s1", text=text)
    
    # (Предварительно наполним память ПРАВИЛЬНЫМ объектом)
    anchor = EpisodicAnchor(
        raw_text=text, 
        tags=['hate'], 
        emotion_score=0.9, # Обязательное поле
        embedding_ref="mock_vec"
    )
    await mem.store.save_episodic(user_id, anchor)
    
    # 4. Сбор контекста (Retrieval)
    context = await mem.recall_context(user_id, "тексты")

    # 5. ГОЛОСОВАНИЕ (Parallel Execution)
    print(f"\n--- INCOMING: '{text}' ---\n")
    
    tasks = [agent.process(msg, context, sliders) for agent in agents]
    signals = await asyncio.gather(*tasks)

    # 6. Вывод результатов (Debate)
    print("--- PARLIAMENT DEBATE RESULTS ---")
    
    # Сортируем по силе сигнала
    signals.sort(key=lambda s: s.score, reverse=True)
    
    for s in signals:
        bar_len = int(s.score * 2)
        bar = "█" * bar_len
        print(f"[{s.agent_name.value:<18}] Score: {s.score:.2f} | {bar}")
        print(f"   Reason: {s.rationale_short}")
        print("-" * 50)

    winner = signals[0]
    print(f"\n🏆 WINNER: {winner.agent_name.value} (Score: {winner.score:.2f})")
    print(f"   Deciding factor: {winner.rationale_short}")

if __name__ == "__main__":
    asyncio.run(run_parliament())
