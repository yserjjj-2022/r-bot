import sys
import os
import asyncio
from unittest.mock import AsyncMock, MagicMock
from datetime import datetime

# Add project root to sys.path to allow running from tests/ dir
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

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
    
    # 2. Mock Data
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
        
    # 3. Test private method _llm_extract_volitional_intent directly
    # Note: We are testing the logic of extraction and parsing, not the DB save part here
    patterns = await hippo._llm_extract_volitional_intent(messages)
    
    print("\n✅ Result Patterns:")
    for p in patterns:
        print(p)
        
    # 4. Assertions
    assert len(patterns) == 1
    assert patterns[0]['target'] == "Spanish"
    assert patterns[0]['impulse'] == "laziness"
    print("\n🎉 Test Passed!")

if __name__ == "__main__":
    asyncio.run(run_test())
