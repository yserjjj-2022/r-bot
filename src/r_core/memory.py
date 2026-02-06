import uuid
from typing import List, Optional, Dict
from datetime import datetime
import math
from pydantic import BaseModel
from sqlalchemy import select

# Импортируем наши контракты
from .schemas import (
    SemanticTriple, 
    EpisodicAnchor, 
    VolitionalPattern,
    IncomingMessage
)

# Импортируем инфраструктуру (FIXED absolute imports)
from src.r_core.infrastructure.db import (
    AsyncSessionLocal, 
    SemanticModel, 
    EpisodicModel, 
    VolitionalModel
)
from src.r_core.infrastructure.llm import LLMService

# --- Interfaces (Abstractions) ---\n
class VectorStoreParams(BaseModel):
    """Параметры для поиска в памяти"""
    limit: int = 5
    min_similarity: float = 0.7

class AbstractMemoryStore:
    """
    Интерфейс для хранилища памяти. 
    """
    async def save_semantic(self, user_id: int, triple: SemanticTriple):
        raise NotImplementedError
    
    async def save_episodic(self, user_id: int, anchor: EpisodicAnchor, embedding: Optional[List[float]] = None):
        raise NotImplementedError
        
    async def save_pattern(self, user_id: int, pattern: VolitionalPattern):
        raise NotImplementedError

    async def search_episodic(self, user_id: int, query_vector: List[float], params: VectorStoreParams) -> List[EpisodicAnchor]:
        raise NotImplementedError
        
    async def search_semantic(self, user_id: int, query_text: str) -> List[SemanticTriple]:
        raise NotImplementedError
        
    async def get_volitional_patterns(self, user_id: int) -> List[VolitionalPattern]:
        raise NotImplementedError

# --- Postgres Implementation ---

class PostgresMemoryStore(AbstractMemoryStore):
    """
    Реализация памяти на базе PostgreSQL + pgvector
    """
    async def save_semantic(self, user_id: int, triple: SemanticTriple):
        async with AsyncSessionLocal() as session:
            # Check overlap (Upsert logic simplified)
            stmt = select(SemanticModel).where(
                SemanticModel.user_id == user_id,
                SemanticModel.subject == triple.subject,
                SemanticModel.predicate == triple.predicate,
                SemanticModel.object == triple.object
            )
            result = await session.execute(stmt)
            existing = result.scalar_one_or_none()
            
            if existing:
                existing.confidence = max(existing.confidence, triple.confidence)
                # existing.source_message_id = triple.source_message_id # Maybe update source?
            else:
                new_triple = SemanticModel(
                    user_id=user_id,
                    subject=triple.subject,
                    predicate=triple.predicate,
                    object=triple.object,
                    confidence=triple.confidence,
                    source_message_id=triple.source_message_id
                )
                session.add(new_triple)
            await session.commit()
            
    async def save_episodic(self, user_id: int, anchor: EpisodicAnchor, embedding: Optional[List[float]] = None):
        if not embedding:
            print("[Memory] Warning: Saving episodic memory without embedding. Search will fail.")
            embedding = [0.0] * 1536 # Placeholder
            
        async with AsyncSessionLocal() as session:
            entry = EpisodicModel(
                user_id=user_id,
                raw_text=anchor.raw_text,
                embedding=embedding,
                emotion_score=anchor.emotion_score,
                tags=anchor.tags,
                ttl_days=anchor.ttl_days
            )
            session.add(entry)
            await session.commit()

    async def save_pattern(self, user_id: int, pattern: VolitionalPattern):
        async with AsyncSessionLocal() as session:
            entry = VolitionalModel(
                user_id=user_id,
                trigger=pattern.trigger,
                impulse=pattern.impulse,
                goal=pattern.goal,
                conflict_detected=pattern.conflict_detected,
                resolution_strategy=pattern.resolution_strategy,
                action_taken=pattern.action_taken
            )
            session.add(entry)
            await session.commit()

    async def search_episodic(self, user_id: int, query_vector: List[float], params: VectorStoreParams) -> List[EpisodicAnchor]:
        async with AsyncSessionLocal() as session:
            # pgvector search: L2 distance or Cosine distance
            # <=> is cosine distance operator
            stmt = select(EpisodicModel).where(EpisodicModel.user_id == user_id)
            stmt = stmt.order_by(EpisodicModel.embedding.cosine_distance(query_vector))
            stmt = stmt.limit(params.limit)
            
            result = await session.execute(stmt)
            rows = result.scalars().all()
            
            return [
                EpisodicAnchor(
                    raw_text=r.raw_text,
                    emotion_score=r.emotion_score,
                    tags=r.tags,
                    ttl_days=r.ttl_days,
                    embedding_ref="pg_vector_stored" 
                ) for r in rows
            ]

    async def search_semantic(self, user_id: int, query_text: str) -> List[SemanticTriple]:
        # Full text search is better, but simple ILIKE for now
        async with AsyncSessionLocal() as session:
            stmt = select(SemanticModel).where(
                SemanticModel.user_id == user_id,
                (SemanticModel.object.ilike(f"%{query_text}%")) | 
                (SemanticModel.predicate.ilike(f"%{query_text}%"))
            )
            result = await session.execute(stmt)
            rows = result.scalars().all()
            
            return [
                SemanticTriple(
                    subject=r.subject,
                    predicate=r.predicate,
                    object=r.object,
                    confidence=r.confidence,
                    source_message_id=r.source_message_id
                ) for r in rows
            ]

    async def get_volitional_patterns(self, user_id: int) -> List[VolitionalPattern]:
        async with AsyncSessionLocal() as session:
            stmt = select(VolitionalModel).where(VolitionalModel.user_id == user_id)
            result = await session.execute(stmt)
            rows = result.scalars().all()
            return [
                VolitionalPattern(
                    trigger=r.trigger,
                    impulse=r.impulse,
                    goal=r.goal,
                    conflict_detected=r.conflict_detected,
                    resolution_strategy=r.resolution_strategy,
                    action_taken=r.action_taken
                ) for r in rows
            ]

