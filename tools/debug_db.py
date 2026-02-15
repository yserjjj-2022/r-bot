import asyncio
import sys
import os

# Add project root to path to ensure imports work
sys.path.append(os.getcwd())

from sqlalchemy import text, select
from src.r_core.infrastructure.db import AsyncSessionLocal, VolitionalModel, UserProfileModel
from src.r_core.config import settings

async def debug_db():
    print(f"\n🔌 Connecting to DB: {settings.database_url.split('@')[-1]}") # Hide password
    
    async with AsyncSessionLocal() as session:
        print("✅ Connection successful.")
        
        # 1. Check User Profile
        print("\n🔍 Checking User Profiles...")
        result = await session.execute(select(UserProfileModel).limit(1))
        user = result.scalar_one_or_none()
        if user:
            print(f"   Found User ID: {user.user_id}")
            print(f"   Memory Load: {user.short_term_memory_load}")
            print(f"   Last Consolidation: {user.last_consolidation_at}")
        else:
            print("   ❌ No users found!")
            user_id = 1 # Fallback for test

        user_id = user.user_id if user else 1

        # 2. Check Volitional Patterns Schema (specifically 'target')
        print("\n🔍 Checking Volitional Patterns Schema...")
        try:
            # Try to select the specific 'target' column to see if it exists
            await session.execute(text("SELECT target FROM volitional_patterns LIMIT 1"))
            print("   ✅ Column 'target' exists and is readable.")
        except Exception as e:
            print(f"   ❌ Column 'target' ERROR: {e}")
            print("   ⚠️  This confirms the log error! You need to run migration.")
            return

        # 3. Test CRUD (Create, Read, Update, Delete)
        print("\n🛠 Testing CRUD on volitional_patterns...")
        try:
            # INSERT
            print(f"   Attempting INSERT for user_id={user_id}...")
            new_pattern = VolitionalModel(
                user_id=user_id,
                trigger="DEBUG_TRIGGER",
                impulse="DEBUG_IMPULSE",
                target="DEBUG_TARGET",
                intensity=0.99,
                fuel=1.0,
                is_active=True
            )
            session.add(new_pattern)
            await session.flush()
            print(f"   ✅ INSERT success. New ID: {new_pattern.id}")
            
            # READ
            print(f"   Attempting READ...")
            stmt = select(VolitionalModel).where(VolitionalModel.id == new_pattern.id)
            result = await session.execute(stmt)
            loaded_pattern = result.scalar_one()
            print(f"   ✅ READ success. Got pattern: {loaded_pattern.trigger} -> {loaded_pattern.impulse}")

            # UPDATE
            print(f"   Attempting UPDATE...")
            loaded_pattern.intensity = 0.11
            await session.flush()
            print(f"   ✅ UPDATE success.")
            
            # DELETE
            print(f"   Attempting DELETE...")
            await session.delete(loaded_pattern)
            await session.flush()
            print(f"   ✅ DELETE success.")
            
            # Commit (actually, let's rollback to keep DB clean)
            await session.rollback()
            print("\n✨ Test Finished. Transaction rolled back (no garbage left in DB).")
            print("Conclusion: DB is healthy and code can write to it.")
            
        except Exception as e:
            print(f"\n❌ CRUD Failed: {e}")
            print("Conclusion: Code cannot write to DB. Check permissions or constraints.")
            await session.rollback()

if __name__ == "__main__":
    try:
        asyncio.run(debug_db())
    except KeyboardInterrupt:
        pass
    except Exception as e:
        print(f"Fatal error: {e}")