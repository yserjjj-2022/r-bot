import asyncio
from sqlalchemy import text
from app.modules.database import engine, init_db
from app.modules.database.session import AsyncSessionLocal


async def run_topic_transitions_migration():
    """Создаёт таблицу topic_transitions для Bifurcation Engine"""
    async with engine.begin() as conn:
        try:
            await conn.execute(text("""
                CREATE TABLE IF NOT EXISTS topic_transitions (
                    id SERIAL PRIMARY KEY,
                    user_id INTEGER NOT NULL,
                    source_embedding vector(1536),
                    target_embedding vector(1536),
                    transition_type VARCHAR(50) NOT NULL,
                    agent_intent VARCHAR(100),
                    success_weight FLOAT DEFAULT 0.5,
                    attempts INTEGER DEFAULT 1,
                    last_used_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """))
            await conn.execute(text(
                "CREATE INDEX IF NOT EXISTS idx_topic_transitions_user_id ON topic_transitions (user_id)"
            ))
            print("[Migration] ✅ topic_transitions table created")
        except Exception as e:
            print(f"[Migration] topic_transitions: {e}")


if __name__ == "__main__":
    # Создаём базовые таблицы (SQLAlchemy models)
    init_db()
    print("База данных инициализирована.")
    
    # Запускаем дополнительные миграции
    asyncio.run(run_topic_transitions_migration())
    print("Миграции выполнены.")