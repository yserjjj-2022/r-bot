import asyncio
from unittest.mock import AsyncMock, MagicMock
from datetime import datetime
from src.r_core.hippocampus import Hippocampus
from src.r_core.infrastructure.db import ChatHistoryModel, VolitionalModel

# --- Mocks ---

class MockLLM:
    async def complete(self, prompt: str) -> str:
        print(f"\n[MockLLM] Prompt received:\n{prompt[:100]}...\n")
        # Simulate extraction for "I want to learn Spanish but I'm lazy"
        return """
        [
          {
            "trigger": "discussion about learning",
            "impulse": "laziness",
            "target": "Spanish",
            "resolution_strategy": "promise to try later",
            "intensity": 0.6,
            "fuel": 0.4
          }
        ]
        """

class MockEmbedder:
    async def embed(self, text: str):
        return [0.1, 0.2, 0.3]

# --- Test Runner ---

async def run_test():
    print("🚀 Starting Semantic Intent Analysis Test (Mocked)...")
    
    # 1. Setup
    llm = MockLLM()
    embedder = MockEmbedder()
    hippo = Hippocampus(llm_client=llm, embedding_client=embedder)
    
    # 2. Mock DB Session and Data
    # We need to monkeypatch the AsyncSessionLocal used inside Hippocampus
    # OR we can just test the internal logic if we refactor, but here we'll mock the db call context.
    
    # Since we can't easily mock the internal AsyncSessionLocal context manager without 
    # complex patching, we will assume the user runs this in an env where DB is accessible
    # OR we demonstrate the logic by extracting the LLM part which is the core change.
    
    # Let's test the LLM extraction part specifically, which is isolated.
    
    messages = [
        ChatHistoryModel(role="user", content="Привет"),
        ChatHistoryModel(role="assistant", content="Привет!"),
        ChatHistoryModel(role="user", content="Хочу выучить испанский, но мне так лень..."),
        ChatHistoryModel(role="assistant", content="Может начнешь с малого?"),
        ChatHistoryModel(role="user", content="Ну ладно, попробую завтра 5 минут.")
    ]
    
    print("\n📝 Analysing Dialogue:")
    for m in messages:
        print(f" - {m.role}: {m.content}")
        
    # Test private method _llm_extract_volitional_intent directly
    patterns = await hippo._llm_extract_volitional_intent(messages)
    
    print("\n✅ Result Patterns:")
    for p in patterns:
        print(p)
        
    assert len(patterns) == 1
    assert patterns[0]['target'] == "Spanish"
    assert patterns[0]['impulse'] == "laziness"
    print("\n🎉 Test Passed!")

if __name__ == "__main__":
    asyncio.run(run_test())
