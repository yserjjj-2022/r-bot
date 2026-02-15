import asyncio
import sys
import os
from datetime import datetime
from unittest.mock import MagicMock

# Add project root
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from sqlalchemy import text, select
from src.r_core.infrastructure.db import AsyncSessionLocal, UserProfileModel, ChatHistoryModel, VolitionalModel, init_models
from src.r_core.hippocampus import Hippocampus

# --- Mock LLM for DB Test ---
class MockLLM:
    async def complete(self, prompt: str) -> str:
        # Эмулируем ответ LLM: Пользователь снова хочет учить испанский, но уже с новой стратегией
        return """
        [
          {
            "trigger": "evening reflection",
            "impulse": "tiredness",
            "target": "Spanish",
            "resolution_strategy": "use duolingo",
            "intensity": 0.8,
            "fuel": 0.9
          }
        ]
        """

class MockEmbedder:
    async def embed(self, text: str):
        return [0.1] * 1536  # Fake vector

async def run_db_test():
    print("🚀 Starting DB Integration Test for Volitional Logic...")
    
    # 1. Init DB Schema (in case it's clean)
    print("... Initializing DB schema")
    await init_models()
    
    user_id = 99999  # Test User ID
    
    async with AsyncSessionLocal() as session:
        # 2. Cleanup old test data
        await session.execute(text("DELETE FROM volitional_patterns WHERE user_id = :uid"), {"uid": user_id})
        await session.execute(text("DELETE FROM chat_history WHERE user_id = :uid"), {"uid": user_id})
        await session.execute(text("DELETE FROM user_profiles WHERE user_id = :uid"), {"uid": user_id})
        await session.commit()

        # 3. Create Test User
        user = UserProfileModel(user_id=user_id, name="TestSubject")
        session.add(user)
        
        # 4. Create EXISTING Pattern (Old state)
        # Target = "Spanish", Fuel = 0.5, Strategy = "promise"
        old_pattern = VolitionalModel(
            user_id=user_id,
            trigger="morning",
            impulse="laziness",
            target="Spanish",
            goal="learning",
            resolution_strategy="promise",
            intensity=0.5,
            fuel=0.5,
            learned_delta=0.1,
            is_active=True
        )
        session.add(old_pattern)
        
        # 5. Create Chat History (Context for Hippocampus)
        # 5 сообщений, чтобы Hippocampus не скипнул работу
        msgs = [
            ChatHistoryModel(user_id=user_id, session_id="test_sess", role="user", content="Msg 1"),
            ChatHistoryModel(user_id=user_id, session_id="test_sess", role="assistant", content="Msg 2"),
            ChatHistoryModel(user_id=user_id, session_id="test_sess", role="user", content="Msg 3"),
            ChatHistoryModel(user_id=user_id, session_id="test_sess", role="assistant", content="Msg 4"),
            ChatHistoryModel(user_id=user_id, session_id="test_sess", role="user", content="Msg 5")
        ]
        session.add_all(msgs)
        await session.commit()
        print("✅ Test data prepared: User created, Old Pattern 'Spanish' (Fuel=0.5) inserted.")

    # 6. Run Hippocampus
    print("... Running Hippocampus Consolidation")
    hippo = Hippocampus(llm_client=MockLLM(), embedding_client=MockEmbedder())
    
    # Run ONLY the volitional update part directly to isolate the test
    result = await hippo._update_volitional_patterns(user_id)
    print(f"Hippocampus Result: {result}")

    # 7. Verify Results in DB
    async with AsyncSessionLocal() as session:
        pattern = (await session.execute(
            select(VolitionalModel).where(VolitionalModel.user_id == user_id)
        )).scalar_one()
        
        print("\n🧐 Verification:")
        print(f"Target: {pattern.target} (Expected: Spanish)")
        print(f"Strategy: {pattern.resolution_strategy} (Expected: 'promise, use duolingo')")
        print(f"Fuel: {pattern.fuel:.2f} (Expected: ~0.62)")
        print(f"Intensity: {pattern.intensity} (Expected: 0.8)")
        
        # Logic Check:
        # Old Fuel = 0.5, New Fuel (from MockLLM) = 0.9
        # Formula: 0.7 * 0.5 + 0.3 * 0.9 = 0.35 + 0.27 = 0.62
        assert abs(pattern.fuel - 0.62) < 0.01, f"Fuel math failed! Got {pattern.fuel}"
        
        # Strategy Check:
        assert "duolingo" in pattern.resolution_strategy, "New strategy not merged!"
        assert "promise" in pattern.resolution_strategy, "Old strategy lost!"
        
        print("\n🎉 DB Integration Test Passed! Logic is solid.")

if __name__ == "__main__":
    asyncio.run(run_db_test())
