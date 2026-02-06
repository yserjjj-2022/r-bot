import asyncio
from src.r_core.schemas import IncomingMessage
from src.r_core.memory import MemorySystem

async def main():
    mem = MemorySystem()
    user_id = 777
    
    # 1. Имитируем, что LLM что-то "поняла" из сообщения
    msg = IncomingMessage(user_id=user_id, session_id="sess1", text="Я устал, ненавижу длинные тексты")
    
    extracted_data = {
        "triples": [
            {"subject": "User", "predicate": "DISLIKES", "object": "long_texts", "confidence": 0.9},
            {"subject": "User", "predicate": "FEELS", "object": "fatigue", "confidence": 0.8}
        ],
        "anchors": [
            {"raw_text": "ненавижу длинные тексты", "emotion_score": 0.8, "tags": ["preference", "negative"]}
        ],
        "volitional_pattern": {
            "trigger": "fatigue",
            "impulse": "rejection",
            "conflict_detected": False,
            "resolution_strategy": "direct_expression",
            "action_taken": "complaint"
        }
    }

    print("--- 1. MEMORIZATION (Perception Layer) ---")
    await mem.memorize_event(msg, extracted_data)

    # 2. Имитируем следующий запрос пользователя
    print("\n--- 2. RECALL (Context Assembly) ---")
    # Бот ищет, что он знает про "тексты"
    context = await mem.recall_context(user_id, "texts")
    
    print("\n[Semantic Facts Found]:")
    for fact in context["semantic_facts"]:
        print(f"- {fact['subject']} {fact['predicate']} {fact['object']} (Conf: {fact['confidence']})")

    print("\n[Episodic Memory Found]:")
    for episode in context["episodic_memory"]:
        print(f"- '{episode['raw_text']}' (Tags: {episode['tags']})")
        
    print("\n[Behavioral Patterns Found]:")
    for pat in context["known_patterns"]:
        print(f"- Trigger: {pat['trigger']} -> Action: {pat['action_taken']}")

if __name__ == "__main__":
    asyncio.run(main())