# --- Service Layer ---\n
class MemorySystem:
    """
    Главная точка входа для работы с памятью в R-Core.
    """
    def __init__(self, store: Optional[AbstractMemoryStore] = None):
        self.store = store or PostgresMemoryStore() # Default to Real DB now
        self.llm_service = LLMService()

    async def memorize_event(self, message: IncomingMessage, extraction_result: dict):
        """
        Сохраняет результаты работы Perception Layer (извлеченные факты, цитаты, паттерны)
        """
        user_id = message.user_id

        # 1. Сохраняем семантику (Факты)
        for triple_data in extraction_result.get("triples", []):
            triple = SemanticTriple(**triple_data, source_message_id=message.message_id)
            await self.store.save_semantic(user_id, triple)

        # 2. Сохраняем эпизоды (Цитаты)
        for anchor_data in extraction_result.get("anchors", []):
            anchor = EpisodicAnchor(**anchor_data)
            # Generate Embedding using LLM Service
            try:
                embedding = await self.llm_service.get_embedding(anchor.raw_text)
                await self.store.save_episodic(user_id, anchor, embedding=embedding)
            except Exception as e:
                print(f"[MemorySystem] Embedding failed for {anchor.raw_text[:20]}...: {e}")

        # 3. Сохраняем волевые паттерны
        if "volitional_pattern" in extraction_result and extraction_result["volitional_pattern"]:
            pattern = VolitionalPattern(**extraction_result["volitional_pattern"])
            await self.store.save_pattern(user_id, pattern)

    async def recall_context(self, user_id: int, current_text: str) -> dict:
        """
        Собирает контекст для LLM (Retrieval)
        """
        # 1. Ищем похожие эпизоды (RAG)
        try:
            query_vec = await self.llm_service.get_embedding(current_text)
            episodic = await self.store.search_episodic(user_id, query_vec, VectorStoreParams(limit=3))
        except Exception as e:
            print(f"[MemorySystem] Recall Embedding failed: {e}")
            episodic = []
        
        # 2. Ищем релевантные факты
        semantic = await self.store.search_semantic(user_id, current_text)
        
        # 3. Достаем паттерны поведения
        patterns = await self.store.get_volitional_patterns(user_id)

        return {
            "episodic_memory": [e.dict() for e in episodic],
            "semantic_facts": [s.dict() for s in semantic],
            "known_patterns": [p.dict() for p in patterns]
        }
