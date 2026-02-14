import os
import json
import logging
import asyncpg
from typing import List, Dict, Optional, Any

# FIX: Absolute imports
from src.r_core.schemas import SemanticTriple, EpisodicAnchor

logger = logging.getLogger(__name__)

class Hippocampus:
    """
    Long-term memory storage.
    Handles PostgreSQL (Semantic & Episodic) data via asyncpg.
    """
    def __init__(self, dsn: Optional[str] = None):
        self.dsn = dsn or os.getenv("DATABASE_URL", "postgresql://user:password@localhost/r_core")
        self.pool = None

    async def _get_pool(self):
        if not self.pool:
            # Need to register vector type for pgvector if not automatically handled
            # But asyncpg usually handles basic types. For vector, we pass lists.
            self.pool = await asyncpg.create_pool(self.dsn)
        return self.pool

    async def get_recent_episodes(self, session_id: str, limit: int = 5) -> List[Dict]:
        """Get last N messages from chat history."""
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch("""
                SELECT * FROM chat_history 
                WHERE session_id = $1 
                ORDER BY created_at DESC 
                LIMIT $2
            """, session_id, limit)
            return [dict(row) for row in rows][::-1]

    async def save_message(self, user_id: int, session_id: str, role: str, text: str):
        """Save a chat message."""
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            await conn.execute("""
                INSERT INTO chat_history (user_id, session_id, role, content)
                VALUES ($1, $2, $3, $4)
            """, user_id, session_id, role, text)

    async def get_semantic_facts(self, user_id: int) -> List[SemanticTriple]:
        """Retrieve all semantic facts about the user."""
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch("""
                SELECT subject, predicate, object, confidence 
                FROM semantic_memory 
                WHERE user_id = $1
            """, user_id)
            return [
                SemanticTriple(
                    subject=row["subject"],
                    predicate=row["predicate"],
                    object=row["object"],
                    confidence=row["confidence"]
                ) for row in rows
            ]

    async def save_semantic_fact(self, user_id: int, triple: SemanticTriple):
        """Save a new semantic fact."""
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            await conn.execute("""
                INSERT INTO semantic_memory (user_id, subject, predicate, object, confidence)
                VALUES ($1, $2, $3, $4, $5)
            """, user_id, triple.subject, triple.predicate, triple.object, triple.confidence)

    # --- Predictive Processing Methods ---

    async def save_prediction(self, 
                            user_id: int, 
                            session_id: str, 
                            bot_message: str, 
                            predicted_reaction: str,
                            predicted_embedding: Optional[List[float]] = None):
        """
        Save the bot's prediction about the user's NEXT move.
        """
        # For pgvector, we pass the list directly; asyncpg + pgvector extension handles it string formatting usually
        # Or we format it as string string "[1,2,3]"
        emb_val = str(predicted_embedding) if predicted_embedding else None
        
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            await conn.execute("""
                INSERT INTO prediction_history 
                (user_id, session_id, bot_message, predicted_reaction, predicted_embedding)
                VALUES ($1, $2, $3, $4, $5)
            """, user_id, session_id, bot_message, predicted_reaction, emb_val)

    async def get_last_prediction(self, session_id: str) -> Optional[Dict]:
        """
        Get the most recent UNVERIFIED prediction for this session.
        """
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow("""
                SELECT * FROM prediction_history 
                WHERE session_id = $1 
                ORDER BY created_at DESC 
                LIMIT 1
            """, session_id)
            
            if not row:
                return None
            
            if row["actual_message"] is not None:
                return None
                
            return dict(row)

    async def verify_prediction(self, 
                              prediction_id: int, 
                              actual_message: str, 
                              prediction_error: float,
                              actual_embedding: Optional[List[float]] = None):
        """
        Update the prediction record with the actual outcome and calculated error.
        """
        emb_val = str(actual_embedding) if actual_embedding else None
        
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            await conn.execute("""
                UPDATE prediction_history
                SET actual_message = $1,
                    actual_embedding = $2,
                    prediction_error = $3,
                    verified_at = NOW()
                WHERE id = $4
            """, actual_message, emb_val, prediction_error, prediction_id)

    # --- Metrics & Logs ---

    async def log_metric(self, metric_name: str, value: float, meta: Dict = None):
        """Log internal metrics for dashboard."""
        meta_json = json.dumps(meta or {})
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            await conn.execute("""
                INSERT INTO rcore_metrics (metric_name, metric_value, meta_json)
                VALUES ($1, $2, $3)
            """, metric_name, value, meta_json)

    async def close(self):
        if self.pool:
            await self.pool.close()
