import aiosqlite
import json
import logging
from typing import List, Dict, Optional, Any
from datetime import datetime

# FIX: Absolute imports
from src.r_core.schemas import SemanticTriple, EpisodicAnchor
from src.r_core.infrastructure.vector_db import VectorDB  # Assuming this exists or mocked

logger = logging.getLogger(__name__)

class Hippocampus:
    """
    Long-term memory storage.
    Handles SQL (Semantic) and Vector (Episodic) data.
    """
    def __init__(self, db_path: str = "r_core.db"):
        self.db_path = db_path
        # self.vector_db = VectorDB() # Initialize when needed

    async def get_recent_episodes(self, session_id: str, limit: int = 5) -> List[Dict]:
        """Get last N messages from chat history."""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute("""
                SELECT * FROM chat_history 
                WHERE session_id = ? 
                ORDER BY created_at DESC 
                LIMIT ?
            """, (session_id, limit))
            rows = await cursor.fetchall()
            return [dict(row) for row in rows][::-1]  # Return in chronological order

    async def save_message(self, user_id: int, session_id: str, role: str, text: str):
        """Save a chat message."""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("""
                INSERT INTO chat_history (user_id, session_id, role, content)
                VALUES (?, ?, ?, ?)
            """, (user_id, session_id, role, text))
            await db.commit()

    async def get_semantic_facts(self, user_id: int) -> List[SemanticTriple]:
        """Retrieve all semantic facts about the user."""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute("""
                SELECT subject, predicate, object, confidence 
                FROM semantic_memory 
                WHERE user_id = ?
            """, (user_id,))
            rows = await cursor.fetchall()
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
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("""
                INSERT INTO semantic_memory (user_id, subject, predicate, object, confidence)
                VALUES (?, ?, ?, ?, ?)
            """, (user_id, triple.subject, triple.predicate, triple.object, triple.confidence))
            await db.commit()

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
        emb_json = json.dumps(predicted_embedding) if predicted_embedding else None
        
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("""
                INSERT INTO prediction_history 
                (user_id, session_id, bot_message, predicted_reaction, predicted_embedding_json)
                VALUES (?, ?, ?, ?, ?)
            """, (user_id, session_id, bot_message, predicted_reaction, emb_json))
            await db.commit()

    async def get_last_prediction(self, session_id: str) -> Optional[Dict]:
        """
        Get the most recent UNVERIFIED prediction for this session.
        """
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            # Get the very last prediction record
            cursor = await db.execute("""
                SELECT * FROM prediction_history 
                WHERE session_id = ? 
                ORDER BY created_at DESC 
                LIMIT 1
            """, (session_id,))
            row = await cursor.fetchone()
            
            if not row:
                return None
            
            # If it's already verified (has actual_message), then we have no "pending" prediction
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
        emb_json = json.dumps(actual_embedding) if actual_embedding else None
        
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("""
                UPDATE prediction_history
                SET actual_message = ?,
                    actual_embedding_json = ?,
                    prediction_error = ?,
                    verified_at = CURRENT_TIMESTAMP
                WHERE id = ?
            """, (actual_message, emb_json, prediction_error, prediction_id))
            await db.commit()

    # --- Metrics & Logs ---

    async def log_metric(self, metric_name: str, value: float, meta: Dict = None):
        """Log internal metrics for dashboard."""
        meta_json = json.dumps(meta or {})
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("""
                INSERT INTO rcore_metrics (metric_name, metric_value, meta_json)
                VALUES (?, ?, ?)
            """, (metric_name, value, meta_json))
            await db.commit()

