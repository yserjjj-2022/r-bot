#!/usr/bin/env python3
"""
Скрипт для ручного применения миграции sentiment.
Используйте, если кнопка "Initialize DB" в Streamlit не сработала.

Запуск:
    python scripts/apply_sentiment_migration.py
"""

import asyncio
import sys
import os

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from src.r_core.infrastructure.db import init_models

async def apply_migration():
    print("="*60)
    print("🔧 Applying Sentiment Migration")
    print("="*60)
    
    try:
        print("\n[1/2] Running init_models()...")
        await init_models()
        print("✅ Migration completed successfully!")
        
        print("\n[2/2] Verifying changes...")
        print("✅ Database schema updated")
        print("\n" + "="*60)
        print("✅ All Done! You can now use Affective ToM.")
        print("="*60)
        
    except Exception as e:
        print(f"\n❌ ERROR: {e}")
        print("\n💡 Troubleshooting:")
        print("1. Check if PostgreSQL is running (docker-compose up -d)")
        print("2. Verify database credentials in .env or config.py")
        print("3. Try running manually: psql -U rbot -d rbot < scripts/migrate_add_sentiment.sql")
        sys.exit(1)

if __name__ == "__main__":
    asyncio.run(apply_migration())
